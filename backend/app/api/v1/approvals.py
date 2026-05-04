"""Approval routing API -- rule CRUD + approval/rejection workflows."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import NotFoundException
from app.models.approval import ApprovalRequest, ApprovalRule
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.user import User
from app.services.approval_service import ApprovalService
from app.services.tenant_context import assert_same_tenant, scoped_for_user


# Map of supported entity_type values to their owning model. Used to
# validate cross-tenant access on /approvals/history (audit TEN-2).
# ApprovalRequest itself has no tenant_id column — we have to reach
# through to the parent entity.
_APPROVAL_ENTITY_MODELS = {
    "quote": Quote,
    "opportunity": Opportunity,
}


async def _assert_entity_in_tenant(
    db: AsyncSession, entity_type: str, entity_id: int, user: User,
) -> None:
    """Raise NotFoundException unless the entity exists and the caller's tenant owns it."""
    model = _APPROVAL_ENTITY_MODELS.get(entity_type)
    if model is None:
        # Unknown entity_type cannot be tenant-checked — treat as not-found
        # so a malicious caller can't probe which types exist.
        raise NotFoundException("Not found")
    record = (
        await db.execute(select(model).where(model.id == entity_id))
    ).scalar_one_or_none()
    if record is None:
        raise NotFoundException("Not found")
    assert_same_tenant(record, user, exception_cls=NotFoundException)

router = APIRouter(prefix="/approvals", tags=["Approvals"])


def _require_approval_routing():
    """Dependency: reject if FEATURE_APPROVAL_ROUTING is off."""
    if not settings.FEATURE_APPROVAL_ROUTING:
        raise HTTPException(status_code=404, detail="Not found")


# -- Pydantic Schemas --

class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    entity_type: str = "quote"
    condition_type: str = Field(min_length=1, max_length=30)
    threshold_value: float
    threshold_operator: str = Field(min_length=1, max_length=10)
    approver_role: str | None = None
    approver_user_id: int | None = None
    priority: int = 0
    is_active: bool = True


class RuleUpdate(BaseModel):
    name: str | None = None
    entity_type: str | None = None
    condition_type: str | None = None
    threshold_value: float | None = None
    threshold_operator: str | None = None
    approver_role: str | None = None
    approver_user_id: int | None = None
    priority: int | None = None
    is_active: bool | None = None


class ApprovalDecision(BaseModel):
    comments: str = ""


# -- Rule Endpoints (manager only) --

@router.get("/rules")
async def list_rules(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_approval_routing),
):
    """List all approval rules."""
    stmt = scoped_for_user(
        select(ApprovalRule), current_user, column=ApprovalRule.tenant_id,
    )
    result = await db.execute(stmt.order_by(ApprovalRule.priority.desc()))
    rules = result.scalars().all()
    return {"items": [_rule_to_dict(r) for r in rules]}


@router.post("/rules", status_code=201)
async def create_rule(
    data: RuleCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_approval_routing),
):
    """Create a new approval rule."""
    rule = ApprovalRule(
        name=data.name,
        entity_type=data.entity_type,
        condition_type=data.condition_type,
        threshold_value=data.threshold_value,
        threshold_operator=data.threshold_operator,
        approver_role=data.approver_role,
        approver_user_id=data.approver_user_id,
        priority=data.priority,
        is_active=data.is_active,
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return _rule_to_dict(rule)


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: int,
    data: RuleUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_approval_routing),
):
    """Update an existing approval rule."""
    result = await db.execute(
        select(ApprovalRule).where(ApprovalRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise NotFoundException("Onay kurali bulunamadi")
    assert_same_tenant(rule, current_user, exception_cls=NotFoundException)

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(rule, field, value)

    await db.flush()
    await db.refresh(rule)
    return _rule_to_dict(rule)


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_approval_routing),
):
    """Delete an approval rule."""
    result = await db.execute(
        select(ApprovalRule).where(ApprovalRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise NotFoundException("Onay kurali bulunamadi")
    assert_same_tenant(rule, current_user, exception_cls=NotFoundException)

    await db.delete(rule)
    await db.flush()


# -- Approval Workflow Endpoints --

@router.get("/pending")
async def list_pending(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_approval_routing),
):
    """Get approval requests pending for the current user."""
    service = ApprovalService(db)
    pending = await service.get_pending_approvals(current_user.id)
    return {"items": [_request_to_dict(r) for r in pending]}


@router.post("/{request_id}/approve")
async def approve_request(
    request_id: int,
    data: ApprovalDecision | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_approval_routing),
):
    """Approve an approval request."""
    service = ApprovalService(db)
    comments = data.comments if data else ""
    approval_request = await service.approve(request_id, current_user.id, comments)
    return _request_to_dict(approval_request)


@router.post("/{request_id}/reject")
async def reject_request(
    request_id: int,
    data: ApprovalDecision | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_approval_routing),
):
    """Reject an approval request (cascades to all pending for same entity)."""
    service = ApprovalService(db)
    comments = data.comments if data else ""
    approval_request = await service.reject(request_id, current_user.id, comments)
    return _request_to_dict(approval_request)


@router.get("/history")
async def approval_history(
    entity_type: str = Query(..., min_length=1),
    entity_id: int = Query(..., ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_approval_routing),
):
    """Get approval history for a specific entity."""
    # Tenant guard (audit TEN-2). Without this an authenticated user
    # could enumerate any entity's approval chain by guessing IDs.
    await _assert_entity_in_tenant(db, entity_type, entity_id, current_user)
    service = ApprovalService(db)
    history = await service.get_approval_history(entity_type, entity_id)
    return {"items": [_request_to_dict(r) for r in history]}


@router.post("/quick-approve/{request_id}")
async def quick_approve(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_approval_routing),
):
    """Minimal-payload approve for PWA. Just approves with empty comment."""
    service = ApprovalService(db)
    approval_request = await service.approve(request_id, current_user.id, "")
    return _request_to_dict(approval_request)


class DelegateRequest(BaseModel):
    rule_id: int
    delegate_to: int
    delegate_until: str | None = None  # ISO datetime


@router.post("/delegate")
async def delegate_approval(
    data: DelegateRequest,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_approval_routing),
):
    """Delegate approval authority to another user (PTO coverage)."""
    from datetime import datetime as dt

    result = await db.execute(select(ApprovalRule).where(ApprovalRule.id == data.rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise NotFoundException("Kural bulunamadi")
    assert_same_tenant(rule, current_user, exception_cls=NotFoundException)

    rule.delegate_to = data.delegate_to
    if data.delegate_until:
        rule.delegate_until = dt.fromisoformat(data.delegate_until)
    await db.flush()

    return _rule_to_dict(rule)


# -- Helpers --

def _rule_to_dict(rule: ApprovalRule) -> dict:
    return {
        "id": rule.id,
        "tenant_id": getattr(rule, "tenant_id", None),
        "name": rule.name,
        "entity_type": rule.entity_type,
        "condition_type": rule.condition_type,
        "threshold_value": rule.threshold_value,
        "threshold_operator": rule.threshold_operator,
        "approver_role": rule.approver_role,
        "approver_user_id": rule.approver_user_id,
        "priority": rule.priority,
        "is_active": rule.is_active,
        "escalation_hours": getattr(rule, "escalation_hours", None),
        "escalation_action": getattr(rule, "escalation_action", None),
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


def _request_to_dict(req: ApprovalRequest) -> dict:
    return {
        "id": req.id,
        "entity_type": req.entity_type,
        "entity_id": req.entity_id,
        "rule_id": req.rule_id,
        "level": req.level,
        "status": req.status,
        "requested_by": req.requested_by,
        "assigned_to": req.assigned_to,
        "decided_by": req.decided_by,
        "decided_at": req.decided_at.isoformat() if req.decided_at else None,
        "comments": req.comments,
        "created_at": req.created_at.isoformat() if req.created_at else None,
    }
