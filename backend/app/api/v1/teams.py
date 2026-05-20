"""Team and sharing rule management endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.team import SharingRule
from app.models.user import User
from app.services.access_service import AccessService
from app.services.tenant_context import assert_same_tenant, scoped_for_user
from app.schemas.common import PaginatedResponse
from app.schemas.round15_pagination import SharingRuleRow

router = APIRouter(tags=["Teams"])


def _check_feature_flag() -> None:
    """Raise 403 if team access feature is disabled."""
    if not settings.FEATURE_TEAM_ACCESS:
        raise ForbiddenException("Takim erisim ozelligi su anda devre disi")


# ── Schemas ──


class TeamMemberCreate(BaseModel):
    user_id: int
    role: str = Field(default="member", pattern="^(owner|member|viewer)$")


class TeamMemberResponse(BaseModel):
    id: int
    customer_id: int
    user_id: int
    role: str
    user_email: str | None = None
    user_full_name: str | None = None

    model_config = {"from_attributes": True}


class SharingRuleCreate(BaseModel):
    name: str = Field(max_length=200)
    entity_type: str = Field(pattern="^(customer|opportunity|quote)$")
    criteria_json: str
    share_with_role: str | None = None
    share_with_user_id: int | None = None
    access_level: str = Field(default="read", pattern="^(read|read_write)$")


class SharingRuleResponse(BaseModel):
    id: int
    name: str
    entity_type: str
    criteria_json: str
    share_with_role: str | None
    share_with_user_id: int | None
    access_level: str
    is_active: bool

    model_config = {"from_attributes": True}


# ── Team Member Endpoints ──


@router.get("/customers/{customer_id}/team", response_model=dict)
async def list_team_members(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List team members for a customer account."""
    _check_feature_flag()

    await _verify_customer_exists(db, customer_id, current_user)

    service = AccessService(db)
    members = await service.get_team_members(customer_id)

    items = [
        TeamMemberResponse(
            id=m.id,
            customer_id=m.customer_id,
            user_id=m.user_id,
            role=m.role,
            user_email=m.user.email if m.user else None,
            user_full_name=m.user.full_name if m.user else None,
        )
        for m in members
    ]
    total = len(items)
    # R7-API-4 — canonical pagination envelope; ``data`` kept as legacy
    # alias for SPA consumers mid-migration.
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
        "data": items,
    }


@router.post("/customers/{customer_id}/team", status_code=201, response_model=dict)
async def add_team_member(
    customer_id: int,
    body: TeamMemberCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a member to a customer's account team."""
    _check_feature_flag()

    await _verify_customer_exists(db, customer_id, current_user)

    # Only managers or existing team owners can add members
    if current_user.role != UserRole.SALES_MANAGER.value:
        service = AccessService(db)
        has_access = await service.can_access(
            user_id=current_user.id,
            user_role=current_user.role,
            entity_type="customer",
            entity_id=customer_id,
        )
        if not has_access:
            raise ForbiddenException("Bu musteri takimina uye ekleme yetkiniz yok")

    # Validate target user exists
    result = await db.execute(select(User).where(User.id == body.user_id))
    target_user = result.scalar_one_or_none()
    if target_user is None:
        raise NotFoundException("Kullanici bulunamadi")
    # Round-4 R4-TEN-16 — block adding a foreign-tenant user to the team.
    assert_same_tenant(target_user, current_user, exception_cls=NotFoundException)

    service = AccessService(db)
    member = await service.add_team_member(
        customer_id=customer_id,
        user_id=body.user_id,
        role=body.role,
    )

    return {
        "data": TeamMemberResponse(
            id=member.id,
            customer_id=member.customer_id,
            user_id=member.user_id,
            role=member.role,
            user_email=target_user.email,
            user_full_name=target_user.full_name,
        )
    }


@router.delete("/customers/{customer_id}/team/{user_id}", status_code=204)
async def remove_team_member(
    customer_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from a customer's account team."""
    _check_feature_flag()

    if current_user.role != UserRole.SALES_MANAGER.value:
        raise ForbiddenException("Sadece yoneticiler takim uyelerini kaldirabilir")

    # Round-4 R4-TEN-16 — block removing members from a foreign-tenant team.
    await _verify_customer_exists(db, customer_id, current_user)

    service = AccessService(db)
    await service.remove_team_member(customer_id=customer_id, user_id=user_id)


# ── Sharing Rule Endpoints ──


@router.get("/sharing-rules/", response_model=PaginatedResponse[SharingRuleRow])
async def list_sharing_rules(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """List all sharing rules (manager only)."""
    _check_feature_flag()

    # Round-4 R4-TEN-16 — sharing rules are tenant-scoped.
    query = scoped_for_user(
        select(SharingRule),
        current_user,
        column=SharingRule.tenant_id,
    )
    result = await db.execute(query)
    rules = result.scalars().all()

    items = [SharingRuleResponse.model_validate(r) for r in rules]
    total = len(items)
    # R7-API-4 — canonical pagination envelope.
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
        "data": items,
    }


@router.post("/sharing-rules/", status_code=201, response_model=dict)
async def create_sharing_rule(
    body: SharingRuleCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a sharing rule (manager only)."""
    _check_feature_flag()

    # Validate criteria JSON
    try:
        criteria = json.loads(body.criteria_json)
    except json.JSONDecodeError:
        raise BadRequestException("criteria_json gecerli bir JSON olmali")

    required_fields = {"field", "operator", "value"}
    if not required_fields.issubset(criteria.keys()):
        raise BadRequestException(
            f"criteria_json su alanlari icermeli: {', '.join(required_fields)}"
        )

    if not body.share_with_role and not body.share_with_user_id:
        raise BadRequestException(
            "share_with_role veya share_with_user_id alanlarindan en az biri gereklidir"
        )

    if body.share_with_user_id is not None:
        target_user_result = await db.execute(
            select(User).where(User.id == body.share_with_user_id)
        )
        target_user = target_user_result.scalar_one_or_none()
        if target_user is None:
            raise NotFoundException("Kullanici bulunamadi")
        # Don't share with users from other tenants.
        assert_same_tenant(target_user, current_user, exception_cls=NotFoundException)

    rule = SharingRule(
        tenant_id=getattr(current_user, "tenant_id", None),
        name=body.name,
        entity_type=body.entity_type,
        criteria_json=body.criteria_json,
        share_with_role=body.share_with_role,
        share_with_user_id=body.share_with_user_id,
        access_level=body.access_level,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)

    return {"data": SharingRuleResponse.model_validate(rule)}


@router.delete("/sharing-rules/{rule_id}", status_code=204)
async def delete_sharing_rule(
    rule_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a sharing rule (manager only)."""
    _check_feature_flag()

    result = await db.execute(select(SharingRule).where(SharingRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule is None:
        raise NotFoundException("Paylasim kurali bulunamadi")
    # Round-4 R4-TEN-16 — block deleting a foreign tenant's rule.
    assert_same_tenant(rule, current_user, exception_cls=NotFoundException)

    await db.delete(rule)


# ── Helpers ──


async def _verify_customer_exists(
    db: AsyncSession, customer_id: int, current_user: User
) -> Customer:
    """Raise 404 if customer does not exist or belongs to another tenant.

    Round-4 R4-TEN-16 — the previous implementation only checked ``id``,
    which let any caller manipulate a foreign tenant's account team.
    """
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if customer is None:
        raise NotFoundException("Musteri bulunamadi")
    assert_same_tenant(customer, current_user, exception_cls=NotFoundException)
    return customer
