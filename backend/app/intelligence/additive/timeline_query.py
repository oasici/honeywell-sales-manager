"""Shared DB reads for additive normalized sales-event timeline (read path only)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.additive.projectors import (
    activity_log_to_canonical,
    merge_canonical_timeline,
    opportunity_event_to_canonical,
    opportunity_signal_to_canonical,
    revenue_signal_to_canonical,
)
from app.intelligence.additive.schemas import CanonicalSalesEvent
from app.models.activity_log import ActivityLog
from app.models.opportunity import OpportunityEvent, OpportunitySignal
from app.models.revenue_signal import RevenueSignal


async def load_merged_canonical_timeline(
    db: AsyncSession,
    opportunity_id: int,
    *,
    account_id: int | None,
    limit: int,
    include_signals: bool = True,
    include_legacy_opportunity_signals: bool = False,
) -> list[CanonicalSalesEvent]:
    """Same merge rules as ``GET .../normalized-timeline`` (activity ∪ events ∪ optional signals)."""
    act_rows = (
        await db.execute(
            select(ActivityLog)
            .where(ActivityLog.opportunity_id == opportunity_id)
            .order_by(ActivityLog.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()

    ev_rows = (
        await db.execute(
            select(OpportunityEvent)
            .where(OpportunityEvent.opportunity_id == opportunity_id)
            .order_by(OpportunityEvent.occurred_at.asc())
            .limit(limit)
        )
    ).scalars().all()

    mapped: list[CanonicalSalesEvent] = []
    mapped.extend([activity_log_to_canonical(r, account_id=account_id) for r in act_rows])
    mapped.extend([opportunity_event_to_canonical(r, account_id=account_id) for r in ev_rows])

    if include_signals:
        sig_rows = (
            await db.execute(
                select(RevenueSignal)
                .where(RevenueSignal.opportunity_id == opportunity_id)
                .order_by(RevenueSignal.created_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        mapped.extend([revenue_signal_to_canonical(r) for r in sig_rows])

    if include_legacy_opportunity_signals:
        legacy_rows = (
            await db.execute(
                select(OpportunitySignal)
                .where(OpportunitySignal.opportunity_id == opportunity_id)
                .order_by(OpportunitySignal.created_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        mapped.extend([opportunity_signal_to_canonical(r, account_id=account_id) for r in legacy_rows])

    merged = merge_canonical_timeline(mapped)
    if len(merged) > limit:
        merged = merged[:limit]
    return merged
