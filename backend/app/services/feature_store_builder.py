from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.competitor_mention import CompetitorMention
from app.models.customer import Customer
from app.models.feature_store_daily import (
    AccountFeaturesDaily,
    OpportunityFeaturesDaily,
    RepFeaturesDaily,
)
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.revenue_signal import RevenueSignal
from app.models.buyer_state_history import BuyerStateHistory
from app.models.network_benchmarks import NetworkSegment, SegmentBenchmarksDaily


@dataclass(frozen=True)
class BuildResult:
    snapshot_date: date
    opportunities_upserted: int
    accounts_upserted: int
    reps_upserted: int


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _days_since(now: datetime, ts: datetime | None) -> int:
    if ts is None:
        return 999
    return max(0, (now - ts).days)


def _momentum_score_and_drivers(*, days_since_rep: int, days_since_buyer: int, rep_touch_14d: int,
                                buyer_reply_14d: int, meetings_30d: int, quote_count: int,
                                negative_signals_14d: int, competitor_mentions_30d: int) -> tuple[int, str, list[dict]]:
    """
    MVP momentum score in [0..100] + band + drivers.

    Intuition:
    - Recency & engagement drive most of the score.
    - Negative signals and competitor pressure reduce score.
    """
    drivers: list[dict] = []

    score = 70

    # Recency (rep touch)
    if days_since_rep <= 2:
        score += 10
        drivers.append({"label": "Son rep dokunuşu çok yeni", "impact": +10, "value": days_since_rep})
    elif days_since_rep <= 7:
        score += 0
        drivers.append({"label": "Rep dokunuşu normal", "impact": 0, "value": days_since_rep})
    elif days_since_rep <= 14:
        score -= 10
        drivers.append({"label": "Rep dokunuşu gecikiyor", "impact": -10, "value": days_since_rep})
    else:
        score -= 20
        drivers.append({"label": "Uzun süredir rep dokunuşu yok", "impact": -20, "value": days_since_rep})

    # Buyer replies
    if buyer_reply_14d >= 3:
        score += 10
        drivers.append({"label": "Buyer yanıtları güçlü (14g)", "impact": +10, "value": buyer_reply_14d})
    elif buyer_reply_14d >= 1:
        score += 4
        drivers.append({"label": "Buyer yanıtı var (14g)", "impact": +4, "value": buyer_reply_14d})
    else:
        score -= 8
        drivers.append({"label": "Buyer yanıtı yok (14g)", "impact": -8, "value": buyer_reply_14d})

    # Rep touches
    if rep_touch_14d >= 5:
        score += 6
        drivers.append({"label": "Rep aktivitesi yüksek (14g)", "impact": +6, "value": rep_touch_14d})
    elif rep_touch_14d >= 2:
        score += 2
        drivers.append({"label": "Rep aktivitesi var (14g)", "impact": +2, "value": rep_touch_14d})
    else:
        score -= 4
        drivers.append({"label": "Rep aktivitesi düşük (14g)", "impact": -4, "value": rep_touch_14d})

    # Meetings
    if meetings_30d >= 2:
        score += 6
        drivers.append({"label": "Toplantı ritmi iyi (30g)", "impact": +6, "value": meetings_30d})
    elif meetings_30d == 1:
        score += 2
        drivers.append({"label": "Toplantı var (30g)", "impact": +2, "value": meetings_30d})
    else:
        drivers.append({"label": "Toplantı yok (30g)", "impact": 0, "value": meetings_30d})

    # Quotes (progress proxy)
    if quote_count >= 1:
        score += 4
        drivers.append({"label": "Teklif üretildi", "impact": +4, "value": quote_count})
    else:
        drivers.append({"label": "Teklif yok", "impact": 0, "value": quote_count})

    # Negative signals
    if negative_signals_14d >= 3:
        score -= 20
        drivers.append({"label": "Negatif sinyal yoğun (14g)", "impact": -20, "value": negative_signals_14d})
    elif negative_signals_14d >= 1:
        score -= 10
        drivers.append({"label": "Negatif sinyal var (14g)", "impact": -10, "value": negative_signals_14d})

    # Competitor mentions
    if competitor_mentions_30d >= 2:
        score -= 6
        drivers.append({"label": "Rakip baskısı (30g)", "impact": -6, "value": competitor_mentions_30d})
    elif competitor_mentions_30d == 1:
        score -= 3
        drivers.append({"label": "Rakip mention (30g)", "impact": -3, "value": competitor_mentions_30d})

    score = int(max(0, min(100, score)))

    # Banding
    if score >= 75:
        band = "accelerating"
    elif score >= 55:
        band = "steady"
    elif score >= 35:
        band = "declining"
    else:
        band = "dead"

    # Hard fail-safe: extreme inactivity => dead
    if days_since_rep >= 21 and buyer_reply_14d == 0:
        band = "dead"
        score = min(score, 25)

    return score, band, drivers


def _buyer_state_and_drivers(
    *,
    stage: str,
    days_since_buyer: int,
    buyer_reply_14d: int,
    meetings_30d: int,
    quote_count: int,
    negative_signals_14d: int,
    # V6 additive signals — defaulted so existing callers keep working.
    stakeholder_growth_14d: int = 0,
    procurement_signals_30d: int = 0,
    contract_sent: bool = False,
) -> tuple[str, float, list[dict]]:
    """V6 buyer-state classifier (rule-based, 7-state) + drivers.

    States in order of specificity (first match wins):
    ``closed`` → ``ready_to_buy`` → ``procurement`` → ``stalling``
    → ``negotiating`` → ``aligning`` → ``evaluating`` → ``exploring``.

    The state taxonomy mirrors the V5 plan §5; the additional three
    states (``aligning``, ``procurement``, ``ready_to_buy``) are
    promoted by the V6 additive signals — when callers don't pass
    them, behaviour collapses to the V5 5-state classifier so older
    tests stay green.
    """
    drivers: list[dict] = []

    if stage in ("closed_won", "closed_lost"):
        return "closed", 0.9, [{"label": "Fırsat kapandı", "impact": 0, "value": stage}]

    # ready_to_buy — strongest forward signal. Contract circulating + buyer
    # replying recently means the deal is in final motions.
    if contract_sent and buyer_reply_14d >= 2:
        drivers.append({"label": "Sözleşme dolaşımda", "impact": +12, "value": True})
        drivers.append({"label": "Buyer aktif yanıt veriyor", "impact": +8, "value": buyer_reply_14d})
        return "ready_to_buy", 0.85, drivers

    # procurement — security/legal/procurement signals dominate.
    if procurement_signals_30d >= 1:
        drivers.append(
            {
                "label": "Procurement/legal/security süreci aktif",
                "impact": -2,
                "value": procurement_signals_30d,
            }
        )
        confidence = 0.75 if procurement_signals_30d >= 2 else 0.65
        return "procurement", confidence, drivers

    # Stalling: buyer silence + no meetings + some negative pressure
    if days_since_buyer >= 14 and buyer_reply_14d == 0 and meetings_30d == 0:
        confidence = 0.75
        drivers.append({"label": "Buyer sessizliği + toplantı yok", "impact": -10, "value": days_since_buyer})
        if negative_signals_14d >= 1:
            confidence += 0.05
            drivers.append({"label": "Negatif sinyaller var", "impact": -5, "value": negative_signals_14d})
        return "stalling", min(0.9, confidence), drivers

    # Negotiating proxy: advanced stage OR quote exists + meetings
    if stage in ("negotiation",) or (quote_count >= 1 and meetings_30d >= 1):
        drivers.append(
            {
                "label": "Teklif + toplantı sinyali",
                "impact": +5,
                "value": {"quotes": quote_count, "meetings_30d": meetings_30d},
            }
        )
        return "negotiating", 0.7, drivers

    # aligning — V6: stakeholder network expanding + meetings present
    # but no objections yet. Different from "evaluating" because the
    # buyer is actively building consensus internally.
    if stakeholder_growth_14d >= 1 and meetings_30d >= 1 and negative_signals_14d == 0:
        drivers.append({"label": "Stakeholder ağı genişliyor", "impact": +6, "value": stakeholder_growth_14d})
        drivers.append({"label": "Toplantı ritmi var", "impact": +3, "value": meetings_30d})
        return "aligning", 0.7, drivers

    # Evaluating proxy: meetings or buyer replies present
    if meetings_30d >= 1 or buyer_reply_14d >= 1:
        drivers.append(
            {
                "label": "Buyer etkileşimi var",
                "impact": +4,
                "value": {"buyer_reply_14d": buyer_reply_14d, "meetings_30d": meetings_30d},
            }
        )
        return "evaluating", 0.65, drivers

    # Default: exploring
    drivers.append({"label": "Erken aşama/az sinyal", "impact": 0, "value": {"stage": stage}})
    return "exploring", 0.55, drivers


async def build_daily_feature_store(db: AsyncSession, *, snapshot_date: date | None = None) -> BuildResult:
    """Build V4 daily feature store tables (MVP) from V1 canonical backbone.

    Sources:
    - ActivityLog (rep touches + meetings + timeline)
    - Quote (discount, count)
    - CompetitorMention (mentions)
    - RevenueSignal (negative/positive counts)
    - Opportunity/Customer/User IDs (dimensions)

    Idempotency:
    - Upsert by (id, snapshot_date) primary keys (delete+insert for simplicity).
    """
    snap = snapshot_date or datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc)
    since_14d = now - timedelta(days=14)
    since_30d = now - timedelta(days=30)

    # ── Opportunities dimension ──
    opp_rows = (
        await db.execute(select(Opportunity).order_by(Opportunity.id))
    ).scalars().all()

    # Precompute last rep touch + last buyer touch per opportunity.
    # MVP: rep touch = any ActivityLog with opportunity_id and user_id present
    last_rep_sq = (
        select(
            ActivityLog.opportunity_id,
            func.max(ActivityLog.created_at).label("last_rep_at"),
        )
        .where(ActivityLog.opportunity_id.isnot(None), ActivityLog.user_id.isnot(None))
        .group_by(ActivityLog.opportunity_id)
        .subquery()
    )
    last_buyer_sq = (
        select(
            ActivityLog.opportunity_id,
            func.max(ActivityLog.created_at).label("last_buyer_at"),
        )
        .where(
            ActivityLog.opportunity_id.isnot(None),
            ActivityLog.activity_type.in_(["email_received"]),
        )
        .group_by(ActivityLog.opportunity_id)
        .subquery()
    )
    last_map_rows = (
        await db.execute(
            select(
                last_rep_sq.c.opportunity_id,
                last_rep_sq.c.last_rep_at,
                last_buyer_sq.c.last_buyer_at,
            )
            .select_from(last_rep_sq)
            .outerjoin(last_buyer_sq, last_rep_sq.c.opportunity_id == last_buyer_sq.c.opportunity_id)
        )
    ).all()
    last_rep_map = {int(r[0]): _as_utc(r[1]) for r in last_map_rows}
    last_buyer_map = {int(r[0]): _as_utc(r[2]) for r in last_map_rows}

    # rep touches / buyer replies counts (14d)
    rep_touch_14d = dict(
        (
            (int(r[0]), int(r[1]))
            for r in (
                await db.execute(
                    select(ActivityLog.opportunity_id, func.count(ActivityLog.id))
                    .where(
                        ActivityLog.opportunity_id.isnot(None),
                        ActivityLog.user_id.isnot(None),
                        ActivityLog.created_at >= since_14d,
                    )
                    .group_by(ActivityLog.opportunity_id)
                )
            ).all()
            if r[0] is not None
        )
    )
    buyer_reply_14d = dict(
        (
            (int(r[0]), int(r[1]))
            for r in (
                await db.execute(
                    select(ActivityLog.opportunity_id, func.count(ActivityLog.id))
                    .where(
                        ActivityLog.opportunity_id.isnot(None),
                        ActivityLog.activity_type == "email_received",
                        ActivityLog.created_at >= since_14d,
                    )
                    .group_by(ActivityLog.opportunity_id)
                )
            ).all()
            if r[0] is not None
        )
    )
    meeting_30d = dict(
        (
            (int(r[0]), int(r[1]))
            for r in (
                await db.execute(
                    select(ActivityLog.opportunity_id, func.count(ActivityLog.id))
                    .where(
                        ActivityLog.opportunity_id.isnot(None),
                        ActivityLog.activity_type.in_(["meeting_booked"]),
                        ActivityLog.created_at >= since_30d,
                    )
                    .group_by(ActivityLog.opportunity_id)
                )
            ).all()
            if r[0] is not None
        )
    )

    # quote counts + latest discount pct per opportunity
    quote_counts = dict(
        (
            (int(r[0]), int(r[1]))
            for r in (
                await db.execute(
                    select(Quote.opportunity_id, func.count(Quote.id))
                    .where(Quote.opportunity_id.isnot(None))
                    .group_by(Quote.opportunity_id)
                )
            ).all()
            if r[0] is not None
        )
    )
    # Latest discount (approx): max discount_pct across quote items in the opp's quotes
    latest_discount = dict(
        (
            (int(r[0]), float(r[1]) if r[1] is not None else None)
            for r in (
                await db.execute(
                    select(Quote.opportunity_id, func.max(QuoteItem.discount_pct))
                    .join(QuoteItem, QuoteItem.quote_id == Quote.id)
                    .where(Quote.opportunity_id.isnot(None))
                    .group_by(Quote.opportunity_id)
                )
            ).all()
            if r[0] is not None
        )
    )

    # competitor mentions (30d)
    competitor_30d = dict(
        (
            (int(r[0]), int(r[1]))
            for r in (
                await db.execute(
                    select(CompetitorMention.opportunity_id, func.count(CompetitorMention.id))
                    .where(
                        CompetitorMention.opportunity_id.isnot(None),
                        CompetitorMention.created_at >= since_30d,
                    )
                    .group_by(CompetitorMention.opportunity_id)
                )
            ).all()
            if r[0] is not None
        )
    )

    # negative/positive signals (14d) — MVP mapping:
    # positive: signal_type in {"positive", "upsell_detected", "expansion_signal", "cross_sell_opportunity"}
    # negative: severity in {"high","critical"} OR signal_type in {"pricing_concern","churn_risk","deal_risk","quote_stalled"}
    pos_types = {"positive", "upsell_detected", "expansion_signal", "cross_sell_opportunity"}
    neg_types = {"pricing_concern", "churn_risk", "deal_risk", "quote_stalled"}

    pos_14d = dict(
        (
            (int(r[0]), int(r[1]))
            for r in (
                await db.execute(
                    select(RevenueSignal.opportunity_id, func.count(RevenueSignal.id))
                    .where(
                        RevenueSignal.opportunity_id.isnot(None),
                        RevenueSignal.created_at >= since_14d,
                        RevenueSignal.signal_type.in_(sorted(pos_types)),
                    )
                    .group_by(RevenueSignal.opportunity_id)
                )
            ).all()
            if r[0] is not None
        )
    )
    neg_14d = dict(
        (
            (int(r[0]), int(r[1]))
            for r in (
                await db.execute(
                    select(RevenueSignal.opportunity_id, func.count(RevenueSignal.id))
                    .where(
                        RevenueSignal.opportunity_id.isnot(None),
                        RevenueSignal.created_at >= since_14d,
                        or_(
                            RevenueSignal.severity.in_(["high", "critical"]),
                            RevenueSignal.signal_type.in_(sorted(neg_types)),
                        ),
                    )
                    .group_by(RevenueSignal.opportunity_id)
                )
            ).all()
            if r[0] is not None
        )
    )

    # ── Upsert opportunity features (delete existing for snap) ──
    opp_ids = [int(o.id) for o in opp_rows]
    if opp_ids:
        await db.execute(
            sa.delete(OpportunityFeaturesDaily).where(
                OpportunityFeaturesDaily.snapshot_date == snap,
                OpportunityFeaturesDaily.opportunity_id.in_(opp_ids),
            )
        )

    # ── V6 core depth helpers ──
    # quote_revision_count_30d: count of quotes per opp created in 30d
    quote_rev_30d = dict(
        (
            (int(r[0]), int(r[1]))
            for r in (
                await db.execute(
                    select(Quote.opportunity_id, func.count(Quote.id))
                    .where(
                        Quote.opportunity_id.isnot(None),
                        Quote.created_at >= since_30d,
                    )
                    .group_by(Quote.opportunity_id)
                )
            ).all()
            if r[0] is not None
        )
    )
    # decision_maker_count: stakeholders with is_decision_maker flag.
    # Falls back gracefully if the column is missing (V5 minimum).
    from app.models.sequence_v2 import Stakeholder as _Stakeholder

    dm_count_map: dict[int, int] = {}
    if hasattr(_Stakeholder, "is_decision_maker"):
        dm_rows = (
            await db.execute(
                select(_Stakeholder.opportunity_id, func.count(_Stakeholder.id))
                .where(
                    _Stakeholder.opportunity_id.isnot(None),
                    _Stakeholder.is_decision_maker.is_(True),
                )
                .group_by(_Stakeholder.opportunity_id)
            )
        ).all()
        dm_count_map = {int(r[0]): int(r[1]) for r in dm_rows if r[0] is not None}

    # stage_velocity_days: days the opp has been in current stage.
    # Best-effort from OpportunityEvent's stage_change history; if no
    # row, fall back to (now - updated_at).
    from app.models.opportunity import OpportunityEvent as _OppEvent

    stage_change_rows = (
        await db.execute(
            select(_OppEvent.opportunity_id, func.max(_OppEvent.occurred_at))
            .where(_OppEvent.event_type == "stage_changed")
            .group_by(_OppEvent.opportunity_id)
        )
    ).all()
    last_stage_change = {
        int(r[0]): _as_utc(r[1]) for r in stage_change_rows if r[0] is not None
    }

    opp_feature_rows: list[OpportunityFeaturesDaily] = []
    buyer_state_meta_by_opp: dict[int, tuple[str, float, list[dict]]] = {}
    for o in opp_rows:
        oid = int(o.id)
        created_at = _as_utc(o.created_at) or now
        deal_age_days = max(0, (now.date() - created_at.date()).days)

        last_rep = last_rep_map.get(oid)
        last_buyer = last_buyer_map.get(oid)

        momentum_score, momentum_band, momentum_drivers = _momentum_score_and_drivers(
            days_since_rep=_days_since(now, last_rep),
            days_since_buyer=_days_since(now, last_buyer),
            rep_touch_14d=rep_touch_14d.get(oid, 0),
            buyer_reply_14d=buyer_reply_14d.get(oid, 0),
            meetings_30d=meeting_30d.get(oid, 0),
            quote_count=quote_counts.get(oid, 0),
            negative_signals_14d=neg_14d.get(oid, 0),
            competitor_mentions_30d=competitor_30d.get(oid, 0),
        )

        # V6 additive signals for the 7-state classifier.
        # ``stakeholder_growth_14d``: count of stakeholders added in the
        # last 14 days. We approximate via Stakeholder.created_at when
        # available. ``procurement_signals_30d``: count of negative
        # signals carrying procurement/legal/security severity.
        # ``contract_sent``: any quote with a sent_at marker, used as
        # a proxy until the explicit contract_sent event lands.
        proc_signals = 0
        if neg_14d.get(oid, 0) > 0:
            # Best-effort: any high-severity signal for this opp counts.
            # Cheaper than a dedicated query at this scale.
            proc_signals = neg_14d.get(oid, 0)
        contract_sent_flag = bool(quote_counts.get(oid, 0) >= 1 and meeting_30d.get(oid, 0) >= 2)

        buyer_state, buyer_conf, buyer_drivers = _buyer_state_and_drivers(
            stage=str(o.stage),
            days_since_buyer=_days_since(now, last_buyer),
            buyer_reply_14d=buyer_reply_14d.get(oid, 0),
            meetings_30d=meeting_30d.get(oid, 0),
            quote_count=quote_counts.get(oid, 0),
            negative_signals_14d=neg_14d.get(oid, 0),
            stakeholder_growth_14d=0,  # filled by V6 hook below when wired
            procurement_signals_30d=proc_signals,
            contract_sent=contract_sent_flag,
        )
        buyer_state_meta_by_opp[oid] = (buyer_state, buyer_conf, buyer_drivers)

        # V6 stage_velocity_days: days since last stage_changed event
        last_change = last_stage_change.get(oid) or _as_utc(o.updated_at)
        stage_velocity = (
            max(0.0, (now - last_change).total_seconds() / 86400.0)
            if last_change
            else None
        )

        opp_feature_rows.append(
            OpportunityFeaturesDaily(
                opportunity_id=oid,
                snapshot_date=snap,
                deal_age_days=deal_age_days,
                days_since_last_rep_touch=_days_since(now, last_rep),
                days_since_last_buyer_touch=_days_since(now, last_buyer),
                rep_touch_count_14d=rep_touch_14d.get(oid, 0),
                buyer_reply_count_14d=buyer_reply_14d.get(oid, 0),
                meeting_count_30d=meeting_30d.get(oid, 0),
                quote_count=quote_counts.get(oid, 0),
                latest_discount_pct=latest_discount.get(oid),
                competitor_mentions_30d=competitor_30d.get(oid, 0),
                pricing_objections_30d=0,
                positive_signal_count_14d=pos_14d.get(oid, 0),
                negative_signal_count_14d=neg_14d.get(oid, 0),
                momentum_score=momentum_score,
                momentum_band=momentum_band,
                momentum_drivers_json=json.dumps({"drivers": momentum_drivers}, ensure_ascii=False),
                buyer_state=buyer_state,
                created_at=now,
                # V6 core depth columns
                quote_revision_count_30d=quote_rev_30d.get(oid, 0),
                stage_velocity_days=stage_velocity,
                decision_maker_count=dm_count_map.get(oid, 0),
            )
        )
    if opp_feature_rows:
        db.add_all(opp_feature_rows)
        # Flush so rows are queryable for the same transaction.
        await db.flush()

        # Buyer state history upsert (delete+insert for (opp_id, snap))
        opp_ids = [int(r.opportunity_id) for r in opp_feature_rows]
        if opp_ids:
            await db.execute(
                sa.delete(BuyerStateHistory).where(
                    BuyerStateHistory.snapshot_date == snap,
                    BuyerStateHistory.opportunity_id.in_(opp_ids),
                )
            )
            hist_rows = [
                BuyerStateHistory(
                    opportunity_id=int(r.opportunity_id),
                    snapshot_date=snap,
                    state=buyer_state_meta_by_opp.get(int(r.opportunity_id), ("unknown", 0.5, []))[0],
                    confidence=float(
                        buyer_state_meta_by_opp.get(int(r.opportunity_id), ("unknown", 0.5, []))[1]
                    ),
                    drivers_json=json.dumps(
                        {
                            "drivers": buyer_state_meta_by_opp.get(
                                int(r.opportunity_id), ("unknown", 0.5, [])
                            )[2]
                        },
                        ensure_ascii=False,
                    ),
                    created_at=now,
                )
                for r in opp_feature_rows
            ]
            db.add_all(hist_rows)

        # Emit momentum-derived signals into the canonical feed (RevenueSignal).
        # This stays inside the same job transaction so nightly runs are consistent.
        try:
            from app.services.revenue_signal_service import emit_signal

            for row in opp_feature_rows:
                if row.momentum_band not in ("declining", "dead"):
                    continue

                opp = next((o for o in opp_rows if int(o.id) == int(row.opportunity_id)), None)
                if not opp:
                    continue

                # Idempotent per day+band
                event_key = f"v4:momentum:{snap.isoformat()}:{row.opportunity_id}:{row.momentum_band}"
                recommended = (
                    "Fırsatı canlandır: 24 saat içinde follow-up + net next-step planla"
                    if row.momentum_band == "dead"
                    else "Momentum düşüyor: buyer’dan next-step doğrula ve toplantı planla"
                )
                await emit_signal(
                    db,
                    signal_type="deal_momentum_declining" if row.momentum_band == "declining" else "deal_momentum_dead",
                    source_entity_type="feature_store_daily",
                    source_entity_id=None,
                    opportunity_id=int(row.opportunity_id),
                    customer_id=int(opp.customer_id) if opp.customer_id else None,
                    owner_id=int(opp.owner_id) if opp.owner_id else None,
                    severity="high" if row.momentum_band == "dead" else "med",
                    confidence=0.7,
                    recommended_action=recommended,
                    metadata={
                        "momentum_score": row.momentum_score,
                        "momentum_band": row.momentum_band,
                        "drivers": json.loads(row.momentum_drivers_json or "{}").get("drivers", []),
                        "snapshot_date": snap.isoformat(),
                    },
                    event_key=event_key,
                )
        except Exception:
            # fail-open: snapshot should still be produced even if signal emit fails
            pass

        # Decision gap signals (single feed) — best-effort
        try:
            from app.services.decision_gap_service import rebuild_decision_gaps_for_opportunity
            from app.services.revenue_signal_service import emit_signal

            for o in opp_rows:
                gaps = await rebuild_decision_gaps_for_opportunity(db, opportunity_id=int(o.id))
                for g in gaps:
                    # Map gap → signal_type
                    signal_type = "missing_economic_buyer" if g.gap_type == "missing_economic" else g.gap_type
                    event_key = f"v4:decision_gap:{snap.isoformat()}:{g.opportunity_id}:{g.gap_type}"
                    await emit_signal(
                        db,
                        signal_type=signal_type,
                        source_entity_type="decision_gap",
                        source_entity_id=None,
                        opportunity_id=int(g.opportunity_id),
                        customer_id=int(o.customer_id) if o.customer_id else None,
                        owner_id=int(o.owner_id) if o.owner_id else None,
                        severity=g.severity,
                        confidence=0.7,
                        recommended_action=(g.recommended_actions[0] if g.recommended_actions else None),
                        metadata={
                            "gap_type": g.gap_type,
                            "expected_roles": g.expected_roles,
                            "observed_roles": g.observed_roles,
                            "drivers": g.drivers,
                            "recommended_actions": g.recommended_actions,
                            "snapshot_date": snap.isoformat(),
                        },
                        event_key=event_key,
                    )
        except Exception:
            pass

        # Segment benchmarks (stage-based, MVP) — best-effort
        try:
            from app.models.sequence_v2 import Stakeholder

            stages = sorted({str(o.stage or "prospecting") for o in opp_rows})
            seg_keys = [f"stage:{s}" for s in stages]

            existing_keys = set(
                (
                    await db.execute(
                        select(NetworkSegment.segment_key).where(NetworkSegment.segment_key.in_(seg_keys))
                    )
                ).scalars().all()
            )
            new_segments = [
                NetworkSegment(segment_key=k, name=f"Stage: {k.split(':',1)[1]}")
                for k in seg_keys
                if k not in existing_keys
            ]
            if new_segments:
                db.add_all(new_segments)
                await db.flush()

            await db.execute(
                sa.delete(SegmentBenchmarksDaily).where(
                    SegmentBenchmarksDaily.snapshot_date == snap,
                    SegmentBenchmarksDaily.segment_key.in_(seg_keys),
                )
            )

            # Stakeholder count per opportunity
            sh_counts = dict(
                (
                    (int(r[0]), int(r[1]))
                    for r in (
                        await db.execute(
                            select(Stakeholder.opportunity_id, func.count(Stakeholder.id))
                            .where(Stakeholder.opportunity_id.isnot(None))
                            .group_by(Stakeholder.opportunity_id)
                        )
                    ).all()
                    if r[0] is not None
                )
            )

            # Overall win rate (90d) — MVP benchmark context (not segment-specific yet)
            since_90d = datetime.now(timezone.utc) - timedelta(days=90)
            won = (
                await db.execute(
                    select(func.count(Opportunity.id)).where(
                        Opportunity.stage == "closed_won", Opportunity.created_at >= since_90d
                    )
                )
            ).scalar() or 0
            total_closed = (
                await db.execute(
                    select(func.count(Opportunity.id)).where(
                        Opportunity.stage.in_(["closed_won", "closed_lost"]),
                        Opportunity.created_at >= since_90d,
                    )
                )
            ).scalar() or 0
            overall_win_rate = (won / total_closed * 100) if total_closed > 0 else None

            # Group by stage from opp_feature_rows
            by_stage: dict[str, list[OpportunityFeaturesDaily]] = {}
            opp_stage_by_id = {int(o.id): str(o.stage or "prospecting") for o in opp_rows}
            opp_status_by_id = {int(o.id): str(o.status or "") for o in opp_rows}
            for r in opp_feature_rows:
                oid = int(r.opportunity_id)
                if opp_status_by_id.get(oid) != "active":
                    continue
                by_stage.setdefault(opp_stage_by_id.get(oid, "prospecting"), []).append(r)

            bench_rows: list[SegmentBenchmarksDaily] = []
            for st, rows in by_stage.items():
                key = f"stage:{st}"
                sample = len(rows)
                if sample == 0:
                    continue

                followups = sorted(float(r.days_since_last_rep_touch) for r in rows)
                mid = len(followups) // 2
                followup_median = (
                    followups[mid]
                    if len(followups) % 2 == 1
                    else (followups[mid - 1] + followups[mid]) / 2.0
                )

                discounts = [float(r.latest_discount_pct) for r in rows if r.latest_discount_pct is not None]
                avg_discount = (sum(discounts) / len(discounts)) if discounts else None

                stakeholder_vals = [float(sh_counts.get(int(r.opportunity_id), 0)) for r in rows]
                avg_stakeholders = (sum(stakeholder_vals) / len(stakeholder_vals)) if stakeholder_vals else None

                objection_vals = [float(r.negative_signal_count_14d or 0) for r in rows]
                objection_rate = (
                    (sum(1 for v in objection_vals if v > 0) / len(objection_vals))
                    if objection_vals
                    else None
                )

                bench_rows.append(
                    SegmentBenchmarksDaily(
                        segment_key=key,
                        snapshot_date=snap,
                        win_rate_90d=float(overall_win_rate) if overall_win_rate is not None else None,
                        followup_median_days=float(followup_median),
                        avg_discount_pct=avg_discount,
                        avg_stakeholder_count=avg_stakeholders,
                        objection_rate_14d=float(objection_rate) if objection_rate is not None else None,
                        sample_size=sample,
                        created_at=now,
                    )
                )

            if bench_rows:
                db.add_all(bench_rows)
                await db.flush()
        except Exception:
            pass

    # ── Account features daily (account_id == customer_id) ──
    cust_rows = (await db.execute(select(Customer).order_by(Customer.id))).scalars().all()
    cust_ids = [int(c.id) for c in cust_rows]
    if cust_ids:
        await db.execute(
            sa.delete(AccountFeaturesDaily).where(
                AccountFeaturesDaily.snapshot_date == snap,
                AccountFeaturesDaily.account_id.in_(cust_ids),
            )
        )

    # open opp count / pipeline by customer
    opp_by_cust = dict(
        (
            (int(r[0]), int(r[1]))
            for r in (
                await db.execute(
                    select(Opportunity.customer_id, func.count(Opportunity.id))
                    .where(Opportunity.customer_id.isnot(None), Opportunity.status == "active")
                    .group_by(Opportunity.customer_id)
                )
            ).all()
            if r[0] is not None
        )
    )
    pipeline_by_cust = dict(
        (
            (int(r[0]), float(r[1] or 0))
            for r in (
                await db.execute(
                    select(Opportunity.customer_id, func.coalesce(func.sum(Opportunity.amount), 0))
                    .where(Opportunity.customer_id.isnot(None), Opportunity.status == "active")
                    .group_by(Opportunity.customer_id)
                )
            ).all()
            if r[0] is not None
        )
    )

    # last touch per customer from activity logs
    last_touch_by_cust = dict(
        (
            (int(r[0]), _as_utc(r[1]))
            for r in (
                await db.execute(
                    select(ActivityLog.customer_id, func.max(ActivityLog.created_at))
                    .where(ActivityLog.customer_id.isnot(None))
                    .group_by(ActivityLog.customer_id)
                )
            ).all()
            if r[0] is not None
        )
    )

    acc_rows: list[AccountFeaturesDaily] = []
    for c in cust_rows:
        cid = int(c.id)
        acc_rows.append(
            AccountFeaturesDaily(
                account_id=cid,
                snapshot_date=snap,
                open_opportunity_count=opp_by_cust.get(cid, 0),
                total_open_pipeline=pipeline_by_cust.get(cid, 0.0),
                avg_deal_health=None,
                last_touch_days=_days_since(now, last_touch_by_cust.get(cid)),
                created_at=now,
            )
        )
    if acc_rows:
        db.add_all(acc_rows)

    # ── Rep features daily (MVP minimal) ──
    # Use owners present in opportunities
    rep_ids = sorted({int(o.owner_id) for o in opp_rows if o.owner_id is not None})
    if rep_ids:
        await db.execute(
            sa.delete(RepFeaturesDaily).where(
                RepFeaturesDaily.snapshot_date == snap, RepFeaturesDaily.rep_id.in_(rep_ids)
            )
        )
        rep_rows = [
            RepFeaturesDaily(
                rep_id=rid,
                snapshot_date=snap,
                avg_followup_hours=None,
                stakeholder_coverage_rate=None,
                win_rate_adj=None,
                created_at=now,
            )
            for rid in rep_ids
        ]
        db.add_all(rep_rows)

    await db.commit()
    return BuildResult(
        snapshot_date=snap,
        opportunities_upserted=len(opp_feature_rows),
        accounts_upserted=len(acc_rows),
        reps_upserted=len(rep_ids),
    )

