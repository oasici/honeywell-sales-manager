"""Read-only Sales DNA miner: aggregates from OFD, activity, opportunity_events, revenue_signals, buyer_state."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.buyer_state_history import BuyerStateHistory
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity, OpportunityEvent
from app.models.revenue_signal import RevenueSignal
from app.models.sales_dna_snapshot import SalesDnaSnapshot

MINER_VERSION = "v4-sales-dna-mvp-1"

_RISK_TYPES = frozenset({"deal_risk", "churn_risk", "discount_risk", "sla_breach", "objection"})


def _window_bounds(snapshot_date: date) -> tuple[datetime, datetime]:
    end_dt = datetime.combine(snapshot_date, time(23, 59, 59), tzinfo=timezone.utc)
    start_30 = end_dt - timedelta(days=30)
    return start_30, end_dt


def _rhythm_label(activity_n: int, ev_n: int) -> str:
    total = activity_n + ev_n
    if total <= 2:
        return "sparse"
    if total <= 12:
        return "steady"
    return "intense"


def _build_traits(
    *,
    snapshot_date: date,
    ofd: OpportunityFeaturesDaily | None,
    activity_count: int,
    opp_event_count: int,
    signal_counts: dict[str, int],
    buyer_state_row: BuyerStateHistory | None,
) -> dict[str, Any]:
    total_signals = sum(signal_counts.values())
    riskish = sum(signal_counts.get(t, 0) for t in _RISK_TYPES)

    risk_posture = "low"
    if ofd is not None:
        if int(ofd.negative_signal_count_14d or 0) >= 3 or int(ofd.pricing_objections_30d or 0) >= 2:
            risk_posture = "high"
        elif int(ofd.negative_signal_count_14d or 0) >= 1 or int(ofd.pricing_objections_30d or 0) >= 1:
            risk_posture = "moderate"
    if risk_posture == "low" and riskish >= 3:
        risk_posture = "high"
    elif risk_posture == "low" and riskish >= 1:
        risk_posture = "moderate"

    hooks: list[str] = []
    if ofd is not None:
        if int(ofd.days_since_last_rep_touch or 999) > 7:
            hooks.append("rep_touch_stale")
        if int(ofd.days_since_last_buyer_touch or 999) > 14:
            hooks.append("buyer_quiet")
        if int(ofd.competitor_mentions_30d or 0) >= 2:
            hooks.append("competitive_pressure")
    if total_signals == 0 and activity_count + opp_event_count <= 1:
        hooks.append("low_signal_surface")
    hooks = hooks[:8]

    traits: dict[str, Any] = {
        "model_version": MINER_VERSION,
        "snapshot_date": snapshot_date.isoformat(),
        "engagement_30d": {
            "activity_log_count": activity_count,
            "opportunity_event_count": opp_event_count,
            "rhythm": _rhythm_label(activity_count, opp_event_count),
        },
        "revenue_signals_30d": {"by_type": dict(sorted(signal_counts.items())), "total": total_signals},
        "feature_store_row": (
            None
            if not ofd
            else {
                "snapshot_date": ofd.snapshot_date.isoformat(),
                "momentum_band": ofd.momentum_band,
                "momentum_score": ofd.momentum_score,
                "buyer_state": ofd.buyer_state,
                "days_since_last_rep_touch": ofd.days_since_last_rep_touch,
                "days_since_last_buyer_touch": ofd.days_since_last_buyer_touch,
                "negative_signal_count_14d": ofd.negative_signal_count_14d,
                "pricing_objections_30d": ofd.pricing_objections_30d,
            }
        ),
        "buyer_state_history": (
            None
            if not buyer_state_row
            else {
                "snapshot_date": buyer_state_row.snapshot_date.isoformat(),
                "state": buyer_state_row.state,
                "confidence": buyer_state_row.confidence,
            }
        ),
        "risk_posture": risk_posture,
        "coaching_hooks": hooks,
    }
    return traits


async def materialize_sales_dna_snapshot(
    db: AsyncSession,
    opportunity_id: int,
    snapshot_date: date,
) -> SalesDnaSnapshot:
    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if not opp:
        raise ValueError("opportunity_not_found")

    start_30, end_dt = _window_bounds(snapshot_date)

    activity_count = (
        await db.execute(
            select(func.count())
            .select_from(ActivityLog)
            .where(
                ActivityLog.opportunity_id == opportunity_id,
                ActivityLog.created_at >= start_30,
                ActivityLog.created_at <= end_dt,
            )
        )
    ).scalar_one()

    opp_event_count = (
        await db.execute(
            select(func.count())
            .select_from(OpportunityEvent)
            .where(
                OpportunityEvent.opportunity_id == opportunity_id,
                OpportunityEvent.occurred_at >= start_30,
                OpportunityEvent.occurred_at <= end_dt,
            )
        )
    ).scalar_one()

    sig_rows = (
        await db.execute(
            select(RevenueSignal.signal_type, func.count())
            .where(
                RevenueSignal.opportunity_id == opportunity_id,
                RevenueSignal.created_at >= start_30,
                RevenueSignal.created_at <= end_dt,
            )
            .group_by(RevenueSignal.signal_type)
        )
    ).all()
    signal_counts: dict[str, int] = {str(r[0]): int(r[1]) for r in sig_rows}

    ofd = (
        await db.execute(
            select(OpportunityFeaturesDaily).where(
                OpportunityFeaturesDaily.opportunity_id == opportunity_id,
                OpportunityFeaturesDaily.snapshot_date == snapshot_date,
            )
        )
    ).scalar_one_or_none()

    buyer_state_row = (
        await db.execute(
            select(BuyerStateHistory)
            .where(
                BuyerStateHistory.opportunity_id == opportunity_id,
                BuyerStateHistory.snapshot_date <= snapshot_date,
            )
            .order_by(BuyerStateHistory.snapshot_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    traits = _build_traits(
        snapshot_date=snapshot_date,
        ofd=ofd,
        activity_count=int(activity_count or 0),
        opp_event_count=int(opp_event_count or 0),
        signal_counts=signal_counts,
        buyer_state_row=buyer_state_row,
    )

    meta = {
        "miner_version": MINER_VERSION,
        "window_utc": {"start": start_30.isoformat(), "end": end_dt.isoformat()},
        "feature_daily_present": ofd is not None,
        "buyer_state_history_present": buyer_state_row is not None,
    }

    now = datetime.now(timezone.utc)
    traits_json = json.dumps(traits, default=str)
    meta_json = json.dumps(meta, default=str)

    existing = (
        await db.execute(
            select(SalesDnaSnapshot).where(
                SalesDnaSnapshot.opportunity_id == opportunity_id,
                SalesDnaSnapshot.snapshot_date == snapshot_date,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.traits_json = traits_json
        existing.meta_json = meta_json
        existing.miner_version = MINER_VERSION
        existing.updated_at = now
        await db.flush()
        return existing

    row = SalesDnaSnapshot(
        opportunity_id=opportunity_id,
        snapshot_date=snapshot_date,
        traits_json=traits_json,
        meta_json=meta_json,
        miner_version=MINER_VERSION,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return row
