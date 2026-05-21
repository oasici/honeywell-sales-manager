"""Next-Best-Action API.

Plan adoption — Phase 1 / Sprint 3 (Tasks & Next Best Action).
Service layer (``app/services/ai_action_generator.py``) already exists —
this router exposes a dedicated, predictable endpoint and lists current
open NBA-sourced tasks for an opportunity.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.opportunity import Opportunity, Task
from app.models.user import User
from app.services.ai_action_generator import generate_actions
from app.services.tenant_context import assert_same_tenant
from app.schemas.common import ItemsResponse, PaginatedResponse
from app.schemas.round15_pagination import NextBestActionRow
from app.schemas.round16_aggregates import NextBestActionDismissAck

router = APIRouter(prefix="/next-best-actions", tags=["Next Best Actions"])


class GenerateRequest(BaseModel):
    max_actions: int = Field(5, ge=1, le=10)


def _task_dict(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "opportunity_id": task.opportunity_id,
        "owner_id": task.owner_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "source": task.source,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


async def _load_opp(db: AsyncSession, opportunity_id: int, current_user: User) -> Opportunity:
    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if opp is None:
        raise NotFoundException("Firsat bulunamadi")
    assert_same_tenant(opp, current_user, exception_cls=NotFoundException)
    return opp


@router.get("/{opportunity_id}", response_model=PaginatedResponse[NextBestActionRow])
async def list_actions(
    opportunity_id: int,
    include_done: bool = Query(False, description="Include completed actions"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current AI-sourced action queue for an opportunity."""
    await _load_opp(db, opportunity_id, current_user)

    conditions = [Task.opportunity_id == opportunity_id, Task.source == "ai"]
    if not include_done:
        conditions.append(Task.status == "open")

    rows = (
        await db.execute(
            select(Task).where(and_(*conditions)).order_by(desc(Task.created_at)).limit(50)
        )
    ).scalars().all()
    items = [_task_dict(t) for t in rows]
    return {"items": items, "total": len(items), "page": 1, "page_size": len(items), "pages": 1 if items else 0}


@router.post("/{opportunity_id}/generate", status_code=201, response_model=ItemsResponse)
async def generate(
    opportunity_id: int,
    body: GenerateRequest = GenerateRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate fresh recommendations and persist them as tasks."""
    await _load_opp(db, opportunity_id, current_user)
    actions = await generate_actions(db, opportunity_id=opportunity_id, max_actions=body.max_actions)
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "items": actions,
        "total": len(actions),
    }


@router.post("/{opportunity_id}/{task_id}/dismiss", response_model=NextBestActionDismissAck)
async def dismiss(
    opportunity_id: int,
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss an NBA recommendation without completing it."""
    await _load_opp(db, opportunity_id, current_user)
    task = (
        await db.execute(
            select(Task).where(
                and_(Task.id == task_id, Task.opportunity_id == opportunity_id, Task.source == "ai")
            )
        )
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundException("Aksiyon bulunamadi")
    task.status = "dismissed"
    await db.flush()
    return _task_dict(task)
