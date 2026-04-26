"""Activity Capture API — manual call/meeting/note logging + metrics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.activity_log import ActivityLog
from app.models.opportunity import OpportunityEvent
from app.models.user import User

router = APIRouter(prefix="/activities", tags=["Activities"])


# ── Pydantic Schemas ──

class ActivityCreate(BaseModel):
    activity_type: str = Field(min_length=1, max_length=30)
    entity_type: str | None = None
    entity_id: int | None = None
    opportunity_id: int | None = None
    customer_id: int | None = None
    summary: str = Field(min_length=1, max_length=500)
    duration_minutes: int | None = None
    outcome: str | None = None
    attendees_json: str | None = None
    agenda: str | None = None


# ── POST /activities/ ──

@router.post("/")
async def log_activity(
    payload: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Log a manual activity (call, meeting, or note)."""
    activity = ActivityLog(
        activity_type=payload.activity_type,
        entity_type=payload.entity_type or payload.activity_type,
        entity_id=payload.entity_id or 0,
        opportunity_id=payload.opportunity_id,
        customer_id=payload.customer_id,
        user_id=current_user.id,
        summary=payload.summary,
        duration_minutes=payload.duration_minutes,
        outcome=payload.outcome,
        attendees_json=payload.attendees_json,
        agenda=payload.agenda,
    )
    db.add(activity)

    if payload.opportunity_id:
        opp_event = OpportunityEvent(
            opportunity_id=payload.opportunity_id,
            event_type=payload.activity_type,
            entity_type="activity",
            entity_id=0,
            description=payload.summary,
        )
        db.add(opp_event)

    await db.commit()
    await db.refresh(activity)

    if payload.opportunity_id and opp_event:
        opp_event.entity_id = activity.id
        await db.commit()

    return {"data": _serialize_activity(activity)}


# ── GET /activities/ ──

@router.get("/")
async def list_activities(
    entity_type: str | None = None,
    entity_id: int | None = None,
    opportunity_id: int | None = None,
    customer_id: int | None = None,
    user_id: int | None = None,
    activity_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """List activities with optional filters and pagination."""
    stmt = select(ActivityLog).order_by(ActivityLog.created_at.desc())

    if entity_type:
        stmt = stmt.where(ActivityLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(ActivityLog.entity_id == entity_id)
    if opportunity_id is not None:
        stmt = stmt.where(ActivityLog.opportunity_id == opportunity_id)
    if customer_id is not None:
        stmt = stmt.where(ActivityLog.customer_id == customer_id)
    if user_id is not None:
        stmt = stmt.where(ActivityLog.user_id == user_id)
    if activity_type:
        stmt = stmt.where(ActivityLog.activity_type == activity_type)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    rows = (await db.execute(stmt.offset(offset).limit(page_size))).scalars().all()

    return {
        "items": [_serialize_activity(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


# ── GET /activities/metrics ──

@router.get("/metrics")
async def activity_metrics(
    window: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Per-rep daily activity averages over the given window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    stmt = (
        select(
            ActivityLog.user_id,
            ActivityLog.activity_type,
            func.count().label("cnt"),
        )
        .where(ActivityLog.created_at >= cutoff)
        .where(ActivityLog.user_id.isnot(None))
        .group_by(ActivityLog.user_id, ActivityLog.activity_type)
    )

    rows = (await db.execute(stmt)).all()

    user_ids = {r.user_id for r in rows}
    users_map: dict[int, str] = {}
    if user_ids:
        user_rows = (
            await db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))
        ).all()
        users_map = {r.id: r.full_name for r in user_rows}

    agg: dict[int, dict[str, int]] = {}
    for r in rows:
        uid = r.user_id
        if uid not in agg:
            agg[uid] = {}
        agg[uid][r.activity_type] = r.cnt

    result = []
    for uid, counts in agg.items():
        result.append({
            "user_id": uid,
            "user_name": users_map.get(uid, ""),
            "calls_per_day": round(counts.get("call", 0) / window, 2),
            "meetings_per_day": round(counts.get("meeting", 0) / window, 2),
            "emails_per_day": round(counts.get("email", 0) / window, 2),
            "notes_per_day": round(counts.get("note", 0) / window, 2),
        })

    return {"data": result}


# ── GET /activities/feed ──

@router.get("/feed")
async def get_activity_feed(
    since: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Return recent activities across all entities for the dashboard feed.

    `source_ref` is excluded from the SELECT list via ``defer()`` because
    it's an INSERT-side dedupe key with no read path in the feed
    serializer — and a partially-applied migration once left this column
    missing on production, which crashed the entire feed endpoint
    (Sentry HONEYWELL-BACKEND-2/7/8/9). Skipping it from the default
    column list keeps the feed healthy regardless of schema drift, and
    it can still be loaded explicitly in code paths that need it.
    """
    query = (
        select(ActivityLog)
        .options(defer(ActivityLog.source_ref))
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
    )
    if since:
        since_dt = datetime.fromisoformat(since)
        query = query.where(ActivityLog.created_at > since_dt)

    result = await db.execute(query)
    activities = result.scalars().all()

    return [_serialize_activity(a) for a in activities]


# ── Helpers ──

def _serialize_activity(a: ActivityLog) -> dict:
    return {
        "id": a.id,
        "activity_type": a.activity_type,
        "entity_type": a.entity_type,
        "entity_id": a.entity_id,
        "opportunity_id": a.opportunity_id,
        "customer_id": a.customer_id,
        "user_id": a.user_id,
        "summary": a.summary,
        "duration_minutes": a.duration_minutes,
        "outcome": a.outcome,
        "attendees_json": a.attendees_json,
        "agenda": a.agenda,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
