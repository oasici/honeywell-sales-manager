"""Stakeholder (Buyer Relationship Map) API — CRUD + coverage alerts.

Gated by FEATURE_BUYER_MAP. Provides buying committee visualization
data for opportunities and customer accounts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.sequence_v2 import Stakeholder
from app.models.user import User
from app.services.tenant_context import assert_same_tenant
from app.schemas.common import PaginatedResponse
from app.schemas.round15_pagination import StakeholderRow
from app.schemas.round16_aggregates import StakeholderAlertsResponse

router = APIRouter(prefix="/stakeholders", tags=["Buyer Relationship Map"])


async def _assert_parent_in_tenant(
    db: AsyncSession,
    current_user: User,
    *,
    opportunity_id: int | None = None,
    customer_id: int | None = None,
) -> None:
    """R5-TEN-26 — Stakeholder has no tenant_id of its own; the boundary
    is inherited from the opportunity / customer it points to. Load the
    parent and assert_same_tenant; both 'doesn't exist' and 'lives in
    another tenant' collapse to 404 so we don't leak existence."""
    if opportunity_id is not None:
        opp = (
            await db.execute(
                select(Opportunity).where(Opportunity.id == opportunity_id)
            )
        ).scalar_one_or_none()
        if opp is None:
            raise NotFoundException("Firsat bulunamadi")
        assert_same_tenant(opp, current_user, exception_cls=NotFoundException)
    if customer_id is not None:
        customer = (
            await db.execute(
                select(Customer).where(Customer.id == customer_id)
            )
        ).scalar_one_or_none()
        if customer is None:
            raise NotFoundException("Musteri bulunamadi")
        assert_same_tenant(customer, current_user, exception_cls=NotFoundException)

VALID_SENIORITIES = {"executive", "senior", "mid_level", "junior"}
VALID_DEPARTMENTS = {"tech", "finance", "legal", "operations", "sales", "marketing", "hr", "other"}
VALID_BUYER_ROLES = {"decision_maker", "influencer", "champion", "detractor", "gatekeeper", "end_user"}


def _require_buyer_map():
    if not settings.FEATURE_BUYER_MAP:
        raise HTTPException(status_code=404, detail="Not found")


class StakeholderCreate(BaseModel):
    opportunity_id: int | None = None
    customer_id: int | None = None
    name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    title: str | None = None
    phone: str | None = None
    seniority: str | None = None
    department_group: str | None = None
    buyer_role: str | None = None
    notes: str | None = None


class StakeholderUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    title: str | None = None
    phone: str | None = None
    seniority: str | None = None
    department_group: str | None = None
    buyer_role: str | None = None
    notes: str | None = None


def _serialize(s: Stakeholder) -> dict:
    return {
        "id": s.id,
        "opportunity_id": s.opportunity_id,
        "customer_id": s.customer_id,
        "name": s.name,
        "email": s.email,
        "title": s.title,
        "phone": s.phone,
        "seniority": s.seniority,
        "department_group": s.department_group,
        "buyer_role": s.buyer_role,
        "notes": s.notes,
        "is_auto_detected": s.is_auto_detected,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("/opportunity/{opportunity_id}", response_model=PaginatedResponse[StakeholderRow])
async def list_by_opportunity(
    opportunity_id: int,
    _: None = Depends(_require_buyer_map),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all stakeholders for an opportunity (buyer relationship map data)."""
    await _assert_parent_in_tenant(db, current_user, opportunity_id=opportunity_id)
    rows = (
        await db.execute(
            select(Stakeholder)
            .where(Stakeholder.opportunity_id == opportunity_id)
            .order_by(Stakeholder.seniority.desc().nullslast(), Stakeholder.name)
        )
    ).scalars().all()
    items = [_serialize(s) for s in rows]
    total = len(items)
    # R7-API-4 — canonical pagination envelope; legacy keys retained.
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
        "opportunity_id": opportunity_id,
        "stakeholders": items,
    }


@router.get("/customer/{customer_id}", response_model=PaginatedResponse[StakeholderRow])
async def list_by_customer(
    customer_id: int,
    _: None = Depends(_require_buyer_map),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all stakeholders for a customer account."""
    await _assert_parent_in_tenant(db, current_user, customer_id=customer_id)
    rows = (
        await db.execute(
            select(Stakeholder)
            .where(Stakeholder.customer_id == customer_id)
            .order_by(Stakeholder.name)
        )
    ).scalars().all()
    items = [_serialize(s) for s in rows]
    total = len(items)
    # R7-API-4 — canonical pagination envelope; legacy keys retained.
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
        "customer_id": customer_id,
        "stakeholders": items,
    }


@router.post("/", status_code=201, response_model=StakeholderRow)
async def create_stakeholder(
    body: StakeholderCreate,
    _: None = Depends(_require_buyer_map),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a stakeholder to an opportunity or customer."""
    if not body.opportunity_id and not body.customer_id:
        raise HTTPException(status_code=400, detail="opportunity_id or customer_id required")

    # R5-TEN-26 — verify the caller has access to the parent record
    # before we let them hang stakeholder rows off it.
    await _assert_parent_in_tenant(
        db,
        current_user,
        opportunity_id=body.opportunity_id,
        customer_id=body.customer_id,
    )

    if body.seniority and body.seniority not in VALID_SENIORITIES:
        raise HTTPException(status_code=400, detail="invalid seniority")
    if body.department_group and body.department_group not in VALID_DEPARTMENTS:
        raise HTTPException(status_code=400, detail="invalid department_group")
    if body.buyer_role and body.buyer_role not in VALID_BUYER_ROLES:
        raise HTTPException(status_code=400, detail="invalid buyer_role")

    stakeholder = Stakeholder(
        opportunity_id=body.opportunity_id,
        customer_id=body.customer_id,
        name=body.name,
        email=body.email,
        title=body.title,
        phone=body.phone,
        seniority=body.seniority,
        department_group=body.department_group,
        buyer_role=body.buyer_role,
        notes=body.notes,
        created_by=current_user.id,
    )
    db.add(stakeholder)
    await db.commit()
    await db.refresh(stakeholder)
    return _serialize(stakeholder)


@router.put("/{stakeholder_id}", response_model=StakeholderRow)
async def update_stakeholder(
    stakeholder_id: int,
    body: StakeholderUpdate,
    _: None = Depends(_require_buyer_map),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update stakeholder details."""
    s = (await db.execute(
        select(Stakeholder).where(Stakeholder.id == stakeholder_id)
    )).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Stakeholder not found")
    await _assert_parent_in_tenant(
        db,
        current_user,
        opportunity_id=s.opportunity_id,
        customer_id=s.customer_id,
    )

    data = body.model_dump(exclude_unset=True)
    if data.get("seniority") is not None and data["seniority"] not in VALID_SENIORITIES:
        raise HTTPException(status_code=400, detail="invalid seniority")
    if data.get("department_group") is not None and data["department_group"] not in VALID_DEPARTMENTS:
        raise HTTPException(status_code=400, detail="invalid department_group")
    if data.get("buyer_role") is not None and data["buyer_role"] not in VALID_BUYER_ROLES:
        raise HTTPException(status_code=400, detail="invalid buyer_role")

    for field, value in data.items():
        setattr(s, field, value)

    await db.commit()
    await db.refresh(s)
    return _serialize(s)


@router.delete("/{stakeholder_id}", status_code=204)
async def delete_stakeholder(
    stakeholder_id: int,
    _: None = Depends(_require_buyer_map),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a stakeholder."""
    s = (await db.execute(
        select(Stakeholder).where(Stakeholder.id == stakeholder_id)
    )).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Stakeholder not found")
    await _assert_parent_in_tenant(
        db,
        current_user,
        opportunity_id=s.opportunity_id,
        customer_id=s.customer_id,
    )
    await db.delete(s)
    await db.commit()


@router.get("/opportunity/{opportunity_id}/alerts", response_model=StakeholderAlertsResponse)
async def coverage_alerts(
    opportunity_id: int,
    _: None = Depends(_require_buyer_map),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate coverage gap alerts for an opportunity's buying committee.

    Checks:
    - No Decision Maker identified
    - Missing department coverage (fewer than 2 departments)
    - Detractor identified (risk flag)
    - Single-threaded deal (fewer than 3 stakeholders)
    """
    rows = (
        await db.execute(
            select(Stakeholder).where(Stakeholder.opportunity_id == opportunity_id)
        )
    ).scalars().all()

    alerts: list[dict] = []

    if not rows:
        alerts.append({
            "severity": "warning",
            "type": "no_stakeholders",
            "message": "Hicbir paydas tanimlanmamis — alis komitesini olusturun",
        })
        return {"opportunity_id": opportunity_id, "alerts": alerts, "stakeholder_count": 0}

    # Decision Maker check
    roles = {s.buyer_role for s in rows if s.buyer_role}
    if "decision_maker" not in roles:
        alerts.append({
            "severity": "warning",
            "type": "no_decision_maker",
            "message": "Karar verici tanimlanmamis — kilit kisiyi belirleyin",
        })

    # Department coverage
    departments = {s.department_group for s in rows if s.department_group}
    if len(departments) < 2:
        alerts.append({
            "severity": "info",
            "type": "low_department_coverage",
            "message": f"Sadece {len(departments)} departman temsil ediliyor — kapsami genisletin",
        })

    # Detractor check
    if "detractor" in roles:
        alerts.append({
            "severity": "risk",
            "type": "detractor_identified",
            "message": "Muhalif tanimlanmis — azaltma stratejisi gelistirin",
        })

    # Champion check
    if "champion" in roles:
        alerts.append({
            "severity": "positive",
            "type": "champion_exists",
            "message": "Sampiyon tanimlanmis — ic satis icin kullanin",
        })

    # Single-threaded check
    if len(rows) < 3:
        alerts.append({
            "severity": "warning",
            "type": "single_threaded",
            "message": f"Sadece {len(rows)} kisi — coklu kanalli etkilesim oneriliyor",
        })

    return {
        "opportunity_id": opportunity_id,
        "alerts": alerts,
        "stakeholder_count": len(rows),
        "departments": list(departments),
        "roles": list(roles),
    }
