"""Lead management API — CRUD + scoring + conversion."""

from __future__ import annotations

import math

import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import extract, func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.rate_limit import enforce_bulk_rate_limit
from app.models.enums import UserRole
from app.models.lead import Lead
from app.models.user import User
from app.core.event_bus import event_bus
from app.services.lead_service import LeadService
from app.services.tenant_context import assert_same_tenant, scoped_for_user

router = APIRouter(prefix="/leads", tags=["Leads"])


def _require_lead_lifecycle():
    """Dependency: reject if FEATURE_LEAD_LIFECYCLE is off."""
    if not settings.FEATURE_LEAD_LIFECYCLE:
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic Schemas ──

class LeadCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    # R5-API-9 — was bare ``str``, accepting "foo" / "a@b" until the DB
    # unique constraint fired downstream. EmailStr forces format
    # validation at the boundary, matching CustomerCreate / UserCreate.
    email: EmailStr
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    source: str = "manual"
    notes: str | None = None


class LeadUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    status: str | None = None
    notes: str | None = None


class LeadConvertRequest(BaseModel):
    create_opportunity: bool = False
    opportunity_title: str | None = None
    opportunity_amount: float | None = None


class WebLeadFormRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    # R5-API-9 — same boundary validation as LeadCreate.
    email: EmailStr
    phone: str | None = None
    company: str | None = None
    message: str | None = None
    honeypot: str | None = Field(None, description="Anti-bot field, must be empty")


# ── Rate limiter for web-to-lead ──
_web_lead_rate: dict[str, list[float]] = {}
WEB_LEAD_RATE_LIMIT = 10
WEB_LEAD_RATE_WINDOW_SECONDS = 60


def _check_web_lead_rate(client_ip: str) -> None:
    """Simple in-memory rate limiter: 10 requests per minute per IP."""
    now = time.time()
    if client_ip not in _web_lead_rate:
        _web_lead_rate[client_ip] = []

    # Clean old entries
    _web_lead_rate[client_ip] = [
        t for t in _web_lead_rate[client_ip]
        if now - t < WEB_LEAD_RATE_WINDOW_SECONDS
    ]

    if len(_web_lead_rate[client_ip]) >= WEB_LEAD_RATE_LIMIT:
        raise BadRequestException("Cok fazla istek gonderildi. Lutfen bir dakika bekleyin.")

    _web_lead_rate[client_ip].append(now)


# ── Endpoints ──

@router.get("/analytics")
async def lead_analytics(
    window: int = Query(90, ge=7, le=365),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_lead_lifecycle),
):
    """Conversion analytics: rate by source, avg time to convert, funnel by status."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    # Funnel: count by status
    funnel_result = await db.execute(
        select(Lead.status, func.count(Lead.id))
        .where(Lead.created_at >= cutoff)
        .group_by(Lead.status)
    )
    funnel = {row[0]: row[1] for row in funnel_result.all()}

    # By source: count, converted, avg days to convert
    all_leads_result = await db.execute(
        select(Lead)
        .where(Lead.created_at >= cutoff)
    )
    all_leads = all_leads_result.scalars().all()

    source_stats: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "converted_count": 0, "total_days": 0}
    )
    for lead in all_leads:
        stats = source_stats[lead.source]
        stats["count"] += 1
        if lead.status == "converted" and lead.converted_at:
            stats["converted_count"] += 1
            # Ensure timezone-aware comparison
            created = lead.created_at
            converted = lead.converted_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if converted.tzinfo is None:
                converted = converted.replace(tzinfo=timezone.utc)
            stats["total_days"] += (converted - created).days

    by_source = []
    for source, stats in source_stats.items():
        avg_days = (
            round(stats["total_days"] / stats["converted_count"], 1)
            if stats["converted_count"] > 0
            else None
        )
        rate = (
            round(stats["converted_count"] / stats["count"] * 100, 1)
            if stats["count"] > 0
            else 0
        )
        by_source.append({
            "source": source,
            "count": stats["count"],
            "converted_count": stats["converted_count"],
            "conversion_rate_pct": rate,
            "avg_days_to_convert": avg_days,
        })

    # Trend: conversions per week
    converted_leads_result = await db.execute(
        select(Lead)
        .where(Lead.status == "converted", Lead.converted_at >= cutoff)
    )
    converted_leads = converted_leads_result.scalars().all()

    weekly_trend: dict[str, int] = defaultdict(int)
    for lead in converted_leads:
        if lead.converted_at:
            converted_at = lead.converted_at
            if converted_at.tzinfo is None:
                converted_at = converted_at.replace(tzinfo=timezone.utc)
            week_key = converted_at.strftime("%Y-W%W")
            weekly_trend[week_key] += 1

    trend = [{"week": k, "conversions": v} for k, v in sorted(weekly_trend.items())]

    return {
        "window_days": window,
        "funnel": funnel,
        "by_source": by_source,
        "weekly_trend": trend,
    }


@router.post("/web-form", status_code=201)
async def web_lead_form(
    data: WebLeadFormRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint for web-to-lead capture. Rate-limited, honeypot check."""
    if not settings.FEATURE_LEAD_LIFECYCLE:
        raise HTTPException(status_code=404, detail="Not found")

    # Honeypot check: if filled, silently accept (bot detection)
    if data.honeypot:
        return {"message": "Lead kaydedildi", "lead_id": 0}

    # Rate limit by IP
    client_ip = request.client.host if request.client else "unknown"
    _check_web_lead_rate(client_ip)

    # Find a default owner (first active sales_manager, fallback to user 1)
    owner_result = await db.execute(
        select(User)
        .where(User.is_active.is_(True), User.role == "sales_manager")
        .order_by(User.id)
        .limit(1)
    )
    default_owner = owner_result.scalar_one_or_none()
    owner_id = default_owner.id if default_owner else 1

    service = LeadService(db)
    try:
        lead = await service.create_lead(
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email,
            phone=data.phone,
            company=data.company,
            source="web",
            owner_id=owner_id,
            notes=data.message,
        )
    except Exception as exc:
        raise BadRequestException(f"Lead olusturulamadi: {exc}")

    return {"message": "Lead kaydedildi", "lead_id": lead.id}


@router.get("/")
async def list_leads(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    owner_id: int | None = Query(None),
    min_score: int | None = Query(None, ge=0, le=100),
    q: str | None = Query(None, description="Search by name/email/company"),
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_lead_lifecycle),
):
    """List leads with pagination and filtering."""
    query = select(Lead)
    count_query = select(func.count(Lead.id))

    conditions = []

    # Ownership scoping
    if current_user.role != UserRole.SALES_MANAGER.value:
        conditions.append(Lead.owner_id == current_user.id)

    if status:
        conditions.append(Lead.status == status)
    if owner_id:
        conditions.append(Lead.owner_id == owner_id)
    if min_score is not None:
        conditions.append(Lead.lead_score >= min_score)
    if q:
        search = f"%{q}%"
        from sqlalchemy import or_
        conditions.append(or_(
            Lead.first_name.ilike(search),
            Lead.last_name.ilike(search),
            Lead.email.ilike(search),
            Lead.company.ilike(search),
        ))

    if conditions:
        combined = and_(*conditions)
        query = query.where(combined)
        count_query = count_query.where(combined)

    # V12 multi-tenant: no-op when current_user.tenant_id is None.
    query = scoped_for_user(query, current_user, column=Lead.tenant_id)
    count_query = scoped_for_user(count_query, current_user, column=Lead.tenant_id)

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    query = query.order_by(Lead.lead_score.desc(), Lead.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    leads = result.scalars().all()

    return {
        "items": [_lead_to_dict(l) for l in leads],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


# ── Scoring Config Endpoints ──

class ScoringConfigUpdate(BaseModel):
    weight: int | None = Field(None, ge=0, le=100)
    is_active: bool | None = None
    description: str | None = None


@router.get("/scoring-config")
async def list_scoring_configs(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_lead_lifecycle),
):
    """List all lead scoring factor configurations (manager only)."""
    from app.models.lead_scoring_config import LeadScoringConfig

    result = await db.execute(
        select(LeadScoringConfig).order_by(LeadScoringConfig.factor_name)
    )
    configs = result.scalars().all()

    return {
        "items": [
            {
                "id": c.id,
                "factor_name": c.factor_name,
                "weight": c.weight,
                "is_active": c.is_active,
                "description": c.description,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in configs
        ],
    }


@router.put("/scoring-config/{factor_name}")
async def update_scoring_config(
    factor_name: str,
    data: ScoringConfigUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_lead_lifecycle),
):
    """Update a scoring factor's weight or active status (manager only).

    Creates the config entry if it does not exist yet.
    """
    from app.models.lead_scoring_config import LeadScoringConfig

    result = await db.execute(
        select(LeadScoringConfig).where(LeadScoringConfig.factor_name == factor_name)
    )
    config = result.scalar_one_or_none()

    if not config:
        config = LeadScoringConfig(factor_name=factor_name)
        db.add(config)

    if data.weight is not None:
        config.weight = data.weight
    if data.is_active is not None:
        config.is_active = data.is_active
    if data.description is not None:
        config.description = data.description

    await db.flush()
    await db.refresh(config)

    # Invalidate the scoring config cache
    from app.services.lead_service import _scoring_config_cache
    import app.services.lead_service as _ls_module
    _ls_module._scoring_config_cache = None
    _ls_module._scoring_config_cached_at = 0

    return {
        "id": config.id,
        "factor_name": config.factor_name,
        "weight": config.weight,
        "is_active": config.is_active,
        "description": config.description,
        "created_at": config.created_at.isoformat() if config.created_at else None,
    }


@router.post(
    "/bulk-action",
    # Round-4 R4-RL-2 — DoS + audit-log flood guard.
    dependencies=[Depends(enforce_bulk_rate_limit)],
)
async def bulk_action_leads(
    body: dict,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_lead_lifecycle),
):
    """Bulk actions on leads: change_status, assign, delete, export."""
    ids = body.get("ids", [])
    action = body.get("action", "")
    params = body.get("params", {})

    if not ids or not isinstance(ids, list):
        raise BadRequestException("Gecerli bir ID listesi saglanmalidir")
    if not action:
        raise BadRequestException("Islem tipi belirtilmelidir")

    # Validate that all IDs exist AND belong to the caller's tenant.
    # Without this guard, a sales rep can mutate or export any
    # tenant's leads by guessing IDs (audit TEN-5, 2026-05-01).
    result = await db.execute(
        scoped_for_user(
            select(Lead), current_user, column=Lead.tenant_id,
        ).where(Lead.id.in_(ids))
    )
    leads = result.scalars().all()
    found_ids = {l.id for l in leads}
    missing_ids = [i for i in ids if i not in found_ids]
    if missing_ids:
        raise NotFoundException(f"Bulunamayan lead ID'leri: {missing_ids}")

    if action == "change_status":
        new_status = params.get("status")
        if not new_status:
            raise BadRequestException("Yeni durum belirtilmelidir")
        for lead in leads:
            lead.status = new_status
        await db.flush()
        return {"message": f"{len(leads)} lead durumu guncellendi", "affected_count": len(leads)}

    if action == "assign":
        new_owner_id = params.get("owner_id")
        if not new_owner_id:
            raise BadRequestException("Atanacak kullanici ID'si (owner_id) belirtilmelidir")
        for lead in leads:
            lead.owner_id = new_owner_id
        await db.flush()
        return {"message": f"{len(leads)} lead atandi", "affected_count": len(leads)}

    if action == "delete":
        if current_user.role != UserRole.SALES_MANAGER.value:
            raise BadRequestException("Silme islemi yalnizca yonetici tarafindan yapilabilir")
        for lead in leads:
            await db.delete(lead)
        await db.flush()
        return {"message": f"{len(leads)} lead silindi", "affected_count": len(leads)}

    if action == "export":
        rows = [_lead_to_dict(l) for l in leads]
        return {"message": f"{len(rows)} lead disa aktarildi", "affected_count": len(rows), "data": rows}

    raise BadRequestException(f"Bilinmeyen islem: {action}")


@router.get("/{lead_id}")
async def get_lead(
    lead_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_lead_lifecycle),
):
    """Get lead detail with score breakdown."""
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise NotFoundException("Lead bulunamadi")
    assert_same_tenant(lead, current_user, exception_cls=NotFoundException)

    lead_dict = _lead_to_dict(lead)

    # Compute score breakdown on-read for detail view
    service = LeadService(db)
    lead_dict["score_breakdown"] = await service.compute_score_breakdown(lead)

    return lead_dict


@router.post("/", status_code=201)
async def create_lead(
    data: LeadCreate,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_lead_lifecycle),
):
    """Create a new lead."""
    service = LeadService(db)
    lead = await service.create_lead(
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        phone=data.phone,
        company=data.company,
        title=data.title,
        source=data.source,
        owner_id=current_user.id,
        notes=data.notes,
        # V12 multi-tenant: inherit caller's tenant.
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    return _lead_to_dict(lead)


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: int,
    data: LeadUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_lead_lifecycle),
):
    """Update lead fields."""
    # V12 cross-tenant guard before delegating to the service.
    existing = (
        await db.execute(select(Lead).where(Lead.id == lead_id))
    ).scalar_one_or_none()
    if existing is None:
        raise NotFoundException("Lead bulunamadi")
    assert_same_tenant(existing, current_user, exception_cls=NotFoundException)

    service = LeadService(db)
    updates = data.model_dump(exclude_unset=True)
    lead = await service.update_lead(lead_id, **updates)
    return _lead_to_dict(lead)


@router.post("/{lead_id}/convert")
async def convert_lead(
    lead_id: int,
    data: LeadConvertRequest,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_lead_lifecycle),
):
    """Convert a qualified lead to Customer + optional Opportunity."""
    existing = (
        await db.execute(select(Lead).where(Lead.id == lead_id))
    ).scalar_one_or_none()
    if existing is None:
        raise NotFoundException("Lead bulunamadi")
    assert_same_tenant(existing, current_user, exception_cls=NotFoundException)

    service = LeadService(db)
    result = await service.convert_lead(
        lead_id=lead_id,
        user_id=current_user.id,
        create_opportunity=data.create_opportunity,
        opportunity_title=data.opportunity_title,
        opportunity_amount=data.opportunity_amount,
    )
    await event_bus.publish("lead.converted", {
        "lead_id": lead_id, "customer_id": result["customer_id"],
        "opportunity_id": result.get("opportunity_id"), "converted_by": current_user.id,
    })
    return result


@router.post("/{lead_id}/rescore")
async def rescore_lead(
    lead_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_lead_lifecycle),
):
    """Manually re-score a lead."""
    service = LeadService(db)
    lead = await service.update_lead(lead_id)  # triggers re-score
    return {"lead_id": lead.id, "lead_score": lead.lead_score}


# ── Helper ──

def _lead_to_dict(lead: Lead) -> dict:
    from app.services.field_permission_service import apply_request_perms

    data = {
        "id": lead.id,
        # tenant_id round-trips per the round-4 standardisation
        # (R4-DTO-2). Lead model already declares it.
        "tenant_id": getattr(lead, "tenant_id", None),
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "full_name": f"{lead.first_name} {lead.last_name}",
        "email": lead.email,
        "phone": lead.phone,
        "company": lead.company,
        "title": lead.title,
        "source": lead.source,
        "status": lead.status,
        "lead_score": lead.lead_score,
        "owner_id": lead.owner_id,
        "owner_name": lead.owner.full_name if lead.owner else None,
        "converted_customer_id": lead.converted_customer_id,
        "converted_opportunity_id": lead.converted_opportunity_id,
        "converted_at": lead.converted_at.isoformat() if lead.converted_at else None,
        # R5-API-10 — surface who converted the lead so the audit
        # surface in the UI can render the actor (was previously
        # only available via the audit log JOIN).
        "converted_by": getattr(lead, "converted_by", None),
        "notes": lead.notes,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
        "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
    }
    return apply_request_perms(data, "lead")
