"""v2 Opportunity CRUD + Board endpoints — guarded by FEATURE_V2_BOARD flag."""

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
        conditions.append(Opportunity.title.ilike(f"%{q}%"))

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
        raise NotFoundException(f"Firsat bulunamadi: {opp_id}")

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

    # Audit
    await log_action(db, user_id=current_user.id, action="create", entity_type="opportunity", entity_id=opp.id)

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
        raise NotFoundException(f"Firsat bulunamadi: {opp_id}")

    # RBAC: rep can only update own
    if current_user.role == UserRole.SALES_REP.value and opp.owner_id != current_user.id:
        raise ForbiddenException("Bu firsati guncelleme yetkiniz yok")

    old_stage = opp.stage
    updates = body.model_dump(exclude_unset=True)

    for field, value in updates.items():
        if field == "close_date" and value:
            setattr(opp, field, datetime.fromisoformat(value).date())
        else:
            setattr(opp, field, value)

    # Stage change event
    if "stage" in updates and updates["stage"] != old_stage:
        db.add(OpportunityEvent(
            opportunity_id=opp.id,
            event_type="stage_change",
            description=f"Asamadan gecis: {old_stage} -> {updates['stage']}",
        ))

    await db.flush()
    await db.refresh(opp)

    await log_action(db, user_id=current_user.id, action="update", entity_type="opportunity", entity_id=opp.id)

    return _opp_to_dict(opp)


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
        raise NotFoundException(f"Firsat bulunamadi: {opp_id}")
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
        conditions.append(Opportunity.title.ilike(f"%{q}%"))

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
