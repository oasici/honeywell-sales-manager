"""v2 Opportunity CRUD + Board endpoints — guarded by FEATURE_V2_BOARD flag."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.enums import OpportunityStage, UserRole
from app.models.opportunity import Opportunity, OpportunityEvent
from app.models.quote import Quote
from app.models.user import User
from app.core.event_bus import event_bus
from app.services.activity_logger import log_activity
from app.services.audit_service import log_action

router = APIRouter(tags=["Opportunities (v2)"])


def _require_v2_board():
    """Dependency: reject if FEATURE_V2_BOARD is off."""
    if not settings.FEATURE_V2_BOARD:
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic schemas ──

class OpportunityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    stage: str = "prospecting"
    amount: float | None = None
    currency: str = "TRY"
    close_date: str | None = None  # ISO date string
    customer_id: int | None = None

class OpportunityUpdate(BaseModel):
    title: str | None = None
    stage: str | None = None
    amount: float | None = None
    currency: str | None = None
    close_date: str | None = None
    customer_id: int | None = None
    status: str | None = None
    loss_reason: str | None = None


# ── Stage probability mapping ──

STAGE_PROBABILITY = {
    "prospecting": 0.10,
    "qualified": 0.25,
    "proposal": 0.50,
    "negotiation": 0.75,
    "closed_won": 1.0,
    "closed_lost": 0.0,
}


# ── Helpers ──

def _opp_to_dict(opp: Opportunity, include_quotes: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    updated = opp.updated_at
    if updated and updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    rotting_days = (now - updated).days if updated else 0

    data = {
        "id": opp.id,
        "title": opp.title,
        "stage": opp.stage,
        "amount": opp.amount,
        "currency": opp.currency,
        "close_date": str(opp.close_date) if opp.close_date else None,
        "owner_id": opp.owner_id,
        "customer_id": opp.customer_id,
        "status": opp.status,
        "probability": getattr(opp, "probability", 0.0),
        "loss_reason": getattr(opp, "loss_reason", None),
        "rotting_days": rotting_days,
        "customer": {
            "id": opp.customer.id,
            "name": opp.customer.name,
            "company": opp.customer.company,
        } if opp.customer else None,
        "owner": {
            "id": opp.owner.id,
            "full_name": opp.owner.full_name,
        } if opp.owner else None,
        "created_at": opp.created_at.isoformat() if opp.created_at else None,
        "updated_at": opp.updated_at.isoformat() if opp.updated_at else None,
    }

    if include_quotes and hasattr(opp, "quotes") and opp.quotes:
        data["quotes"] = [
            {"id": q.id, "quote_number": q.quote_number, "status": q.status, "grand_total": q.grand_total}
            for q in opp.quotes
        ]
    else:
        data["quotes"] = []

    return data


# ══════════════════════════════════════════
# OPPORTUNITY CRUD
# ══════════════════════════════════════════

@router.get("/opportunities/")
async def list_opportunities(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    stage: str | None = None,
    owner_id: int | None = None,
    status: str | None = Query("active"),
    q: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    """List opportunities with pagination, filtering, and ownership scoping."""
    query = select(Opportunity)
    count_query = select(func.count(Opportunity.id))

    conditions = []

    # RBAC scoping
    if current_user.role == UserRole.SALES_REP.value:
        conditions.append(Opportunity.owner_id == current_user.id)
    elif owner_id is not None:
        conditions.append(Opportunity.owner_id == owner_id)

    if stage:
        conditions.append(Opportunity.stage == stage)
    if status:
        conditions.append(Opportunity.status == status)
    if q:
        safe_q = q.replace("%", "\\%").replace("_", "\\_")
        conditions.append(Opportunity.title.ilike(f"%{safe_q}%"))

    if conditions:
        combined = and_(*conditions)
        query = query.where(combined)
        count_query = count_query.where(combined)

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    query = query.order_by(Opportunity.updated_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    opps = result.scalars().unique().all()

    return {
        "items": [_opp_to_dict(o) for o in opps],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


# ══════════════════════════════════════════
# PIPELINE INSPECTION (before /{opp_id} to avoid path conflict)
# ══════════════════════════════════════════

STALE_THRESHOLD_DAYS = 7


@router.get("/opportunities/pipeline-inspection")
async def pipeline_inspection(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    """Pipeline inspection: by stage with health scores, stale count, coverage."""
    from app.services.deal_health_service import DealHealthService

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=STALE_THRESHOLD_DAYS)

    # RBAC scoping
    owner_filter = []
    if current_user.role == UserRole.SALES_REP.value:
        owner_filter.append(Opportunity.owner_id == current_user.id)

    active_filter = [Opportunity.status == "active"]
    base_conditions = active_filter + owner_filter

    # Get deal health scores in batch
    health_owner_id = (
        current_user.id if current_user.role == UserRole.SALES_REP.value else None
    )
    health_service = DealHealthService(db)
    health_reports = await health_service.get_all_deal_health(owner_id=health_owner_id)
    health_map = {r.opportunity_id: r.score for r in health_reports}

    stages_data = []
    pipeline_total = 0.0
    weighted_forecast = 0.0

    for stage_name in KANBAN_STAGES:
        stage_conds = base_conditions + [Opportunity.stage == stage_name]
        combined = and_(*stage_conds)

        count = (
            await db.execute(
                select(func.count(Opportunity.id)).where(combined)
            )
        ).scalar() or 0

        total_amount = (
            await db.execute(
                select(func.coalesce(func.sum(Opportunity.amount), 0.0)).where(combined)
            )
        ).scalar() or 0

        stale_count = (
            await db.execute(
                select(func.count(Opportunity.id)).where(
                    combined, Opportunity.updated_at < stale_cutoff,
                )
            )
        ).scalar() or 0

        # Avg health score for this stage
        stage_opp_ids_q = await db.execute(
            select(Opportunity.id).where(combined)
        )
        stage_opp_ids = [row[0] for row in stage_opp_ids_q.all()]
        stage_health_scores = [
            health_map[oid] for oid in stage_opp_ids if oid in health_map
        ]
        avg_health = (
            round(sum(stage_health_scores) / len(stage_health_scores), 1)
            if stage_health_scores
            else 0.0
        )

        amount_float = round(float(total_amount), 2)
        pipeline_total += amount_float

        # Weighted forecast: amount * stage probability
        prob = STAGE_PROBABILITY.get(stage_name, 0.0)
        weighted_forecast += amount_float * prob

        stages_data.append({
            "stage": stage_name,
            "count": count,
            "total_amount": amount_float,
            "avg_health_score": avg_health,
            "stale_count": stale_count,
        })

    # Coverage ratio: pipeline / weighted_forecast (or quota placeholder)
    coverage_ratio = (
        round(pipeline_total / weighted_forecast, 2) if weighted_forecast > 0 else 0.0
    )

    return {
        "stages": stages_data,
        "pipeline_total": round(pipeline_total, 2),
        "weighted_forecast": round(weighted_forecast, 2),
        "coverage_ratio": coverage_ratio,
    }


@router.get("/opportunities/{opp_id}")
async def get_opportunity(
    opp_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    """Get opportunity detail with quotes and computed fields."""
    result = await db.execute(
        select(Opportunity)
        .options(selectinload(Opportunity.quotes))
        .where(Opportunity.id == opp_id)
    )
    opp = result.scalar_one_or_none()
    if not opp:
        raise NotFoundException("Firsat bulunamadi")

    # RBAC
    if current_user.role == UserRole.SALES_REP.value and opp.owner_id != current_user.id:
        raise ForbiddenException("Bu firsata erisim yetkiniz yok")

    data = _opp_to_dict(opp, include_quotes=True)

    # Computed: open_quotes_count
    open_q = await db.execute(
        select(func.count(Quote.id)).where(
            Quote.opportunity_id == opp_id,
            Quote.status.notin_(["expired", "rejected"]),
        )
    )
    data["open_quotes_count"] = open_q.scalar() or 0

    return data


@router.get("/opportunities/{opp_id}/stage-requirements")
async def get_stage_requirements(
    opp_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    """Return per-stage completion status for the sales path / guided selling bar."""
    result = await db.execute(select(Opportunity).where(Opportunity.id == opp_id))
    opp = result.scalar_one_or_none()
    if not opp:
        raise NotFoundException("Firsat bulunamadi")

    if current_user.role == UserRole.SALES_REP.value and opp.owner_id != current_user.id:
        raise ForbiddenException("Bu firsata erisim yetkiniz yok")

    from app.services.stage_validation_service import get_all_stage_status

    stages = await get_all_stage_status(db, opp)
    return {"data": stages}


@router.post("/opportunities/", status_code=201)
async def create_opportunity(
    body: OpportunityCreate,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    """Create a new opportunity."""
    opp = Opportunity(
        title=body.title,
        stage=body.stage,
        amount=body.amount,
        currency=body.currency,
        close_date=datetime.fromisoformat(body.close_date).date() if body.close_date else None,
        customer_id=body.customer_id,
        owner_id=current_user.id,
    )
    db.add(opp)
    await db.flush()
    await db.refresh(opp)

    # Timeline event
    db.add(OpportunityEvent(
        opportunity_id=opp.id,
        event_type="stage_change",
        description=f"Firsat olusturuldu: {body.stage}",
    ))

    # Activity + Audit + Event
    await log_activity(
        db, activity_type="stage_change", entity_type="opportunity", entity_id=opp.id,
        opportunity_id=opp.id, customer_id=body.customer_id, user_id=current_user.id,
        summary=f"Firsat olusturuldu: {body.title}",
    )
    await log_action(db, user_id=current_user.id, action="create", entity_type="opportunity", entity_id=opp.id)
    await event_bus.publish("opportunity.created", {
        "opportunity_id": opp.id, "title": body.title, "stage": body.stage,
        "amount": body.amount, "owner_id": current_user.id,
    })

    return _opp_to_dict(opp)


@router.patch("/opportunities/{opp_id}")
async def update_opportunity(
    opp_id: int,
    body: OpportunityUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    """Update opportunity fields. Stage changes create timeline events."""
    result = await db.execute(select(Opportunity).where(Opportunity.id == opp_id))
    opp = result.scalar_one_or_none()
    if not opp:
        raise NotFoundException("Firsat bulunamadi")

    # RBAC: rep can only update own
    if current_user.role == UserRole.SALES_REP.value and opp.owner_id != current_user.id:
        raise ForbiddenException("Bu firsati guncelleme yetkiniz yok")

    old_stage = opp.stage
    updates = body.model_dump(exclude_unset=True)

    # Track previous values for revenue leak detection
    if "stage" in updates and updates["stage"] != opp.stage:
        opp.previous_stage = opp.stage
    if "close_date" in updates and updates.get("close_date") != str(opp.close_date):
        opp.previous_close_date = opp.close_date
    if "amount" in updates and updates.get("amount") != opp.amount:
        opp.previous_amount = opp.amount

    # Stage validation (guided selling) — warn but don't block
    stage_warnings: dict | None = None
    if "stage" in updates and updates["stage"] != old_stage:
        if settings.FEATURE_GUIDED_SELLING:
            from app.services.stage_validation_service import validate_stage_transition

            validation = await validate_stage_transition(db, opp, updates["stage"])
            if not validation["valid"]:
                stage_warnings = {
                    "errors": validation["errors"],
                    "tips": validation["tips"],
                }

    for field, value in updates.items():
        if field == "close_date" and value:
            setattr(opp, field, datetime.fromisoformat(value).date())
        else:
            setattr(opp, field, value)

    # Auto-set probability on stage change
    if "stage" in updates and updates["stage"] != old_stage:
        new_probability = STAGE_PROBABILITY.get(updates["stage"])
        if new_probability is not None:
            opp.probability = new_probability

    # Stage change event
    if "stage" in updates and updates["stage"] != old_stage:
        db.add(OpportunityEvent(
            opportunity_id=opp.id,
            event_type="stage_change",
            description=f"Asamadan gecis: {old_stage} -> {updates['stage']}",
        ))

    await db.flush()
    await db.refresh(opp)

    # Activity logging + event for stage changes
    if "stage" in updates and updates["stage"] != old_stage:
        await log_activity(
            db, activity_type="stage_change", entity_type="opportunity", entity_id=opp.id,
            opportunity_id=opp.id, customer_id=opp.customer_id, user_id=current_user.id,
            summary=f"Asamadan gecis: {old_stage} -> {updates['stage']}",
        )
        await event_bus.publish("opportunity.stage_changed", {
            "opportunity_id": opp.id, "old_stage": old_stage,
            "new_stage": updates["stage"], "owner_id": current_user.id,
        })

    await log_action(db, user_id=current_user.id, action="update", entity_type="opportunity", entity_id=opp.id)

    response = _opp_to_dict(opp)
    if stage_warnings:
        response["stage_warnings"] = stage_warnings
    return response


@router.post("/opportunities/bulk-action")
async def bulk_action_opportunities(
    body: dict,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    """Bulk actions on opportunities: change_stage, assign, mark_won, mark_lost, delete, export."""
    ids = body.get("ids", [])
    action = body.get("action", "")
    params = body.get("params", {})

    if not ids or not isinstance(ids, list):
        raise BadRequestException("Gecerli bir ID listesi saglanmalidir")
    if not action:
        raise BadRequestException("Islem tipi belirtilmelidir")

    # Validate that all IDs exist
    result = await db.execute(
        select(Opportunity).where(Opportunity.id.in_(ids))
    )
    opps = result.scalars().all()
    found_ids = {o.id for o in opps}
    missing_ids = [i for i in ids if i not in found_ids]
    if missing_ids:
        raise NotFoundException(f"Bulunamayan firsat ID'leri: {missing_ids}")

    if action == "change_stage":
        new_stage = params.get("stage")
        if not new_stage:
            raise BadRequestException("Yeni asama belirtilmelidir")
        for opp in opps:
            opp.stage = new_stage
            new_prob = STAGE_PROBABILITY.get(new_stage)
            if new_prob is not None:
                opp.probability = new_prob
        await db.flush()
        return {"message": f"{len(opps)} firsat asamasi guncellendi", "affected_count": len(opps)}

    if action == "assign":
        new_owner_id = params.get("owner_id")
        if not new_owner_id:
            raise BadRequestException("Atanacak kullanici ID'si (owner_id) belirtilmelidir")
        for opp in opps:
            opp.owner_id = new_owner_id
        await db.flush()
        return {"message": f"{len(opps)} firsat atandi", "affected_count": len(opps)}

    if action == "mark_won":
        for opp in opps:
            opp.stage = "closed_won"
            opp.status = "closed"
            opp.probability = STAGE_PROBABILITY.get("closed_won", 1.0)
        await db.flush()
        return {"message": f"{len(opps)} firsat kazanildi olarak isaretlendi", "affected_count": len(opps)}

    if action == "mark_lost":
        loss_reason = params.get("loss_reason", "")
        for opp in opps:
            opp.stage = "closed_lost"
            opp.status = "closed"
            opp.probability = STAGE_PROBABILITY.get("closed_lost", 0.0)
            if loss_reason:
                opp.loss_reason = loss_reason
        await db.flush()
        return {"message": f"{len(opps)} firsat kaybedildi olarak isaretlendi", "affected_count": len(opps)}

    if action == "delete":
        if current_user.role != UserRole.SALES_MANAGER.value:
            raise BadRequestException("Silme islemi yalnizca yonetici tarafindan yapilabilir")
        for opp in opps:
            await db.delete(opp)
        await db.flush()
        return {"message": f"{len(opps)} firsat silindi", "affected_count": len(opps)}

    if action == "export":
        rows = [_opp_to_dict(o) for o in opps]
        return {"message": f"{len(rows)} firsat disa aktarildi", "affected_count": len(rows), "data": rows}

    raise BadRequestException(f"Bilinmeyen islem: {action}")


# ══════════════════════════════════════════
# OPPORTUNITY TIMELINE
# ══════════════════════════════════════════

@router.get("/opportunities/{opp_id}/timeline")
async def get_opportunity_timeline(
    opp_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    """Get chronological timeline events for an opportunity."""
    # Verify exists + RBAC
    opp = (await db.execute(select(Opportunity).where(Opportunity.id == opp_id))).scalar_one_or_none()
    if not opp:
        raise NotFoundException("Firsat bulunamadi")
    if current_user.role == UserRole.SALES_REP.value and opp.owner_id != current_user.id:
        raise ForbiddenException("Bu firsata erisim yetkiniz yok")

    events_q = await db.execute(
        select(OpportunityEvent)
        .where(OpportunityEvent.opportunity_id == opp_id)
        .order_by(OpportunityEvent.occurred_at.desc())
        .limit(limit)
    )
    events = events_q.scalars().all()

    return {
        "opportunity_id": opp_id,
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "description": e.description,
                "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
            }
            for e in events
        ],
    }


# ══════════════════════════════════════════
# BOARD (KANBAN)
# ══════════════════════════════════════════

KANBAN_STAGES = [s.value for s in OpportunityStage]


@router.get("/board/kanban")
async def get_board_kanban(
    owner_id: int | None = None,
    stages: str | None = None,
    q: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    """Kanban board: opportunities grouped by stage columns."""
    requested_stages = stages.split(",") if stages else KANBAN_STAGES

    conditions = [Opportunity.status == "active"]

    # RBAC scoping
    if current_user.role == UserRole.SALES_REP.value:
        conditions.append(Opportunity.owner_id == current_user.id)
    elif owner_id is not None:
        conditions.append(Opportunity.owner_id == owner_id)

    if q:
        safe_q = q.replace("%", "\\%").replace("_", "\\_")
        conditions.append(Opportunity.title.ilike(f"%{safe_q}%"))

    columns = []
    for stage in requested_stages:
        stage_conds = conditions + [Opportunity.stage == stage]
        combined = and_(*stage_conds)

        count = (await db.execute(select(func.count(Opportunity.id)).where(combined))).scalar() or 0
        total_amount = (await db.execute(
            select(func.coalesce(func.sum(Opportunity.amount), 0.0)).where(combined)
        )).scalar() or 0

        items_q = await db.execute(
            select(Opportunity).where(combined).order_by(Opportunity.updated_at.desc()).limit(50)
        )
        items = items_q.scalars().unique().all()

        columns.append({
            "stage": stage,
            "count": count,
            "total_amount": round(float(total_amount), 2),
            "items": [_opp_to_dict(o) for o in items],
        })

    return {"columns": columns}


# ══════════════════════════════════════════
# ACTIVITY SUMMARY (Modul 6)
# ══════════════════════════════════════════

@router.get("/opportunities/{opp_id}/activity-summary")
async def get_activity_summary(
    opp_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    """Per-deal activity summary: counts by type, last activity, stage comparison."""
    from app.models.activity_log import ActivityLog

    # Verify exists + RBAC
    opp = (await db.execute(select(Opportunity).where(Opportunity.id == opp_id))).scalar_one_or_none()
    if not opp:
        raise NotFoundException("Firsat bulunamadi")
    if current_user.role == UserRole.SALES_REP.value and opp.owner_id != current_user.id:
        raise ForbiddenException("Bu firsata erisim yetkiniz yok")

    # Total activities for this opportunity
    total_activities = (await db.execute(
        select(func.count(ActivityLog.id)).where(ActivityLog.opportunity_id == opp_id)
    )).scalar() or 0

    # By type breakdown
    type_counts_q = await db.execute(
        select(ActivityLog.activity_type, func.count(ActivityLog.id).label("cnt"))
        .where(ActivityLog.opportunity_id == opp_id)
        .group_by(ActivityLog.activity_type)
    )
    by_type: dict[str, int] = {}
    activity_type_mapping = {
        "call": "call",
        "meeting": "meeting",
        "note_added": "note",
        "email_received": "email",
        "email_parsed": "email",
        "quote_created": "quote",
        "quote_approved": "quote",
        "quote_sent": "email",
        "stage_change": "stage_change",
        "task_created": "task",
        "task_completed": "task",
        "transcript_uploaded": "meeting",
    }
    for row in type_counts_q.all():
        mapped = activity_type_mapping.get(row.activity_type, row.activity_type)
        by_type[mapped] = by_type.get(mapped, 0) + row.cnt

    # Last activity timestamp
    last_activity_q = await db.execute(
        select(func.max(ActivityLog.created_at)).where(ActivityLog.opportunity_id == opp_id)
    )
    last_activity_at = last_activity_q.scalar()

    now = datetime.now(timezone.utc)
    days_since_last = 0
    if last_activity_at:
        if last_activity_at.tzinfo is None:
            last_activity_at = last_activity_at.replace(tzinfo=timezone.utc)
        days_since_last = (now - last_activity_at).days

    # Average activities for same stage (compare across all opps in this stage)
    avg_for_stage_q = await db.execute(
        select(func.count(ActivityLog.id).label("cnt"))
        .join(Opportunity, ActivityLog.opportunity_id == Opportunity.id)
        .where(Opportunity.stage == opp.stage, Opportunity.status == "active")
        .group_by(ActivityLog.opportunity_id)
    )
    stage_counts = [row.cnt for row in avg_for_stage_q.all()]
    avg_activities_for_stage = (
        round(sum(stage_counts) / len(stage_counts), 1) if stage_counts else 0.0
    )

    return {
        "opportunity_id": opp_id,
        "total_activities": total_activities,
        "by_type": by_type,
        "last_activity_at": last_activity_at.isoformat() if last_activity_at else None,
        "days_since_last_activity": days_since_last,
        "avg_activities_for_stage": avg_activities_for_stage,
    }


@router.get("/board/summary")
async def get_board_summary(
    window: int = Query(30, ge=7, le=365),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    """Board KPIs: coverage, forecast, rotting count, win-rate."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window)

    # Open pipeline
    open_total = (await db.execute(
        select(func.coalesce(func.sum(Opportunity.amount), 0.0)).where(
            Opportunity.status == "active"
        )
    )).scalar() or 0

    # Won in window
    won_count = (await db.execute(
        select(func.count(Opportunity.id)).where(
            and_(Opportunity.stage == "closed_won", Opportunity.updated_at >= cutoff)
        )
    )).scalar() or 0
    total_closed = (await db.execute(
        select(func.count(Opportunity.id)).where(
            and_(Opportunity.stage.in_(["closed_won", "closed_lost"]), Opportunity.updated_at >= cutoff)
        )
    )).scalar() or 0
    win_rate = round(won_count / total_closed * 100, 1) if total_closed > 0 else 0

    # Rotting (no update > 7 days)
    rotting_threshold = now - timedelta(days=7)
    rotting_count = (await db.execute(
        select(func.count(Opportunity.id)).where(
            and_(Opportunity.status == "active", Opportunity.updated_at < rotting_threshold)
        )
    )).scalar() or 0

    return {
        "window_days": window,
        "open_pipeline_total": round(float(open_total), 2),
        "won_count": won_count,
        "win_rate": win_rate,
        "rotting_count": rotting_count,
    }
