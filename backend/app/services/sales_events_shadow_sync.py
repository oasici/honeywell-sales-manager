"""Nightly idempotent materialization into v4_sales_events_shadow (additive; CRM writers untouched)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.additive.projectors import (
    activity_log_to_canonical,
    opportunity_event_to_canonical,
    opportunity_signal_to_canonical,
    revenue_signal_to_canonical,
)
from app.models.activity_log import ActivityLog
from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal
from app.models.revenue_signal import RevenueSignal
from app.models.sales_event_shadow import SalesEventShadow

SHADOW_PREFIX = "shadow:"


def shadow_source_ref(synthetic_id: str) -> str:
    return f"{SHADOW_PREFIX}{synthetic_id}"


def _row_from_canonical(c, *, event_dt: datetime, synced_at: datetime) -> SalesEventShadow:
    return SalesEventShadow(
        source_ref=shadow_source_ref(c.synthetic_id),
        provenance=c.provenance,
        account_id=c.account_id,
        opportunity_id=c.opportunity_id,
        contact_id=c.contact_id,
        event_type=c.event_type,
        event_ts=event_dt,
        actor_type=c.actor_type,
        actor_id=c.actor_id,
        channel=c.channel,
        direction=c.direction,
        payload_json=json.dumps(c.payload_json, ensure_ascii=False),
        synced_at=synced_at,
    )


async def _existing_refs(db: AsyncSession, refs: list[str]) -> set[str]:
    if not refs:
        return set()
    rows = (await db.execute(select(SalesEventShadow.source_ref).where(SalesEventShadow.source_ref.in_(refs)))).all()
    return {str(r[0]) for r in rows}


async def sync_sales_events_shadow_window(
    db: AsyncSession,
    *,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, int]:
    """Upsert-less idempotent inserts: skip rows whose source_ref already exists."""
    synced_at = datetime.now(timezone.utc)
    counts: dict[str, int] = {
        "activity_logs": 0,
        "opportunity_events": 0,
        "revenue_signals": 0,
        "opportunity_signals": 0,
        "skipped": 0,
    }

    logs = (
        await db.execute(
            select(ActivityLog).where(
                ActivityLog.opportunity_id.isnot(None),
                ActivityLog.created_at >= window_start,
                ActivityLog.created_at < window_end,
            )
        )
    ).scalars().all()

    refs_a = [shadow_source_ref(activity_log_to_canonical(l, account_id=int(l.customer_id) if l.customer_id else None).synthetic_id) for l in logs]
    have_a = await _existing_refs(db, refs_a)
    for log in logs:
        c = activity_log_to_canonical(log, account_id=int(log.customer_id) if log.customer_id else None)
        ref = shadow_source_ref(c.synthetic_id)
        if ref in have_a:
            counts["skipped"] += 1
            continue
        dt = log.created_at or synced_at
        db.add(_row_from_canonical(c, event_dt=dt, synced_at=synced_at))
        have_a.add(ref)
        counts["activity_logs"] += 1

    evs = (
        await db.execute(
            select(OpportunityEvent).where(
                OpportunityEvent.occurred_at >= window_start,
                OpportunityEvent.occurred_at < window_end,
            )
        )
    ).scalars().all()
    opp_ids = {int(e.opportunity_id) for e in evs}
    opp_map: dict[int, Opportunity | None] = {}
    if opp_ids:
        opps = (await db.execute(select(Opportunity).where(Opportunity.id.in_(opp_ids)))).scalars().all()
        opp_map = {int(o.id): o for o in opps}

    refs_e = []
    for ev in evs:
        o = opp_map.get(int(ev.opportunity_id))
        aid = int(o.customer_id) if o and o.customer_id else None
        c = opportunity_event_to_canonical(ev, account_id=aid)
        refs_e.append(shadow_source_ref(c.synthetic_id))
    have_e = await _existing_refs(db, refs_e)
    for ev in evs:
        o = opp_map.get(int(ev.opportunity_id))
        aid = int(o.customer_id) if o and o.customer_id else None
        c = opportunity_event_to_canonical(ev, account_id=aid)
        ref = shadow_source_ref(c.synthetic_id)
        if ref in have_e:
            counts["skipped"] += 1
            continue
        dt = ev.occurred_at or synced_at
        db.add(_row_from_canonical(c, event_dt=dt, synced_at=synced_at))
        have_e.add(ref)
        counts["opportunity_events"] += 1

    sigs = (
        await db.execute(
            select(RevenueSignal).where(
                RevenueSignal.opportunity_id.isnot(None),
                RevenueSignal.created_at >= window_start,
                RevenueSignal.created_at < window_end,
            )
        )
    ).scalars().all()
    refs_s = [shadow_source_ref(revenue_signal_to_canonical(s).synthetic_id) for s in sigs]
    have_s = await _existing_refs(db, refs_s)
    for rs in sigs:
        c = revenue_signal_to_canonical(rs)
        ref = shadow_source_ref(c.synthetic_id)
        if ref in have_s:
            counts["skipped"] += 1
            continue
        dt = rs.created_at or synced_at
        db.add(_row_from_canonical(c, event_dt=dt, synced_at=synced_at))
        have_s.add(ref)
        counts["revenue_signals"] += 1

    oss = (
        await db.execute(
            select(OpportunitySignal).where(
                OpportunitySignal.created_at >= window_start,
                OpportunitySignal.created_at < window_end,
            )
        )
    ).scalars().all()
    opp_ids_o = {int(s.opportunity_id) for s in oss}
    missing_o = opp_ids_o - set(opp_map.keys())
    if missing_o:
        extra_o = (await db.execute(select(Opportunity).where(Opportunity.id.in_(missing_o)))).scalars().all()
        for o in extra_o:
            opp_map[int(o.id)] = o

    refs_o = []
    for s in oss:
        o = opp_map.get(int(s.opportunity_id))
        aid = int(o.customer_id) if o and o.customer_id else None
        c = opportunity_signal_to_canonical(s, account_id=aid)
        refs_o.append(shadow_source_ref(c.synthetic_id))
    have_o = await _existing_refs(db, refs_o)
    for s in oss:
        o = opp_map.get(int(s.opportunity_id))
        aid = int(o.customer_id) if o and o.customer_id else None
        c = opportunity_signal_to_canonical(s, account_id=aid)
        ref = shadow_source_ref(c.synthetic_id)
        if ref in have_o:
            counts["skipped"] += 1
            continue
        dt = s.created_at or synced_at
        db.add(_row_from_canonical(c, event_dt=dt, synced_at=synced_at))
        have_o.add(ref)
        counts["opportunity_signals"] += 1

    await db.commit()
    return counts


async def sync_sales_events_shadow_last_n_days(db: AsyncSession, *, days: int) -> dict[str, int]:
    """Rolling UTC window for manual backfill (manager/operations)."""
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(seconds=1)
    window_start = now - timedelta(days=int(days))
    return await sync_sales_events_shadow_window(db, window_start=window_start, window_end=window_end)


async def sync_sales_events_shadow_yesterday(db: AsyncSession) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    today_mid = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    window_end = today_mid
    window_start = today_mid - timedelta(days=1)
    return await sync_sales_events_shadow_window(db, window_start=window_start, window_end=window_end)
