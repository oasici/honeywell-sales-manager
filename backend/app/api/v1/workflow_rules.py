"""Workflow Rules API — CRUD for event-driven automation rules."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.models.user import User
from app.models.workflow_rule import WorkflowRule

router = APIRouter(prefix="/workflow-rules", tags=["Workflow Rules"])


def _require_workflow_rules():
    """Dependency: reject if FEATURE_WORKFLOW_RULES is off."""
    if not settings.FEATURE_WORKFLOW_RULES:
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic Schemas ──


class WorkflowRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    entity_type: str = Field(min_length=1, max_length=50)
    trigger_event: str = Field(min_length=1, max_length=100)
    conditions_json: str | None = None
    actions_json: str = "[]"
    flow_json: str | None = None
    is_active: bool = True


class WorkflowRuleUpdate(BaseModel):
    name: str | None = None
    entity_type: str | None = None
    trigger_event: str | None = None
    conditions_json: str | None = None
    actions_json: str | None = None
    flow_json: str | None = None
    is_active: bool | None = None


# ── Endpoints ──


@router.get("/")
async def list_workflow_rules(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_workflow_rules),
):
    """List all workflow rules (manager only)."""
    result = await db.execute(
        select(WorkflowRule).order_by(WorkflowRule.created_at.desc())
    )
    rules = result.scalars().all()
    return {
        "items": [_rule_to_dict(r) for r in rules],
        "total": len(rules),
    }


@router.post("/", status_code=201)
async def create_workflow_rule(
    body: WorkflowRuleCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_workflow_rules),
):
    """Create a new workflow rule (manager only)."""
    rule = WorkflowRule(
        name=body.name,
        entity_type=body.entity_type,
        trigger_event=body.trigger_event,
        conditions_json=body.conditions_json,
        actions_json=body.actions_json,
        flow_json=body.flow_json,
        is_active=body.is_active,
        created_by=current_user.id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return {
        "message": "Is kurali olusturuldu",
        "id": rule.id,
        "name": rule.name,
    }


@router.put("/{rule_id}")
async def update_workflow_rule(
    rule_id: int,
    body: WorkflowRuleUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_workflow_rules),
):
    """Update a workflow rule (manager only)."""
    result = await db.execute(
        select(WorkflowRule).where(WorkflowRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Is kurali bulunamadi")

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Guncellenecek alan bulunamadi")

    for key, value in update_data.items():
        setattr(rule, key, value)

    await db.commit()
    await db.refresh(rule)
    return {"message": "Is kurali guncellendi", "id": rule.id}


@router.delete("/{rule_id}")
async def delete_workflow_rule(
    rule_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_workflow_rules),
):
    """Delete a workflow rule (manager only)."""
    result = await db.execute(
        select(WorkflowRule).where(WorkflowRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Is kurali bulunamadi")

    await db.delete(rule)
    await db.commit()
    return {"message": "Is kurali silindi", "id": rule_id}


# ── Helpers ──


def _rule_to_dict(rule: WorkflowRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "entity_type": rule.entity_type,
        "trigger_event": rule.trigger_event,
        "conditions_json": rule.conditions_json,
        "actions_json": rule.actions_json,
        "flow_json": rule.flow_json,
        "is_active": rule.is_active,
        "created_by": rule.created_by,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }
