"""Real-time recompute hooks (V6).

V5 left momentum / buyer-state / decision-gap recomputation to the
nightly batch. The product team's framework calls for these to be
near-real-time so a rep sees the current state right after logging
an activity. This module exposes a single async entry point
``recompute_after_activity`` that callers (typically
``activity_logger``) can fire-and-forget after persisting an event.

Design constraints
------------------
- Must be **best-effort**: if anything raises, swallow + log so we
  never break the upstream write path.
- Must be **flag-gated** (``FEATURE_V6_REALTIME``) so we can disable
  in incidents without redeploying.
- Must be **idempotent**: calling twice for the same opp on the same
  day produces the same OFD row.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity

logger = logging.getLogger(__name__)


KIND_MOMENTUM = "momentum"
KIND_BUYER = "buyer"
KIND_GAP = "gap"
KIND_TIMING = "timing"
DEFAULT_KINDS = (KIND_MOMENTUM, KIND_BUYER, KIND_GAP, KIND_TIMING)


async def recompute_after_activity(
    db: AsyncSession,
    *,
    opportunity_id: int | None,
    kinds: Iterable[str] = DEFAULT_KINDS,
) -> dict[str, str]:
    """Recompute downstream state for one opportunity.

    Returns a small per-kind status map for observability. Empty map
    when the V6 realtime flag is off or ``opportunity_id`` is missing.
    """
    if not getattr(settings, "FEATURE_V6_REALTIME", False):
        return {}
    if opportunity_id is None:
        return {}

    opp = await db.get(Opportunity, opportunity_id)
    if opp is None:
        return {"status": "opp_not_found"}

    today = datetime.now(timezone.utc).date()
    status: dict[str, str] = {}

    kinds_set = set(kinds)

    # Momentum + buyer-state come from the same OFD row, so we run the
    # builder once and let the configured kinds_set decide which
    # downstream field is "live".
    if kinds_set & {KIND_MOMENTUM, KIND_BUYER}:
        try:
            await _recompute_ofd(db, opportunity_id=opportunity_id, snapshot_date=today)
            status[KIND_MOMENTUM] = "ok"
            status[KIND_BUYER] = "ok"
        except Exception as exc:
            logger.warning("v6 recompute_ofd failed opp=%s: %s", opportunity_id, exc)
            status[KIND_MOMENTUM] = "fail"
            status[KIND_BUYER] = "fail"

    if KIND_GAP in kinds_set:
        try:
            from app.services.decision_gap_service import (
                rebuild_decision_gaps_for_opportunity,
            )

            await rebuild_decision_gaps_for_opportunity(db, opportunity_id=opportunity_id)
            status[KIND_GAP] = "ok"
        except Exception as exc:
            logger.warning("v6 decision_gap recompute failed opp=%s: %s", opportunity_id, exc)
            status[KIND_GAP] = "fail"

    if KIND_TIMING in kinds_set:
        try:
            from app.services.timing_engine_service import (
                materialize_windows_for_opportunity,
            )

            await materialize_windows_for_opportunity(db, opportunity_id=opportunity_id)
            status[KIND_TIMING] = "ok"
        except Exception as exc:
            logger.warning("v6 timing recompute failed opp=%s: %s", opportunity_id, exc)
            status[KIND_TIMING] = "fail"

    return status


# ─────────────────────── per-opp OFD recompute ────────────────────────


async def _recompute_ofd(
    db: AsyncSession, *, opportunity_id: int, snapshot_date: date
) -> None:
    """Idempotent OFD upsert for one opportunity.

    Reuses the V4 helpers so the rule semantics stay consistent with
    the nightly job. We run them inline (not via the full
    ``build_daily_feature_store``) because the realtime path only
    cares about one row, not the whole tenant.
    """
    from app.services.feature_store_builder import (  # noqa: WPS433 (lazy import to avoid cycle)
        _as_utc,
        _buyer_state_and_drivers,
        _days_since,
        _momentum_score_and_drivers,
    )
    from datetime import timedelta
    import json

    from sqlalchemy import func

    from app.models.activity_log import ActivityLog
    from app.models.competitor_mention import CompetitorMention
    from app.models.quote import Quote
    from app.models.quote_item import QuoteItem
    from app.models.revenue_signal import RevenueSignal

    opp = await db.get(Opportunity, opportunity_id)
    if opp is None:
        return

    now = datetime.now(timezone.utc)
    since_14d = now - timedelta(days=14)
    since_30d = now - timedelta(days=30)

    last_rep = (
        await db.execute(
            select(func.max(ActivityLog.created_at)).where(
                ActivityLog.opportunity_id == opportunity_id,
                ActivityLog.user_id.isnot(None),
            )
        )
    ).scalar()
    last_buyer = (
        await db.execute(
            select(func.max(ActivityLog.created_at)).where(
                ActivityLog.opportunity_id == opportunity_id,
                ActivityLog.activity_type == "email_received",
            )
        )
    ).scalar()

    rep_touch_14d = (
        await db.execute(
            select(func.count(ActivityLog.id)).where(
                ActivityLog.opportunity_id == opportunity_id,
                ActivityLog.user_id.isnot(None),
                ActivityLog.created_at >= since_14d,
            )
        )
    ).scalar() or 0

    buyer_reply_14d = (
        await db.execute(
            select(func.count(ActivityLog.id)).where(
                ActivityLog.opportunity_id == opportunity_id,
                ActivityLog.activity_type == "email_received",
                ActivityLog.created_at >= since_14d,
            )
        )
    ).scalar() or 0

    meeting_count_30d = (
        await db.execute(
            select(func.count(ActivityLog.id)).where(
                ActivityLog.opportunity_id == opportunity_id,
                ActivityLog.activity_type.in_(["meeting_booked"]),
                ActivityLog.created_at >= since_30d,
            )
        )
    ).scalar() or 0

    quote_count = (
        await db.execute(
            select(func.count(Quote.id)).where(Quote.opportunity_id == opportunity_id)
        )
    ).scalar() or 0
    latest_discount = (
        await db.execute(
            select(func.max(QuoteItem.discount_pct))
            .join(Quote, Quote.id == QuoteItem.quote_id)
            .where(Quote.opportunity_id == opportunity_id)
        )
    ).scalar()

    competitor_mentions_30d = (
        await db.execute(
            select(func.count(CompetitorMention.id)).where(
                CompetitorMention.opportunity_id == opportunity_id,
                CompetitorMention.created_at >= since_30d,
            )
        )
    ).scalar() or 0

    neg_14d = (
        await db.execute(
            select(func.count(RevenueSignal.id)).where(
                RevenueSignal.opportunity_id == opportunity_id,
                RevenueSignal.created_at >= since_14d,
                RevenueSignal.severity.in_(["high", "critical"]),
            )
        )
    ).scalar() or 0
    pos_14d = (
        await db.execute(
            select(func.count(RevenueSignal.id)).where(
                RevenueSignal.opportunity_id == opportunity_id,
                RevenueSignal.created_at >= since_14d,
                RevenueSignal.signal_type.in_(["positive", "upsell_detected"]),
            )
        )
    ).scalar() or 0

    momentum_score, momentum_band, momentum_drivers = _momentum_score_and_drivers(
        days_since_rep=_days_since(now, _as_utc(last_rep)),
        days_since_buyer=_days_since(now, _as_utc(last_buyer)),
        rep_touch_14d=rep_touch_14d,
        buyer_reply_14d=buyer_reply_14d,
        meetings_30d=meeting_count_30d,
        quote_count=quote_count,
        negative_signals_14d=neg_14d,
        competitor_mentions_30d=competitor_mentions_30d,
    )

    buyer_state, _conf, _drivers = _buyer_state_and_drivers(
        stage=str(opp.stage),
        days_since_buyer=_days_since(now, _as_utc(last_buyer)),
        buyer_reply_14d=buyer_reply_14d,
        meetings_30d=meeting_count_30d,
        quote_count=quote_count,
        negative_signals_14d=neg_14d,
        procurement_signals_30d=neg_14d,  # best-effort proxy until typed signal lands
        contract_sent=quote_count >= 1 and meeting_count_30d >= 2,
    )

    created_at = _as_utc(opp.created_at) or now
    deal_age_days = max(0, (now.date() - created_at.date()).days)

    existing = (
        await db.execute(
            select(OpportunityFeaturesDaily)
            .where(OpportunityFeaturesDaily.opportunity_id == opportunity_id)
            .where(OpportunityFeaturesDaily.snapshot_date == snapshot_date)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = OpportunityFeaturesDaily(
            opportunity_id=opportunity_id,
            snapshot_date=snapshot_date,
        )
        db.add(existing)

    existing.deal_age_days = deal_age_days
    existing.days_since_last_rep_touch = _days_since(now, _as_utc(last_rep))
    existing.days_since_last_buyer_touch = _days_since(now, _as_utc(last_buyer))
    existing.rep_touch_count_14d = rep_touch_14d
    existing.buyer_reply_count_14d = buyer_reply_14d
    existing.meeting_count_30d = meeting_count_30d
    existing.quote_count = quote_count
    existing.latest_discount_pct = float(latest_discount) if latest_discount is not None else None
    existing.competitor_mentions_30d = competitor_mentions_30d
    existing.positive_signal_count_14d = pos_14d
    existing.negative_signal_count_14d = neg_14d
    existing.momentum_score = momentum_score
    existing.momentum_band = momentum_band
    existing.momentum_drivers_json = json.dumps({"drivers": momentum_drivers}, ensure_ascii=False)
    existing.buyer_state = buyer_state

    await db.flush()
