"""Territory Management API — hierarchical territory CRUD, assignments, and auto-assign."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.territory import Territory, TerritoryAssignment
from app.models.user import User
from app.services.tenant_context import assert_same_tenant, scoped_for_user

router = APIRouter(prefix="/territories", tags=["Territories"])

VALID_ASSIGNMENT_ROLES = {"owner", "member", "viewer"}


def _require_territories():
    """Dependency: reject if FEATURE_TERRITORIES is off."""
    if not settings.FEATURE_TERRITORIES:
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic Schemas ──


class TerritoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: Optional[int] = None
    description: Optional[str] = None
    region: Optional[str] = Field(default=None, max_length=100)
    rules_json: Optional[str] = None


class TerritoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    parent_id: Optional[int] = None
    description: Optional[str] = None
    region: Optional[str] = Field(default=None, max_length=100)
    rules_json: Optional[str] = None


class AssignmentCreate(BaseModel):
    user_id: int
    role: str = Field(default="member", max_length=20)


# ── Serializers ──


def _serialize_territory(t: Territory) -> dict:
    return {
        "id": t.id,
        # Round-4 R4-DTO-6 — round-trip tenant_id (R4-TEN-16).
        "tenant_id": getattr(t, "tenant_id", None),
        "name": t.name,
        "parent_id": t.parent_id,
        "description": t.description,
        "region": t.region,
        "rules_json": t.rules_json,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _serialize_assignment(a: TerritoryAssignment) -> dict:
    return {
        "id": a.id,
        "territory_id": a.territory_id,
        "user_id": a.user_id,
        "role": a.role,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _build_tree(territories: list) -> list[dict]:
    by_parent: dict[int | None, list] = {}
    for t in territories:
        by_parent.setdefault(t.parent_id, []).append(t)

    def _children(parent_id: int | None) -> list[dict]:
        return [
            {
                "id": t.id,
                "name": t.name,
                "region": t.region,
                "description": t.description,
                "children": _children(t.id),
            }
            for t in by_parent.get(parent_id, [])
        ]

    return _children(None)


def _match_rule(rule: dict, customer: Customer) -> bool:
    """Evaluate a single rules_json rule against a customer record."""
    field = rule.get("field", "")
    operator = rule.get("operator", "equals")
    value = rule.get("value", "")

    customer_value = getattr(customer, field, None)
    if customer_value is None:
        return False

    customer_str = str(customer_value).lower()
    rule_str = str(value).lower()

    if operator == "equals":
        return customer_str == rule_str
    if operator == "contains":
        return rule_str in customer_str
    if operator == "starts_with":
        return customer_str.startswith(rule_str)
    return False


def _customer_matches_territory(customer: Customer, territory: Territory) -> bool:
    """Return True if customer matches ALL rules in territory.rules_json."""
    if not territory.rules_json:
        return False
    try:
        rules = json.loads(territory.rules_json)
    except (json.JSONDecodeError, TypeError):
        return False
    if not rules:
        return False
    return all(_match_rule(r, customer) for r in rules)


# ── Endpoints ──


@router.get("/")
async def list_territories(
    _: None = Depends(_require_territories),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Flat list of all territories."""
    query = scoped_for_user(
        select(Territory).order_by(Territory.name),
        current_user,
        column=Territory.tenant_id,
    )
    result = await db.execute(query)
    territories = result.scalars().all()
    return {"territories": [_serialize_territory(t) for t in territories]}


@router.get("/tree")
async def territory_tree(
    _: None = Depends(_require_territories),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Nested tree of all territories."""
    query = scoped_for_user(
        select(Territory).order_by(Territory.name),
        current_user,
        column=Territory.tenant_id,
    )
    result = await db.execute(query)
    territories = result.scalars().all()
    return {"tree": _build_tree(list(territories))}


@router.post("/", status_code=201)
async def create_territory(
    body: TerritoryCreate,
    _: None = Depends(_require_territories),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new territory. Manager-only."""
    if body.parent_id is not None:
        parent_result = await db.execute(
            select(Territory).where(Territory.id == body.parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if parent is None:
            raise NotFoundException("Parent territory not found")
        # Round-4 R4-TEN-16 — block parenting under a foreign tenant.
        assert_same_tenant(parent, current_user, exception_cls=NotFoundException)

    territory = Territory(
        tenant_id=getattr(current_user, "tenant_id", None),
        name=body.name,
        parent_id=body.parent_id,
        description=body.description,
        region=body.region,
        rules_json=body.rules_json,
        created_by=current_user.id,
    )
    db.add(territory)
    await db.commit()
    await db.refresh(territory)
    return _serialize_territory(territory)


@router.get("/{territory_id}")
async def get_territory(
    territory_id: int,
    _: None = Depends(_require_territories),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get territory detail."""
    result = await db.execute(select(Territory).where(Territory.id == territory_id))
    territory = result.scalar_one_or_none()
    if territory is None:
        raise NotFoundException("Territory not found")
    # Round-4 R4-TEN-16 — refuse cross-tenant detail reads.
    assert_same_tenant(territory, current_user, exception_cls=NotFoundException)
    # Load assignments with user info
    assign_result = await db.execute(
        select(TerritoryAssignment, User.full_name, User.email)
        .join(User, User.id == TerritoryAssignment.user_id, isouter=True)
        .where(TerritoryAssignment.territory_id == territory_id)
    )
    assignment_rows = assign_result.all()
    assignments = [
        {
            **_serialize_assignment(row[0]),
            "user": {"full_name": row[1], "email": row[2]},
        }
        for row in assignment_rows
    ]
    return {
        "territory": _serialize_territory(territory),
        "assignments": assignments,
    }


@router.get("/{territory_id}/metrics")
async def get_territory_metrics(
    territory_id: int,
    _: None = Depends(_require_territories),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight territory KPIs for management screens."""
    terr = (
        await db.execute(select(Territory).where(Territory.id == territory_id))
    ).scalar_one_or_none()
    if terr is None:
        raise NotFoundException("Territory not found")
    # Round-4 R4-TEN-16 — block cross-tenant metric snooping.
    assert_same_tenant(terr, current_user, exception_cls=NotFoundException)

    # Round-4 R4-TEN-16 — aggregate joins must filter by the parent
    # entity's tenant_id, otherwise totals span every tenant.
    cust_count_query = scoped_for_user(
        select(func.count(Customer.id)).where(Customer.territory_id == territory_id),
        current_user,
        column=Customer.tenant_id,
    )
    cust_count = (await db.execute(cust_count_query)).scalar() or 0

    opp_count_query = scoped_for_user(
        select(func.count(Opportunity.id)).where(Opportunity.territory_id == territory_id),
        current_user,
        column=Opportunity.tenant_id,
    )
    opp_count = (await db.execute(opp_count_query)).scalar() or 0

    pipeline_query = scoped_for_user(
        select(func.coalesce(func.sum(Opportunity.amount), 0)).where(
            Opportunity.territory_id == territory_id,
            Opportunity.status == "active",
        ),
        current_user,
        column=Opportunity.tenant_id,
    )
    pipeline_total = (await db.execute(pipeline_query)).scalar() or 0

    return {
        "territory_id": territory_id,
        "customer_count": int(cust_count),
        "opportunity_count": int(opp_count),
        "active_pipeline_total": float(pipeline_total),
        "currency": "TRY",
    }


@router.get("/{territory_id}/opportunities")
async def list_territory_opportunities(
    territory_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: None = Depends(_require_territories),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List opportunities belonging to a territory (for drill-down)."""
    terr = (
        await db.execute(select(Territory).where(Territory.id == territory_id))
    ).scalar_one_or_none()
    if terr is None:
        raise NotFoundException("Territory not found")
    # Round-4 R4-TEN-16 — refuse drill-down on a foreign territory.
    assert_same_tenant(terr, current_user, exception_cls=NotFoundException)

    q = scoped_for_user(
        select(Opportunity)
        .where(Opportunity.territory_id == territory_id)
        .order_by(Opportunity.updated_at.desc())
        .limit(limit)
        .offset(offset),
        current_user,
        column=Opportunity.tenant_id,
    )
    total_query = scoped_for_user(
        select(func.count(Opportunity.id)).where(Opportunity.territory_id == territory_id),
        current_user,
        column=Opportunity.tenant_id,
    )
    total = (await db.execute(total_query)).scalar() or 0
    rows = (await db.execute(q)).scalars().all()
    return {
        "items": [
            {
                "id": o.id,
                "title": o.title,
                "stage": o.stage,
                "amount": o.amount,
                "currency": o.currency,
                "status": o.status,
                "owner_id": o.owner_id,
                "customer_id": o.customer_id,
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            }
            for o in rows
        ],
        "total": int(total),
    }


@router.put("/{territory_id}")
async def update_territory(
    territory_id: int,
    body: TerritoryUpdate,
    _: None = Depends(_require_territories),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update a territory. Manager-only."""
    result = await db.execute(select(Territory).where(Territory.id == territory_id))
    territory = result.scalar_one_or_none()
    if territory is None:
        raise NotFoundException("Territory not found")
    # Round-4 R4-TEN-16 — block cross-tenant updates.
    assert_same_tenant(territory, current_user, exception_cls=NotFoundException)

    if body.parent_id is not None:
        if body.parent_id == territory_id:
            raise BadRequestException("Territory cannot be its own parent")
        parent_result = await db.execute(
            select(Territory).where(Territory.id == body.parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if parent is None:
            raise NotFoundException("Parent territory not found")
        assert_same_tenant(parent, current_user, exception_cls=NotFoundException)
        territory.parent_id = body.parent_id

    if body.name is not None:
        territory.name = body.name
    if body.description is not None:
        territory.description = body.description
    if body.region is not None:
        territory.region = body.region
    if body.rules_json is not None:
        territory.rules_json = body.rules_json

    await db.commit()
    await db.refresh(territory)
    return _serialize_territory(territory)


@router.delete("/{territory_id}", status_code=204)
async def delete_territory(
    territory_id: int,
    _: None = Depends(_require_territories),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a territory. Fails if it has children. Manager-only."""
    result = await db.execute(select(Territory).where(Territory.id == territory_id))
    territory = result.scalar_one_or_none()
    if territory is None:
        raise NotFoundException("Territory not found")
    # Round-4 R4-TEN-16 — block cross-tenant deletes.
    assert_same_tenant(territory, current_user, exception_cls=NotFoundException)

    children_query = scoped_for_user(
        select(Territory.id).where(Territory.parent_id == territory_id).limit(1),
        current_user,
        column=Territory.tenant_id,
    )
    children_result = await db.execute(children_query)
    if children_result.scalar_one_or_none() is not None:
        raise BadRequestException("Cannot delete territory: it has child territories")

    await db.delete(territory)


@router.post("/{territory_id}/assignments", status_code=201)
async def assign_user(
    territory_id: int,
    body: AssignmentCreate,
    _: None = Depends(_require_territories),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Assign a user to a territory. Manager-only."""
    territory_result = await db.execute(
        select(Territory).where(Territory.id == territory_id)
    )
    territory = territory_result.scalar_one_or_none()
    if territory is None:
        raise NotFoundException("Territory not found")
    # Round-4 R4-TEN-16 — block assignments onto a foreign-tenant territory.
    assert_same_tenant(territory, current_user, exception_cls=NotFoundException)

    if body.role not in VALID_ASSIGNMENT_ROLES:
        raise BadRequestException(f"Invalid role. Must be one of: {', '.join(VALID_ASSIGNMENT_ROLES)}")

    user_result = await db.execute(select(User).where(User.id == body.user_id))
    target_user = user_result.scalar_one_or_none()
    if target_user is None:
        raise NotFoundException("User not found")
    # Don't let a manager pull users from another tenant into their roster.
    assert_same_tenant(target_user, current_user, exception_cls=NotFoundException)

    existing_result = await db.execute(
        select(TerritoryAssignment).where(
            TerritoryAssignment.territory_id == territory_id,
            TerritoryAssignment.user_id == body.user_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        existing.role = body.role
        await db.commit()
        await db.refresh(existing)
        return _serialize_assignment(existing)

    assignment = TerritoryAssignment(
        territory_id=territory_id,
        user_id=body.user_id,
        role=body.role,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return _serialize_assignment(assignment)


@router.delete("/{territory_id}/assignments/{user_id}", status_code=204)
async def remove_assignment(
    territory_id: int,
    user_id: int,
    _: None = Depends(_require_territories),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Remove a user assignment from a territory. Manager-only."""
    territory_result = await db.execute(
        select(Territory).where(Territory.id == territory_id)
    )
    territory = territory_result.scalar_one_or_none()
    if territory is None:
        raise NotFoundException("Assignment not found")
    # Round-4 R4-TEN-16 — block removing assignments from a foreign tenant.
    assert_same_tenant(territory, current_user, exception_cls=NotFoundException)

    result = await db.execute(
        select(TerritoryAssignment).where(
            TerritoryAssignment.territory_id == territory_id,
            TerritoryAssignment.user_id == user_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise NotFoundException("Assignment not found")

    await db.delete(assignment)


@router.post("/auto-assign")
async def auto_assign_territories(
    _: None = Depends(_require_territories),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Run rules_json against customers with no territory_id and assign matches. Manager-only."""
    # Round-4 R4-TEN-16 — auto-assign must only consider rules + rows for the
    # caller's tenant, otherwise it would tag tenant-A customers with
    # tenant-B territories.
    territories_query = scoped_for_user(
        select(Territory).where(Territory.rules_json.isnot(None)),
        current_user,
        column=Territory.tenant_id,
    )
    territories_result = await db.execute(territories_query)
    territories = territories_result.scalars().all()

    customers_query = scoped_for_user(
        select(Customer).where(Customer.territory_id.is_(None)),
        current_user,
        column=Customer.tenant_id,
    )
    customers_result = await db.execute(customers_query)
    customers = customers_result.scalars().all()

    assigned_count = 0
    for customer in customers:
        for territory in territories:
            if _customer_matches_territory(customer, territory):
                customer.territory_id = territory.id
                assigned_count += 1
                break

    await db.commit()
    return {"assigned": assigned_count, "checked": len(customers)}
