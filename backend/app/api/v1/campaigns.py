"""Campaign Management API — CRUD, member management, and ROI tracking."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import NotFoundException
from app.models.campaign import Campaign, CampaignMember
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.campaign import CampaignResponse
from app.schemas.common import PaginatedResponse
from app.services.tenant_context import assert_same_tenant, scoped_for_user

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


def _require_campaigns():
    """Dependency: reject if FEATURE_CAMPAIGNS is off."""
    if not settings.FEATURE_CAMPAIGNS:
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic Schemas ──


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str = Field(default="email", max_length=30)
    status: str = Field(default="draft", max_length=20)
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    budget: Optional[float] = None
    expected_revenue: Optional[float] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    type: Optional[str] = Field(default=None, max_length=30)
    status: Optional[str] = Field(default=None, max_length=20)
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    budget: Optional[float] = None
    actual_cost: Optional[float] = None
    expected_revenue: Optional[float] = None
    actual_revenue: Optional[float] = None


class MemberAdd(BaseModel):
    lead_id: Optional[int] = None
    customer_id: Optional[int] = None


class MemberStatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=20)


# ── Helpers ──


def _campaign_to_dict(campaign: Campaign, member_count: int = 0) -> dict:
    data = {
        "id": campaign.id,
        # R6-API-1 — tenant_id round-tripped after the migration so the
        # SPA can verify isolation client-side.
        "tenant_id": getattr(campaign, "tenant_id", None),
        "name": campaign.name,
        "type": campaign.type,
        "status": campaign.status,
        "description": campaign.description,
        "start_date": campaign.start_date.isoformat() if campaign.start_date else None,
        "end_date": campaign.end_date.isoformat() if campaign.end_date else None,
        "budget": campaign.budget,
        "actual_cost": campaign.actual_cost,
        "expected_revenue": campaign.expected_revenue,
        "actual_revenue": campaign.actual_revenue,
        "created_by": campaign.created_by,
        "member_count": member_count,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
    }
    # R5-PERM-1 — admin-configured field-permission rules apply here.
    from app.services.field_permission_service import apply_request_perms

    return apply_request_perms(data, "campaign")


def _member_to_dict(member: CampaignMember) -> dict:
    # R6-API-4 — lead and customer relationships are loaded selectin
    # on the model, so emitting summary objects is free. Without them
    # the SPA could only render "#${lead_id}" / "#${customer_id}"
    # placeholder rows.
    lead_summary: dict | None = None
    if getattr(member, "lead", None) is not None:
        lead_summary = {
            "id": member.lead.id,
            "first_name": member.lead.first_name,
            "last_name": member.lead.last_name,
            "email": member.lead.email,
        }
    customer_summary: dict | None = None
    if getattr(member, "customer", None) is not None:
        customer_summary = {
            "id": member.customer.id,
            "name": member.customer.name,
            "email": member.customer.email,
            "company": member.customer.company,
        }
    return {
        "id": member.id,
        "campaign_id": member.campaign_id,
        "lead_id": member.lead_id,
        "customer_id": member.customer_id,
        "lead": lead_summary,
        "customer": customer_summary,
        "status": member.status,
        "responded_at": member.responded_at.isoformat() if member.responded_at else None,
        "created_at": member.created_at.isoformat() if member.created_at else None,
    }


# ── Endpoints ──


# Round-10 R10-API-5 — canonical pagination envelope on OpenAPI.
@router.get("/", response_model=PaginatedResponse[CampaignResponse])
async def list_campaigns(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_campaigns),
):
    """List campaigns with optional status/type filters and pagination.

    Returns the canonical envelope ``{items, total, page, page_size, pages}``
    so the frontend list component doesn't need a campaigns-specific
    pagination shape (audit A-5).
    """
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 200:
        page_size = 20
    query = select(Campaign).order_by(Campaign.created_at.desc())
    # R6-API-1 — tenant scoping. Pre-R6, every authenticated user saw
    # every other tenant's campaigns. Mirrors the round-4 fix for
    # invoice/contract/subscription.
    query = scoped_for_user(query, current_user, column=Campaign.tenant_id)
    if status:
        query = query.where(Campaign.status == status)
    if type:
        query = query.where(Campaign.type == type)

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    campaigns = result.scalars().all()

    items = []
    for campaign in campaigns:
        count_res = await db.execute(
            select(func.count(CampaignMember.id)).where(
                CampaignMember.campaign_id == campaign.id
            )
        )
        member_count = count_res.scalar_one()
        items.append(_campaign_to_dict(campaign, member_count))

    import math

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.post("/", status_code=201, response_model=CampaignResponse)
async def create_campaign(
    body: CampaignCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_campaigns),
):
    """Create a new campaign (manager only)."""
    campaign = Campaign(
        # R6-API-1 — every CRM row carries tenant_id (R4-CLOSE-1).
        tenant_id=getattr(current_user, "tenant_id", None),
        name=body.name,
        type=body.type,
        status=body.status,
        description=body.description,
        budget=body.budget,
        expected_revenue=body.expected_revenue,
        created_by=current_user.id,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return {
        "message": "Kampanya olusturuldu",
        "id": campaign.id,
        "name": campaign.name,
    }


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_campaigns),
):
    """Get campaign detail with member count."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadi")
    # R6-API-1 — cross-tenant access maps to 404, not 403, so an attacker
    # cannot probe campaign IDs to enumerate other tenants.
    assert_same_tenant(campaign, current_user, exception_cls=NotFoundException)

    count_res = await db.execute(
        select(func.count(CampaignMember.id)).where(
            CampaignMember.campaign_id == campaign_id
        )
    )
    member_count = count_res.scalar_one()
    return _campaign_to_dict(campaign, member_count)


@router.put("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int,
    body: CampaignUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_campaigns),
):
    """Update a campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadi")
    assert_same_tenant(campaign, current_user, exception_cls=NotFoundException)

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Guncellenecek alan bulunamadi")

    for key, value in update_data.items():
        setattr(campaign, key, value)

    await db.commit()
    await db.refresh(campaign)
    return {"message": "Kampanya guncellendi", "id": campaign.id}


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_campaigns),
):
    """Soft-delete a campaign by setting status to cancelled (manager only)."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadi")
    assert_same_tenant(campaign, current_user, exception_cls=NotFoundException)

    campaign.status = "cancelled"
    await db.commit()
    return {"message": "Kampanya iptal edildi", "id": campaign_id}


@router.get("/{campaign_id}/roi")
async def get_campaign_roi(
    campaign_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_campaigns),
):
    """Compute ROI metrics for a campaign."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadi")
    assert_same_tenant(campaign, current_user, exception_cls=NotFoundException)

    count_res = await db.execute(
        select(func.count(CampaignMember.id)).where(
            CampaignMember.campaign_id == campaign_id
        )
    )
    member_count = count_res.scalar_one()

    responded_res = await db.execute(
        select(func.count(CampaignMember.id)).where(
            CampaignMember.campaign_id == campaign_id,
            CampaignMember.status == "responded",
        )
    )
    responded_count = responded_res.scalar_one()

    converted_res = await db.execute(
        select(func.count(CampaignMember.id)).where(
            CampaignMember.campaign_id == campaign_id,
            CampaignMember.status == "converted",
        )
    )
    converted_count = converted_res.scalar_one()

    actual_cost = campaign.actual_cost or 0.0
    actual_revenue = campaign.actual_revenue or 0.0

    roi_pct = (
        (actual_revenue - actual_cost) / actual_cost * 100
        if actual_cost > 0
        else 0.0
    )
    conversion_rate = (
        converted_count / member_count * 100 if member_count > 0 else 0.0
    )

    return {
        "campaign_id": campaign_id,
        "actual_revenue": actual_revenue,
        "actual_cost": actual_cost,
        "roi_pct": round(roi_pct, 2),
        "member_count": member_count,
        "responded_count": responded_count,
        "conversion_rate": round(conversion_rate, 2),
    }


@router.get("/{campaign_id}/members")
async def list_campaign_members(
    campaign_id: int,
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_campaigns),
):
    """List campaign members with pagination."""
    campaign_res = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = campaign_res.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadi")
    assert_same_tenant(campaign, current_user, exception_cls=NotFoundException)

    count_res = await db.execute(
        select(func.count(CampaignMember.id)).where(
            CampaignMember.campaign_id == campaign_id
        )
    )
    total = count_res.scalar_one()

    result = await db.execute(
        select(CampaignMember)
        .where(CampaignMember.campaign_id == campaign_id)
        .order_by(CampaignMember.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    members = result.scalars().all()

    return {
        "items": [_member_to_dict(m) for m in members],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("/{campaign_id}/members", status_code=201)
async def add_campaign_members(
    campaign_id: int,
    body: list[MemberAdd],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_campaigns),
):
    """Bulk add members (leads or customers) to a campaign."""
    campaign_res = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = campaign_res.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadi")
    assert_same_tenant(campaign, current_user, exception_cls=NotFoundException)

    added = 0
    invalid = 0
    for entry in body:
        if not entry.lead_id and not entry.customer_id:
            invalid += 1
            continue
        member = CampaignMember(
            # R6-API-1 — child rows mirror their parent's tenant_id so
            # cross-tenant attempts (lead_id from another tenant) still
            # leave a row that scoped_for_user filters out.
            tenant_id=getattr(campaign, "tenant_id", None),
            campaign_id=campaign_id,
            lead_id=entry.lead_id,
            customer_id=entry.customer_id,
            status="sent",
        )
        db.add(member)
        added += 1

    if added == 0:
        raise HTTPException(
            status_code=400,
            detail="No valid members to add. Each entry must have lead_id or customer_id.",
        )

    await db.commit()
    return {"message": "Uyeler eklendi", "added": added, "invalid": invalid}


@router.delete("/{campaign_id}/members/{member_id}")
async def remove_campaign_member(
    campaign_id: int,
    member_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_campaigns),
):
    """Remove a member from a campaign."""
    result = await db.execute(
        select(CampaignMember).where(
            CampaignMember.id == member_id,
            CampaignMember.campaign_id == campaign_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Uye bulunamadi")
    # R6-API-1 — assert via parent campaign, since legacy rows may have
    # NULL tenant_id while the campaign carries the correct value.
    assert_same_tenant(member.campaign, current_user, exception_cls=NotFoundException)

    await db.delete(member)
    await db.commit()
    return {"message": "Uye kaldirildi", "id": member_id}


@router.patch("/{campaign_id}/members/{member_id}/status")
async def update_member_status(
    campaign_id: int,
    member_id: int,
    body: MemberStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_campaigns),
):
    """Update the status of a campaign member."""
    result = await db.execute(
        select(CampaignMember).where(
            CampaignMember.id == member_id,
            CampaignMember.campaign_id == campaign_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Uye bulunamadi")
    assert_same_tenant(member.campaign, current_user, exception_cls=NotFoundException)

    member.status = body.status
    await db.commit()
    return {"message": "Uye durumu guncellendi", "id": member_id, "status": body.status}
