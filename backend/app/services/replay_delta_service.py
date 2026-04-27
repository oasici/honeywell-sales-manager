"""Deal replay delta service (V6).

Walks an opportunity's ``opportunity_features_daily`` history pairwise
and emits ``deal_replay_deltas`` rows describing what changed and —
when the change is bad — a rule-based ``counterfactual_hint`` that
tells the rep what *should have* happened.

We use OFD as the source of truth (instead of
``v4_deal_replay_snapshots.frames_json``) because OFD already carries
the typed columns we need (momentum_score, latest_discount_pct, etc.).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity
from app.models.sales_event_shadow import SalesEventShadow
from app.models.v6_replay import DealReplayDelta

logger = logging.getLogger(__name__)


# ─────────────────────── counterfactual hints ────────────────────────


HINT_COMPETITIVE_RESPONSE_MISSING = "competitive_response_missing"
HINT_POST_QUOTE_GAP = "post_quote_followup_gap"
HINT_PROCUREMENT_UNENGAGED = "procurement_unengaged"
HINT_STAKEHOLDER_THINNING = "stakeholder_thinning"
HINT_DISCOUNT_SPIRAL = "discount_spiral"


@dataclass(frozen=True)
class _Pair:
    prev: OpportunityFeaturesDaily
    curr: OpportunityFeaturesDaily


def _as_utc(dt) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _hint_for_pair(
    pair: _Pair, events_between: list[SalesEventShadow]
) -> tuple[str | None, list[dict]]:
    """Return (hint_code, drivers) for a snapshot pair.

    Multiple hints can apply but we surface the *most actionable* one
    only — UI noise reduction. Drivers list is always populated so the
    explanation envelope downstream can show the supporting evidence.
    """
    drivers: list[dict] = []
    prev, curr = pair.prev, pair.curr

    # Drop in momentum is the trigger — if momentum hasn't dropped, we
    # don't bother emitting a counterfactual.
    momentum_drop = (prev.momentum_score or 50) - (curr.momentum_score or 50)

    competitor_seen = (curr.competitor_mentions_30d or 0) > (
        prev.competitor_mentions_30d or 0
    )
    if competitor_seen and (curr.days_since_last_rep_touch or 0) >= 5:
        drivers.append(
            {
                "label": "Rakip mention'a 5+ gün rep cevabı yok",
                "impact": -10,
                "value": curr.days_since_last_rep_touch,
            }
        )
        return HINT_COMPETITIVE_RESPONSE_MISSING, drivers

    # post_quote_followup_gap: at least one quote_sent event in window
    # AND days_since_last_rep_touch ≥ 3 (≈72h) AND no follow-up after.
    quote_sent_evs = [e for e in events_between if e.event_type == "quote_sent"]
    if quote_sent_evs:
        last_quote = max(quote_sent_evs, key=lambda e: e.event_ts)
        followups_after = [
            e
            for e in events_between
            if e.event_type in {"email_sent", "call_logged", "meeting_logged"}
            and e.event_ts > last_quote.event_ts
        ]
        if not followups_after and (curr.days_since_last_rep_touch or 0) >= 3:
            drivers.append(
                {
                    "label": "Quote sonrası 72+ saat follow-up yok",
                    "impact": -8,
                    "value": curr.days_since_last_rep_touch,
                }
            )
            return HINT_POST_QUOTE_GAP, drivers

    # procurement_unengaged: procurement-style negative signals exist
    # but stakeholder count didn't grow.
    if (curr.negative_signal_count_14d or 0) > (
        prev.negative_signal_count_14d or 0
    ):
        if (curr.decision_maker_count or 0) <= (prev.decision_maker_count or 0):
            drivers.append(
                {
                    "label": "Procurement/legal sinyali var, stakeholder büyümüyor",
                    "impact": -6,
                    "value": {
                        "neg_signals": curr.negative_signal_count_14d,
                        "dm_count": curr.decision_maker_count,
                    },
                }
            )
            return HINT_PROCUREMENT_UNENGAGED, drivers

    # stakeholder_thinning: explicit shrink in DM count.
    if (prev.decision_maker_count or 0) > (curr.decision_maker_count or 0):
        drivers.append(
            {
                "label": "Karar verici sayısı düştü",
                "impact": -7,
                "value": {
                    "from": prev.decision_maker_count,
                    "to": curr.decision_maker_count,
                },
            }
        )
        return HINT_STAKEHOLDER_THINNING, drivers

    # discount_spiral: discount climbed across snapshots.
    prev_d = prev.latest_discount_pct or 0.0
    curr_d = curr.latest_discount_pct or 0.0
    if curr_d > prev_d + 5:
        drivers.append(
            {
                "label": "İskonto yükseliyor",
                "impact": -5,
                "value": {"from": prev_d, "to": curr_d},
            }
        )
        return HINT_DISCOUNT_SPIRAL, drivers

    if momentum_drop >= 10:
        drivers.append(
            {"label": "Momentum düştü", "impact": -int(momentum_drop), "value": momentum_drop}
        )
    return None, drivers


# ─────────────────────── public entry points ─────────────────────────


async def compute_deltas(
    db: AsyncSession, *, opportunity_id: int
) -> int:
    """Recompute delta rows for one opportunity.

    Strategy:
      1. Pull all OFD rows for this opp ordered by snapshot_date.
      2. Walk pairwise; for each (prev, curr) emit a delta row when
         momentum or stakeholder count moved meaningfully.
      3. Idempotent on (opportunity_id, from_ts, to_ts) — we drop the
         old rows for this opp before re-writing.
    """
    rows = (
        await db.execute(
            select(OpportunityFeaturesDaily)
            .where(OpportunityFeaturesDaily.opportunity_id == opportunity_id)
            .order_by(OpportunityFeaturesDaily.snapshot_date.asc())
        )
    ).scalars().all()
    if len(rows) < 2:
        return 0

    # Drop stale deltas. Cheaper than per-pair upsert at our scale.
    existing = (
        await db.execute(
            select(DealReplayDelta).where(
                DealReplayDelta.opportunity_id == opportunity_id
            )
        )
    ).scalars().all()
    for d in existing:
        await db.delete(d)
    await db.flush()

    written = 0
    for i in range(1, len(rows)):
        prev, curr = rows[i - 1], rows[i]
        pair = _Pair(prev=prev, curr=curr)

        from_ts = datetime.combine(prev.snapshot_date, datetime.min.time(), tzinfo=timezone.utc)
        to_ts = datetime.combine(curr.snapshot_date, datetime.min.time(), tzinfo=timezone.utc)

        events_between = (
            await db.execute(
                select(SalesEventShadow)
                .where(SalesEventShadow.opportunity_id == opportunity_id)
                .where(SalesEventShadow.event_ts >= from_ts)
                .where(SalesEventShadow.event_ts <= to_ts + timedelta(days=1))
                .order_by(SalesEventShadow.event_ts.asc())
            )
        ).scalars().all()

        hint, drivers = _hint_for_pair(pair, list(events_between))
        momentum_delta = (curr.momentum_score or 0) - (prev.momentum_score or 0)
        if abs(momentum_delta) < 5 and hint is None:
            continue  # quiet day, nothing worth surfacing

        change_type = (
            "momentum_drop"
            if momentum_delta <= -5
            else "momentum_rise"
            if momentum_delta >= 5
            else "risk_increase"
        )
        impact_score = round(-momentum_delta / 100.0, 3)
        change_summary = (
            f"Momentum {prev.momentum_score} → {curr.momentum_score}"
            if prev.momentum_score is not None and curr.momentum_score is not None
            else None
        )

        db.add(
            DealReplayDelta(
                opportunity_id=opportunity_id,
                from_ts=from_ts,
                to_ts=to_ts,
                change_type=change_type,
                change_summary=change_summary,
                impact_score=impact_score,
                drivers_json=json.dumps({"drivers": drivers}, ensure_ascii=False),
                counterfactual_hint=hint,
            )
        )
        written += 1

    await db.flush()
    return written


async def list_deltas(
    db: AsyncSession, *, opportunity_id: int, limit: int = 20
) -> list[DealReplayDelta]:
    rows = (
        await db.execute(
            select(DealReplayDelta)
            .where(DealReplayDelta.opportunity_id == opportunity_id)
            .order_by(DealReplayDelta.to_ts.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)
