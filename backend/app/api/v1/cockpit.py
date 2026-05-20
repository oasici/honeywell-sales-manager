"""Revenue Cockpit API — single-screen signal + KPI + action endpoints.

This is the "command center" read layer. Write operations (resolve, generate)
are minimal. All heavy computation happens in services.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, Query
import sqlalchemy
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.enums import UserRole
from app.models.opportunity import Opportunity, OpportunitySignal, Task
from app.models.quote import Quote
from app.models.revenue_signal import RevenueSignal
from app.models.user import User
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.services.deal_health_service import DealHealthService
from app.services.customer_health_service import CustomerHealthService
from app.services import revenue_signal_service
from app.api.v1.opportunities import _opportunity_staleness_days
from app.schemas.cockpit import (
    CockpitActionsResponse,
    CockpitKPIsResponse,
    CockpitMomentumResponse,
    CockpitRiskyAccountsResponse,
    CockpitStallingResponse,
    CockpitTrendsResponse,
    ResolveSignalResponse,
    SignalStreamResponse,
)

router = APIRouter(prefix="/cockpit", tags=["Revenue Cockpit"])


def _require_cockpit():
    if not settings.FEATURE_REVENUE_COCKPIT:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/signals", response_model=SignalStreamResponse)
async def get_signals(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    severity: str | None = Query(None),
    signal_type: str | None = Query(None),
    opportunity_id: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Paginated signal stream. Scoped by role (rep sees own, manager sees all)."""
    owner_id = None
    if current_user.role == UserRole.SALES_REP.value:
        owner_id = current_user.id

    return await revenue_signal_service.get_signal_stream(
        db,
        owner_id=owner_id,
        opportunity_id=opportunity_id,
        severity=severity,
        signal_type=signal_type,
        limit=limit,
        offset=offset,
    )


@router.get("/kpis", response_model=CockpitKPIsResponse)
async def get_kpis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Revenue KPI strip. 6 core metrics."""
    owner_filter = None
    if current_user.role == UserRole.SALES_REP.value:
        owner_filter = current_user.id

    # Pipeline total (active opps)
    pipeline_q = select(func.coalesce(func.sum(Opportunity.amount), 0)).where(
        Opportunity.status == "active"
    )
    if owner_filter:
        pipeline_q = pipeline_q.where(Opportunity.owner_id == owner_filter)
    pipeline_total = (await db.execute(pipeline_q)).scalar() or 0

    # Win rate (last 90 days)
    since_90d = datetime.now(timezone.utc) - timedelta(days=90)
    won_q = select(func.count(Opportunity.id)).where(
        Opportunity.stage == "closed_won",
        Opportunity.created_at >= since_90d,
    )
    total_closed_q = select(func.count(Opportunity.id)).where(
        Opportunity.stage.in_(["closed_won", "closed_lost"]),
        Opportunity.created_at >= since_90d,
    )
    if owner_filter:
        won_q = won_q.where(Opportunity.owner_id == owner_filter)
        total_closed_q = total_closed_q.where(Opportunity.owner_id == owner_filter)

    won = (await db.execute(won_q)).scalar() or 0
    total_closed = (await db.execute(total_closed_q)).scalar() or 0
    win_rate = round((won / total_closed * 100) if total_closed > 0 else 0, 1)

    # At-risk count (signals with severity high/critical, unresolved)
    risk_q = select(func.count(RevenueSignal.id)).where(
        RevenueSignal.severity.in_(["high", "critical"]),
        RevenueSignal.is_resolved.is_(False),
    )
    if owner_filter:
        risk_q = risk_q.where(RevenueSignal.owner_id == owner_filter)
    at_risk_count = (await db.execute(risk_q)).scalar() or 0

    # Avg deal velocity (days from created to closed_won, last 90d)
    from sqlalchemy import extract
    velocity_q = select(
        func.avg(
            extract("epoch", Opportunity.updated_at) / 86400.0
            - extract("epoch", Opportunity.created_at) / 86400.0
        )
    ).where(
        Opportunity.stage == "closed_won",
        Opportunity.created_at >= since_90d,
    )
    if owner_filter:
        velocity_q = velocity_q.where(Opportunity.owner_id == owner_filter)
    avg_velocity = (await db.execute(velocity_q)).scalar()
    avg_velocity_days = round(avg_velocity, 1) if avg_velocity else 0

    # Open AI tasks (action queue size)
    task_q = select(func.count(Task.id)).where(
        Task.source == "ai", Task.status == "open"
    )
    if owner_filter:
        task_q = task_q.where(Task.owner_id == owner_filter)
    open_ai_tasks = (await db.execute(task_q)).scalar() or 0

    # Signal stats
    signal_stats = await revenue_signal_service.get_signal_stats(
        db, owner_id=owner_filter
    )

    return {
        "pipeline_total": float(pipeline_total),
        "pipeline_currency": "TRY",
        "win_rate": win_rate,
        "at_risk_count": at_risk_count,
        "avg_deal_velocity_days": avg_velocity_days,
        "open_ai_tasks": open_ai_tasks,
        "signal_stats": signal_stats,
    }


@router.get("/actions", response_model=CockpitActionsResponse)
async def get_actions(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """AI-recommended action queue (Tasks with source='ai', status='open').

    Sprint 2: enrich each action with deal intelligence so the cockpit can show
    "next best actions" that are actually prioritized by risk + staleness.
    """
    conditions = [Task.source == "ai", Task.status == "open"]
    if current_user.role == UserRole.SALES_REP.value:
        conditions.append(Task.owner_id == current_user.id)

    result = await db.execute(
        select(Task)
        .where(and_(*conditions))
        .order_by(
            # urgent > high > normal > low
            sqlalchemy.case(
                (Task.priority == "urgent", 0),
                (Task.priority == "high", 1),
                (Task.priority == "normal", 2),
                else_=3,
            ),
            Task.created_at.desc(),
        )
        .limit(limit)
    )
    tasks = result.scalars().all()

    opp_ids = sorted({int(t.opportunity_id) for t in tasks if t.opportunity_id is not None})

    # Enrichment (batch)
    opp_map: dict[int, Opportunity] = {}
    last_activity_map: dict[int, datetime | None] = {}
    open_tasks_map: dict[int, int] = {}
    deal_health_map: dict[int, dict[str, int | str]] = {}

    if opp_ids:
        # Opportunities for rotting_days
        opp_rows = (
            await db.execute(select(Opportunity).where(Opportunity.id.in_(opp_ids)))
        ).scalars().all()
        opp_map = {int(o.id): o for o in opp_rows}

        # Last activity per opportunity
        from app.models.activity_log import ActivityLog

        last_rows = (
            await db.execute(
                select(ActivityLog.opportunity_id, func.max(ActivityLog.created_at))
                .where(ActivityLog.opportunity_id.in_(opp_ids))
                .group_by(ActivityLog.opportunity_id)
            )
        ).all()
        last_activity_map = {int(row[0]): row[1] for row in last_rows}

        # Open tasks count per opportunity (all sources)
        task_rows = (
            await db.execute(
                select(Task.opportunity_id, func.count(Task.id))
                .where(Task.opportunity_id.in_(opp_ids), Task.status == "open")
                .group_by(Task.opportunity_id)
            )
        ).all()
        open_tasks_map = {int(row[0]): int(row[1]) for row in task_rows}

        # Deal health (optimized batch) → map by opportunity_id
        owner_filter = None
        if current_user.role == UserRole.SALES_REP.value:
            owner_filter = current_user.id
        health_service = DealHealthService(db)
        # batch method already applies owner scoping; then we filter down to opp_ids
        reports = await health_service.get_all_deal_health_batch(owner_id=owner_filter)
        for r in reports:
            if int(r.opportunity_id) in opp_ids:
                deal_health_map[int(r.opportunity_id)] = {
                    "score": int(r.score),
                    "risk_level": str(r.risk_level),
                }

    def risk_rank(level: str | None) -> int:
        return {
            "critical": 4,
            "high_risk": 3,
            "at_risk": 2,
            "healthy": 1,
        }.get(level or "", 0)

    now = datetime.now(timezone.utc)

    def rotting_days_for(opp_id: int | None) -> int:
        if opp_id is None:
            return 0
        oid = int(opp_id)
        opp = opp_map.get(oid)
        if not opp:
            return 0
        la = last_activity_map.get(oid)
        return _opportunity_staleness_days(opp, la)

    # Re-sort tasks with enrichment signals (risk → rotting → due → priority → created)
    def priority_rank(p: str | None) -> int:
        return {"urgent": 0, "high": 1, "normal": 2, "low": 3}.get(p or "", 4)

    def due_rank(d: datetime | None) -> tuple[int, datetime]:
        # no due dates should go last
        if d is None:
            return (1, now)
        dt = d
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (0, dt)

    tasks_sorted = sorted(
        tasks,
        key=lambda t: (
            -risk_rank(deal_health_map.get(int(t.opportunity_id or 0), {}).get("risk_level")),  # type: ignore[arg-type]
            -rotting_days_for(t.opportunity_id),
            due_rank(t.due_at),
            priority_rank(t.priority),
            -(t.created_at.timestamp() if t.created_at else 0),
        ),
    )

    return {
        "items": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "opportunity_id": t.opportunity_id,
                "owner_id": t.owner_id,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "rotting_days": rotting_days_for(t.opportunity_id),
                "last_activity_at": (
                    last_activity_map.get(int(t.opportunity_id)).isoformat()
                    if t.opportunity_id is not None and last_activity_map.get(int(t.opportunity_id)) is not None
                    else None
                ),
                "open_tasks_count": (
                    open_tasks_map.get(int(t.opportunity_id), 0) if t.opportunity_id is not None else 0
                ),
                "deal_health": (
                    deal_health_map.get(int(t.opportunity_id)) if t.opportunity_id is not None else None
                ),
            }
            for t in tasks_sorted
        ],
        "total": len(tasks_sorted),
    }


@router.get("/risky-accounts", response_model=CockpitRiskyAccountsResponse)
async def get_risky_accounts(
    limit: int = Query(12, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Accounts (customers) with poor health plus operational load on active pipeline.

    Uses CustomerHealthService for account-level risk, then enriches with counts
    scoped to the caller's pipeline visibility (rep: own opps only).
    """
    owner_filter = None
    if current_user.role == UserRole.SALES_REP.value:
        owner_filter = current_user.id

    # N15-AUTH-4 — tenant scope on the at-risk fan-out.
    health = CustomerHealthService(db)
    reports = await health.get_at_risk_customers(
        limit=max(limit * 3, limit), tenant_id=current_user.tenant_id,
    )

    # Rep: only customers where they still have active pipeline
    if owner_filter is not None:
        cust_rows = (
            await db.execute(
                select(Opportunity.customer_id)
                .where(
                    Opportunity.status == "active",
                    Opportunity.owner_id == owner_filter,
                    Opportunity.customer_id.is_not(None),
                )
                .distinct()
            )
        ).all()
        allowed = {int(row[0]) for row in cust_rows if row[0] is not None}
        reports = [r for r in reports if int(r.customer_id) in allowed]

    reports = reports[:limit]

    if not reports:
        return {"items": [], "total": 0}

    customer_ids = [int(r.customer_id) for r in reports]

    # Active opportunities per customer (scoped)
    opp_conds = [
        Opportunity.customer_id.in_(customer_ids),
        Opportunity.status == "active",
    ]
    if owner_filter is not None:
        opp_conds.append(Opportunity.owner_id == owner_filter)

    opps = (await db.execute(select(Opportunity).where(and_(*opp_conds)))).scalars().all()
    opps_by_customer: dict[int, list[Opportunity]] = {}
    opp_ids: list[int] = []
    for o in opps:
        cid = int(o.customer_id) if o.customer_id is not None else None
        if cid is None:
            continue
        opps_by_customer.setdefault(cid, []).append(o)
        opp_ids.append(int(o.id))

    from app.models.activity_log import ActivityLog

    open_tasks_map: dict[int, int] = {}
    if opp_ids:
        task_rows = (
            await db.execute(
                select(Task.opportunity_id, func.count(Task.id))
                .where(Task.opportunity_id.in_(opp_ids), Task.status == "open")
                .group_by(Task.opportunity_id)
            )
        ).all()
        open_tasks_map = {int(row[0]): int(row[1]) for row in task_rows}

    last_activity_map: dict[int, datetime | None] = {}
    if opp_ids:
        last_rows = (
            await db.execute(
                select(ActivityLog.opportunity_id, func.max(ActivityLog.created_at))
                .where(ActivityLog.opportunity_id.in_(opp_ids))
                .group_by(ActivityLog.opportunity_id)
            )
        ).all()
        last_activity_map = {int(row[0]): row[1] for row in last_rows}

    high_sig_map: dict[int, int] = {}
    if opp_ids:
        sig_rows = (
            await db.execute(
                select(OpportunitySignal.opportunity_id, func.count(OpportunitySignal.id))
                .where(
                    OpportunitySignal.opportunity_id.in_(opp_ids),
                    OpportunitySignal.is_resolved.is_(False),
                    OpportunitySignal.severity.in_(["high", "critical"]),
                )
                .group_by(OpportunitySignal.opportunity_id)
            )
        ).all()
        high_sig_map = {int(row[0]): int(row[1]) for row in sig_rows}

    items = []
    for r in reports:
        cid = int(r.customer_id)
        cust_opps = opps_by_customer.get(cid, [])
        if not cust_opps:
            # Health says risk, but no visible pipeline for this user — skip
            continue

        open_tasks = 0
        last_ts: datetime | None = None
        high_sigs = 0
        pipeline = 0.0
        for o in cust_opps:
            oid = int(o.id)
            open_tasks += open_tasks_map.get(oid, 0)
            high_sigs += high_sig_map.get(oid, 0)
            la = last_activity_map.get(oid)
            if la is not None and (last_ts is None or la > last_ts):
                last_ts = la
            if o.amount is not None:
                pipeline += float(o.amount)

        items.append({
            "customer_id": cid,
            "customer_name": r.customer_name,
            "company": r.company,
            "health_score": r.score,
            "health_risk_level": r.risk_level,
            "active_opportunities": len(cust_opps),
            "pipeline_total": round(pipeline, 2),
            "open_tasks_count": open_tasks,
            "unresolved_high_signals": high_sigs,
            "last_activity_at": last_ts.isoformat() if last_ts else None,
        })

    # Round-11 R11-API-1 — canonical pagination envelope. These cockpit
    # endpoints all return a single bounded slice (limit-only), so page=1
    # and pages=ceil(total/page_size). Adding the keys lets the SPA reuse
    # its generic pagination components without per-endpoint branches.
    total = len(items)
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
    }


@router.get("/momentum", response_model=CockpitMomentumResponse)
async def get_momentum_declining(
    limit: int = Query(20, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Declining/dead momentum deals based on latest daily snapshot."""
    owner_filter = None
    if current_user.role == UserRole.SALES_REP.value:
        owner_filter = current_user.id

    latest_date = (
        await db.execute(select(func.max(OpportunityFeaturesDaily.snapshot_date)))
    ).scalar_one_or_none()
    if not latest_date:
        return {
            "snapshot_date": None,
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 0,
            "pages": 0,
        }

    conditions = [
        OpportunityFeaturesDaily.snapshot_date == latest_date,
        OpportunityFeaturesDaily.momentum_band.in_(["declining", "dead"]),
        Opportunity.status == "active",
    ]
    if owner_filter is not None:
        conditions.append(Opportunity.owner_id == owner_filter)

    rows = (
        await db.execute(
            select(
                Opportunity.id,
                Opportunity.title,
                Opportunity.stage,
                Opportunity.amount,
                Opportunity.currency,
                Opportunity.owner_id,
                Opportunity.customer_id,
                OpportunityFeaturesDaily.momentum_score,
                OpportunityFeaturesDaily.momentum_band,
                OpportunityFeaturesDaily.momentum_drivers_json,
            )
            .join(Opportunity, Opportunity.id == OpportunityFeaturesDaily.opportunity_id)
            .where(and_(*conditions))
            .order_by(
                OpportunityFeaturesDaily.momentum_band.desc(),
                OpportunityFeaturesDaily.momentum_score.asc().nullsfirst(),
            )
            .limit(limit)
        )
    ).all()

    return {
        "snapshot_date": latest_date.isoformat(),
        "items": [
            {
                "id": int(r.id),
                "title": r.title,
                "stage": r.stage,
                "amount": float(r.amount) if r.amount is not None else None,
                "currency": r.currency,
                "owner_id": int(r.owner_id) if r.owner_id is not None else None,
                "customer_id": int(r.customer_id) if r.customer_id is not None else None,
                "momentum_score": int(r.momentum_score) if r.momentum_score is not None else None,
                "momentum_band": r.momentum_band,
                "drivers": (
                    (json.loads(r.momentum_drivers_json).get("drivers", []) if r.momentum_drivers_json else [])
                ),
            }
            for r in rows
        ],
        "total": len(rows),
        # Round-11 R11-API-1 — canonical pagination envelope.
        "page": 1,
        "page_size": len(rows),
        "pages": 1 if rows else 0,
    }


@router.get("/buyer-state/stalling", response_model=CockpitStallingResponse)
async def get_stalling_deals(
    limit: int = Query(20, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Buyer-state stalling deals from latest snapshot."""
    owner_filter = None
    if current_user.role == UserRole.SALES_REP.value:
        owner_filter = current_user.id

    latest_date = (
        await db.execute(select(func.max(OpportunityFeaturesDaily.snapshot_date)))
    ).scalar_one_or_none()
    if not latest_date:
        return {
            "snapshot_date": None,
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 0,
            "pages": 0,
        }

    conditions = [
        OpportunityFeaturesDaily.snapshot_date == latest_date,
        OpportunityFeaturesDaily.buyer_state == "stalling",
        Opportunity.status == "active",
    ]
    if owner_filter is not None:
        conditions.append(Opportunity.owner_id == owner_filter)

    rows = (
        await db.execute(
            select(
                Opportunity.id,
                Opportunity.title,
                Opportunity.stage,
                Opportunity.amount,
                Opportunity.currency,
                Opportunity.owner_id,
                Opportunity.customer_id,
                OpportunityFeaturesDaily.days_since_last_buyer_touch,
                OpportunityFeaturesDaily.buyer_reply_count_14d,
                OpportunityFeaturesDaily.meeting_count_30d,
                OpportunityFeaturesDaily.negative_signal_count_14d,
            )
            .join(Opportunity, Opportunity.id == OpportunityFeaturesDaily.opportunity_id)
            .where(and_(*conditions))
            .order_by(
                OpportunityFeaturesDaily.days_since_last_buyer_touch.desc().nullslast(),
                OpportunityFeaturesDaily.negative_signal_count_14d.desc().nullslast(),
            )
            .limit(limit)
        )
    ).all()

    return {
        "snapshot_date": latest_date.isoformat(),
        "items": [
            {
                "id": int(r.id),
                "title": r.title,
                "stage": r.stage,
                "amount": float(r.amount) if r.amount is not None else None,
                "currency": r.currency,
                "owner_id": int(r.owner_id) if r.owner_id is not None else None,
                "customer_id": int(r.customer_id) if r.customer_id is not None else None,
                "days_since_last_buyer_touch": int(r.days_since_last_buyer_touch)
                if r.days_since_last_buyer_touch is not None
                else None,
                "buyer_reply_count_14d": int(r.buyer_reply_count_14d)
                if r.buyer_reply_count_14d is not None
                else 0,
                "meeting_count_30d": int(r.meeting_count_30d) if r.meeting_count_30d is not None else 0,
                "negative_signal_count_14d": int(r.negative_signal_count_14d)
                if r.negative_signal_count_14d is not None
                else 0,
            }
            for r in rows
        ],
        "total": len(rows),
        # Round-11 R11-API-1 — canonical pagination envelope.
        "page": 1,
        "page_size": len(rows),
        "pages": 1 if rows else 0,
    }


@router.post("/signals/{signal_id}/resolve", response_model=ResolveSignalResponse)
async def resolve_signal(
    signal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Mark a signal as resolved."""
    # Round-11 R11-AUTH-1 — tenant boundary check before write. Pre-fix,
    # any authenticated user could resolve any signal across tenants.
    from app.services.tenant_context import assert_same_tenant
    from app.core.exceptions import NotFoundException

    signal = (
        await db.execute(select(RevenueSignal).where(RevenueSignal.id == signal_id))
    ).scalar_one_or_none()
    if signal is None:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadi")
    assert_same_tenant(signal, current_user, exception_cls=NotFoundException)

    found = await revenue_signal_service.resolve_signal(db, signal_id)
    if not found:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadi")
    return {"message": "Sinyal cozuldu olarak isaretlendi", "signal_id": signal_id}


@router.get("/trends", response_model=CockpitTrendsResponse)
async def get_trends(
    weeks: int = Query(12, ge=1, le=52),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Time-series data for cockpit bottom charts."""
    now = datetime.now(timezone.utc)

    # Signal volume by week
    signal_weeks = []
    for i in range(weeks):
        week_end = now - timedelta(weeks=i)
        week_start = week_end - timedelta(days=7)
        count = (await db.execute(
            select(func.count(RevenueSignal.id)).where(
                RevenueSignal.created_at >= week_start,
                RevenueSignal.created_at < week_end,
            )
        )).scalar() or 0
        signal_weeks.append({
            "week": week_start.strftime("%Y-%m-%d"),
            "signal_count": count,
        })

    signal_weeks.reverse()

    return {
        "signal_volume": signal_weeks,
    }


# ── GET /cockpit/stream — Round-10 R10-SSE-1 ─────────────────────────
#
# SSE foundation. The CockpitPage previously fired 16 independent
# refetchInterval timers (30s + 60s × 5 + 120s × 9 + 300s × 1). On a
# 10-user instance with cockpit open 8 h/day that produced ~1200
# polling hits and 16 wakeups/minute per tab. This endpoint emits one
# `tick` event every 60 s as the source-of-truth heartbeat; the SPA
# consumes it via a single EventSource and calls
# `queryClient.invalidateQueries(['cockpit'])` once per tick, replacing
# all 16 inline timers with one shared connection.
#
# Future iterations can move real data deltas onto this stream (the
# current `data` payload only carries the tick number + ISO timestamp).
# The endpoint deliberately avoids long-lived DB connections and any
# stateful per-user buffering — it's a heartbeat, not a transport.


# Round-15 N15-API-1: response_model exempt (returns non-JSON: file/redirect/stream)
@router.get("/stream")
async def cockpit_stream(
    _: None = Depends(_require_cockpit),
    current_user: User = Depends(get_current_user),
):
    """Server-Sent Events heartbeat that drives FE cache invalidation.

    Emits one ``tick`` event per 60 s. The connection is closed by the
    FE when the user navigates away; the backend has no persistent
    state to clean up.
    """
    from fastapi.responses import StreamingResponse
    import asyncio

    async def _gen():
        # Initial hello so the FE knows the connection is healthy.
        yield (
            "event: hello\n"
            f"data: {{\"user_id\":{current_user.id},\"ts\":\"{datetime.now(timezone.utc).isoformat()}\"}}\n\n"
        )
        tick = 0
        while True:
            await asyncio.sleep(60)
            tick += 1
            yield (
                "event: tick\n"
                f"data: {{\"tick\":{tick},\"ts\":\"{datetime.now(timezone.utc).isoformat()}\"}}\n\n"
            )

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            # Keep proxies + browser from buffering / coalescing events.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
