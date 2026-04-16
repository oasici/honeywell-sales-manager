"""Revenue Cockpit API — single-screen signal + KPI + action endpoints.

This is the "command center" read layer. Write operations (resolve, generate)
are minimal. All heavy computation happens in services.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
import sqlalchemy
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.enums import UserRole
from app.models.opportunity import Opportunity, Task
from app.models.quote import Quote
from app.models.revenue_signal import RevenueSignal
from app.models.user import User
from app.services import revenue_signal_service

router = APIRouter(prefix="/cockpit", tags=["Revenue Cockpit"])


def _require_cockpit():
    if not settings.FEATURE_REVENUE_COCKPIT:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/signals")
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


@router.get("/kpis")
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


@router.get("/actions")
async def get_actions(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """AI-recommended action queue (Tasks with source='ai', status='open')."""
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
            }
            for t in tasks
        ],
        "total": len(tasks),
    }


@router.post("/signals/{signal_id}/resolve")
async def resolve_signal(
    signal_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Mark a signal as resolved."""
    found = await revenue_signal_service.resolve_signal(db, signal_id)
    if not found:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadi")
    return {"message": "Sinyal cozuldu olarak isaretlendi", "signal_id": signal_id}


@router.get("/trends")
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
