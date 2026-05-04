"""v2 Opportunity CRUD + Board endpoints — guarded by FEATURE_V2_BOARD flag."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Integer, String, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.enums import OpportunityStage, UserRole
from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal, Task
from app.models.quote import Quote
from app.models.user import User
from app.core.event_bus import event_bus
from app.services.activity_logger import log_activity
from app.services.audit_service import log_action
from app.services.tenant_context import assert_same_tenant, scoped_for_user

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


# ── Stage probability mapping (centralized) ──

async def _stage_probability(db: AsyncSession, stage: str) -> float:
    from app.services.stage_probability_service import get_stage_probability

    return await get_stage_probability(db, stage)


# ── Helpers ──

def _opportunity_staleness_days(opp: Opportunity, last_activity_at: datetime | None) -> int:
    """Days since last ActivityLog on this deal, else since updated_at (aligned with /board/*)."""
    ref_dt = last_activity_at or opp.updated_at
    if ref_dt is None:
        return 0
    now = datetime.now(timezone.utc)
    ref = ref_dt
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return max(0, (now - ref).days)


def _board_staleness_timestamp():
    """SQL: last ActivityLog time for the opportunity, else Opportunity.updated_at."""
    from app.models.activity_log import ActivityLog

    last_activity_scalar = (
        select(func.max(ActivityLog.created_at))
        .where(ActivityLog.opportunity_id == Opportunity.id)
        .scalar_subquery()
    )
    return func.coalesce(last_activity_scalar, Opportunity.updated_at)


async def _last_activity_max_by_opportunity_ids(
    db: AsyncSession, opp_ids: list[int],
) -> dict[int, datetime | None]:
    if not opp_ids:
        return {}
    from app.models.activity_log import ActivityLog

    rows = (
        await db.execute(
            select(ActivityLog.opportunity_id, func.max(ActivityLog.created_at))
            .where(ActivityLog.opportunity_id.in_(opp_ids))
            .group_by(ActivityLog.opportunity_id)
        )
    ).all()
    return {int(r[0]): r[1] for r in rows}


def _opp_to_dict(
    opp: Opportunity,
    include_quotes: bool = False,
    last_activity_at: datetime | None = None,
) -> dict:
    rotting_days = _opportunity_staleness_days(opp, last_activity_at)

    data = {
        "id": opp.id,
        # tenant_id round-trips so the frontend can verify isolation and
        # analytics layers can group without a re-query (round-4 R4-DTO-1).
        "tenant_id": getattr(opp, "tenant_id", None),
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
        # Forecast classification + segmentation FKs that the model
        # carries but the serializer used to drop. The board view
        # filters by these and the forecast page shows category
        # rollups, so they need to round-trip cleanly.
        "forecast_category": getattr(opp, "forecast_category", None),
        "pipeline_id": getattr(opp, "pipeline_id", None),
        "territory_id": getattr(opp, "territory_id", None),
        # Revenue-leak tracking — the previous_* columns store the
        # prior values whenever stage/close_date/amount change. We
        # surface them so closed-lost detail pages can render a
        # "this deal slipped from X → Y" diff.
        "previous_stage": getattr(opp, "previous_stage", None),
        "previous_close_date": (
            str(opp.previous_close_date) if getattr(opp, "previous_close_date", None) else None
        ),
        "previous_amount": getattr(opp, "previous_amount", None),
        # Lead-source attribution — column existed since the V2
        # foundation migration but was unmapped on the model until
        # audit DB-6 (v1.8.0). Surfacing now so the funnel report
        # can group conversions by source.
        "source": getattr(opp, "source", None),
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

    # Field-level masking (R4-PERM-1).
    from app.services.field_permission_service import apply_request_perms
    return apply_request_perms(data, "opportunity")


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

    # V12 multi-tenant: no-op when current_user.tenant_id is None.
    query = scoped_for_user(query, current_user, column=Opportunity.tenant_id)
    count_query = scoped_for_user(
        count_query, current_user, column=Opportunity.tenant_id
    )

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    query = query.order_by(Opportunity.updated_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    opps = result.scalars().unique().all()

    opp_ids = [int(o.id) for o in opps]
    last_by_opp = await _last_activity_max_by_opportunity_ids(db, opp_ids)

    return {
        "items": [
            _opp_to_dict(o, last_activity_at=last_by_opp.get(int(o.id)))
            for o in opps
        ],
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

        staleness_ts = _board_staleness_timestamp()
        stale_count = (
            await db.execute(
                select(func.count(Opportunity.id)).where(
                    combined,
                    staleness_ts < stale_cutoff,
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
        prob = await _stage_probability(db, stage_name)
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

    # V12 multi-tenant guard — cross-tenant lookups should look like
    # a 404 so callers cannot enumerate IDs across tenants.
    assert_same_tenant(opp, current_user, exception_cls=NotFoundException)

    # RBAC
    if current_user.role == UserRole.SALES_REP.value and opp.owner_id != current_user.id:
        raise ForbiddenException("Bu firsata erisim yetkiniz yok")

    last_by_opp = await _last_activity_max_by_opportunity_ids(db, [int(opp.id)])
    data = _opp_to_dict(
        opp,
        include_quotes=True,
        last_activity_at=last_by_opp.get(int(opp.id)),
    )

    # Computed: open_quotes_count
    open_q = await db.execute(
        select(func.count(Quote.id)).where(
            Quote.opportunity_id == opp_id,
            Quote.status.notin_(["expired", "rejected"]),
        )
    )
    data["open_quotes_count"] = open_q.scalar() or 0

    return data


@router.get("/opportunities/{opp_id}/intelligence")
async def get_opportunity_intelligence(
    opp_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    """Unified intelligence payload for Opportunity Detail + Board (Sprint 1)."""
    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opp_id))
    ).scalar_one_or_none()
    if not opp:
        raise NotFoundException("Firsat bulunamadi")
    assert_same_tenant(opp, current_user, exception_cls=NotFoundException)
    if current_user.role == UserRole.SALES_REP.value and opp.owner_id != current_user.id:
        raise ForbiddenException("Bu firsata erisim yetkiniz yok")

    # Deal health (rule-based)
    from app.services.deal_health_service import DealHealthService

    health_service = DealHealthService(db)
    health = await health_service.compute_deal_health(opp_id)

    # Predictive close probability (heuristic v1.5)
    from app.services.predictive_scoring_service import predict_close_probability

    probability = await predict_close_probability(db, opp_id)

    # Signals (opportunity_signals)
    signals = (
        await db.execute(
            select(OpportunitySignal)
            .where(OpportunitySignal.opportunity_id == opp_id)
            .order_by(OpportunitySignal.created_at.desc())
            .limit(50)
        )
    ).scalars().all()

    # Tasks (open first)
    tasks = (
        await db.execute(
            select(Task)
            .where(Task.opportunity_id == opp_id)
            .order_by(
                (Task.status == "open").desc(),
                Task.due_at.asc().nullslast(),
                Task.created_at.desc(),
            )
            .limit(50)
        )
    ).scalars().all()

    open_tasks_count = sum(1 for t in tasks if t.status == "open")

    last_by_opp = await _last_activity_max_by_opportunity_ids(db, [int(opp.id)])

    return {
        "opportunity": _opp_to_dict(
            opp,
            include_quotes=True,
            last_activity_at=last_by_opp.get(int(opp.id)),
        ),
        "health": {
            "opportunity_id": health.opportunity_id,
            "score": health.score,
            "risk_level": health.risk_level,
            "indicators": [
                {
                    "name": i.name,
                    "label": i.label,
                    "score": i.score,
                    "weight": i.weight,
                    "raw_value": i.raw_value,
                    "description": i.description,
                }
                for i in (health.indicators or [])
            ],
            "recommendations": health.recommendations,
        } if health else None,
        "probability": probability,
        "signals": [
            {
                "id": s.id,
                "signal_type": s.signal_type,
                "severity": s.severity,
                "evidence": s.evidence,
                "source_type": s.source_type,
                "source_id": s.source_id,
                "is_resolved": s.is_resolved,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in signals
        ],
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "status": t.status,
                "source": t.source,
                "priority": t.priority,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ],
        "open_tasks_count": open_tasks_count,
    }


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
        # V12 multi-tenant: inherit caller's tenant. NULL on
        # single-tenant deployments — schema accepts NULL.
        tenant_id=getattr(current_user, "tenant_id", None),
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

    last_by_opp = await _last_activity_max_by_opportunity_ids(db, [int(opp.id)])
    return _opp_to_dict(opp, last_activity_at=last_by_opp.get(int(opp.id)))


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
    assert_same_tenant(opp, current_user, exception_cls=NotFoundException)

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
    old_probability = opp.probability
    if "stage" in updates and updates["stage"] != old_stage:
        opp.probability = await _stage_probability(db, updates["stage"])

    # Emit opportunity.score_changed when probability moves (audit
    # EVT-2). The constant + payload schema were defined but no
    # publisher existed; downstream subscribers (workflow rules,
    # forecasts) silently saw nothing.
    if opp.probability != old_probability:
        try:
            from app.services.domain_events import (
                DomainEvents,
                emit_domain_event,
            )

            await emit_domain_event(
                db,
                DomainEvents.OPP_SCORE_CHANGED,
                {
                    "opportunity_id": opp.id,
                    "old_score": old_probability,
                    "new_score": opp.probability,
                    "reason": "stage_change" if "stage" in updates else "manual_update",
                },
                entity_type="opportunity",
                entity_id=opp.id,
                actor_id=current_user.id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("emit opportunity.score_changed failed: %s", exc)

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
        # V11 RAG hook: index closed deals into the deals collection
        # so retrieve-then-generate has fresh context. Best-effort —
        # never blocks the stage-change flow.
        if updates["stage"] in {"closed_won", "closed_lost"}:
            try:
                from app.services.rag_backfill_service import index_opportunity_close

                await index_opportunity_close(int(opp.id))
            except Exception as exc:
                logger.debug("RAG index_opportunity_close skip: %s", exc)

    await log_action(db, user_id=current_user.id, action="update", entity_type="opportunity", entity_id=opp.id)

    last_by_opp = await _last_activity_max_by_opportunity_ids(db, [int(opp.id)])
    response = _opp_to_dict(opp, last_activity_at=last_by_opp.get(int(opp.id)))
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

    # Validate that all IDs exist AND belong to the caller's tenant.
    # Without this guard, a sales rep can mutate any tenant's
    # opportunities by guessing IDs (audit TEN-1, 2026-05-01).
    # The v1.6.1 hotfix used the wrong (positional) signature here
    # which raised TypeError at runtime — corrected with explicit
    # column kwarg in v1.7.2.
    result = await db.execute(
        scoped_for_user(
            select(Opportunity), current_user, column=Opportunity.tenant_id,
        ).where(Opportunity.id.in_(ids))
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
            opp.probability = await _stage_probability(db, new_stage)
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
            opp.probability = await _stage_probability(db, "closed_won")
        await db.flush()
        return {"message": f"{len(opps)} firsat kazanildi olarak isaretlendi", "affected_count": len(opps)}

    if action == "mark_lost":
        loss_reason = params.get("loss_reason", "")
        for opp in opps:
            opp.stage = "closed_lost"
            opp.status = "closed"
            opp.probability = await _stage_probability(db, "closed_lost")
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
        exp_ids = [int(o.id) for o in opps]
        last_by_opp = await _last_activity_max_by_opportunity_ids(db, exp_ids)
        rows = [
            _opp_to_dict(o, last_activity_at=last_by_opp.get(int(o.id)))
            for o in opps
        ]
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
    """Get chronological timeline: opportunity_events + linked email_requests (S2)."""
    from app.models.email_request import EmailRequest

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
        .limit(limit * 2),
    )
    events = events_q.scalars().all()

    covered_email_ids: set[int] = set()
    for e in events:
        if e.entity_id is None:
            continue
        et = (e.entity_type or "").lower()
        if et in ("email", "email_request"):
            covered_email_ids.add(int(e.entity_id))

    emails_q = await db.execute(
        select(EmailRequest)
        .where(EmailRequest.opportunity_id == opp_id)
        .order_by(EmailRequest.created_at.desc())
        .limit(limit * 2),
    )
    linked_emails = emails_q.scalars().all()
    linked_email_ids = {int(em.id) for em in linked_emails}

    quote_email_id_rows = (
        await db.execute(
            select(Quote.email_request_id).where(
                Quote.opportunity_id == opp_id,
                Quote.email_request_id.isnot(None),
            )
        )
    ).all()
    quote_email_ids = [int(r[0]) for r in quote_email_id_rows if r[0] is not None]
    quote_emails: list[EmailRequest] = []
    if quote_email_ids:
        qem = await db.execute(select(EmailRequest).where(EmailRequest.id.in_(quote_email_ids)))
        quote_emails = list(qem.scalars().all())

    email_by_id: dict[int, EmailRequest] = {em.id: em for em in linked_emails}
    for em in quote_emails:
        email_by_id.setdefault(em.id, em)

    SYNTH_ID_BASE = 2_000_000_000
    rows: list[dict] = [
        {
            "id": e.id,
            "event_type": e.event_type,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "description": e.description,
            "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
            "synthetic": False,
        }
        for e in events
    ]

    for em in email_by_id.values():
        if em.id in covered_email_ids:
            continue
        ts = em.received_at or em.created_at
        via_quote = em.id not in linked_email_ids and em.id in quote_email_ids
        suffix = " (teklif uzerinden)" if via_quote else ""
        rows.append(
            {
                "id": SYNTH_ID_BASE + int(em.id),
                "event_type": "email",
                "entity_type": "email_request",
                "entity_id": em.id,
                "description": (
                    f"E-posta: {em.subject or '(konu yok)'} — {em.from_address}{suffix}"
                ),
                "occurred_at": ts.isoformat() if ts else None,
                "synthetic": True,
                "via_quote": via_quote,
            }
        )

    rows.sort(key=lambda r: r.get("occurred_at") or "", reverse=True)
    rows = rows[:limit]

    return {"opportunity_id": opp_id, "events": rows}


# ══════════════════════════════════════════
# BOARD (KANBAN)
# ══════════════════════════════════════════

KANBAN_STAGES = [s.value for s in OpportunityStage]


@router.get("/board/kanban")
async def get_board_kanban(
    owner_id: int | None = None,
    stages: str | None = None,
    q: str | None = None,
    customer_id: int | None = None,
    min_rotting_days: int | None = Query(None, ge=0, le=3650),
    min_open_tasks: int | None = Query(None, ge=0, le=500),
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

    if customer_id is not None:
        conditions.append(Opportunity.customer_id == customer_id)

    if q:
        safe_q = q.replace("%", "\\%").replace("_", "\\_")
        conditions.append(Opportunity.title.ilike(f"%{safe_q}%"))

    staleness_ts = _board_staleness_timestamp()

    dialect = db.bind.dialect.name if db.bind is not None else "postgresql"

    if min_rotting_days is not None:
        if dialect == "sqlite":
            # SQLite: avoid mixing func.now() with timezone-aware datetimes (tests use sqlite).
            now_j = func.julianday("now")
            st_txt = cast(staleness_ts, String)
            st_j = case(
                (st_txt.like("%+%"), func.julianday(func.substr(st_txt, 1, 19), "+00:00")),
                (st_txt.like("%Z"), func.julianday(func.substr(st_txt, 1, 19), "+00:00")),
                else_=func.julianday(staleness_ts),
            )
            rotting_days_expr = cast(now_j - st_j, Integer)
        else:
            rotting_days_expr = func.coalesce(
                func.floor(func.extract("epoch", func.now() - staleness_ts) / 86400.0),
                0,
            )
        conditions.append(rotting_days_expr >= min_rotting_days)

    columns = []
    for stage in requested_stages:
        stage_conds = conditions + [Opportunity.stage == stage]
        combined = and_(*stage_conds)

        if min_open_tasks is not None:
            open_tasks_cnt = (
                select(func.count(Task.id))
                .where(Task.opportunity_id == Opportunity.id, Task.status == "open")
                .scalar_subquery()
            )
            combined = and_(combined, open_tasks_cnt >= min_open_tasks)

        base_stmt = select(Opportunity).where(combined)

        count = (await db.execute(select(func.count(Opportunity.id)).where(combined))).scalar() or 0
        total_amount = (await db.execute(
            select(func.coalesce(func.sum(Opportunity.amount), 0.0)).where(combined)
        )).scalar() or 0

        items_q = await db.execute(
            base_stmt.order_by(Opportunity.updated_at.desc()).limit(50)
        )
        items = items_q.scalars().unique().all()
        item_ids = [o.id for o in items]

        # Batch: last activity + open task counts for board badges
        last_activity_map: dict[int, datetime | None] = {}
        open_tasks_map: dict[int, int] = {}
        if item_ids:
            last_activity_map = await _last_activity_max_by_opportunity_ids(
                db, [int(i) for i in item_ids]
            )

            task_rows = (
                await db.execute(
                    select(Task.opportunity_id, func.count(Task.id))
                    .where(
                        Task.opportunity_id.in_(item_ids),
                        Task.status == "open",
                    )
                    .group_by(Task.opportunity_id)
                )
            ).all()
            open_tasks_map = {int(row[0]): int(row[1]) for row in task_rows}

        item_payloads: list[dict] = []
        for o in items:
            la = last_activity_map.get(int(o.id))
            row = _opp_to_dict(o, last_activity_at=la)
            row["last_activity_at"] = la.isoformat() if la is not None else None
            row["open_tasks_count"] = open_tasks_map.get(int(o.id), 0)
            item_payloads.append(row)

        columns.append({
            "stage": stage,
            "count": count,
            "total_amount": round(float(total_amount), 2),
            "items": item_payloads,
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

    # Rotting: no last activity (else last update) for > 7 days — same staleness as /board/kanban
    rotting_threshold = now - timedelta(days=7)
    staleness_ts = _board_staleness_timestamp()
    rotting_count = (await db.execute(
        select(func.count(Opportunity.id)).where(
            and_(Opportunity.status == "active", staleness_ts < rotting_threshold)
        )
    )).scalar() or 0

    return {
        "window_days": window,
        "open_pipeline_total": round(float(open_total), 2),
        "won_count": won_count,
        "win_rate": win_rate,
        "rotting_count": rotting_count,
    }
