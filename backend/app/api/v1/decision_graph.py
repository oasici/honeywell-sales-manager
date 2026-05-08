"""Decision graph API.

Plan adoption — Phase 3 / Sprint 14 extension. Layer the structural
process graph on top of the existing decision_gaps detector.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services import decision_graph_service

router = APIRouter(prefix="/decision-graph", tags=["Decision Graph"])


class NodeStatePatch(BaseModel):
    state: str = Field(..., description="not_started|in_progress|blocked|complete|skipped")
    blocker_reason: str | None = None


@router.get("/{opportunity_id}")
async def get_graph(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await decision_graph_service.get_graph(db, opportunity_id, current_user)


@router.post("/{opportunity_id}/initialize")
async def initialize(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await decision_graph_service.initialize_default(db, opportunity_id, current_user)


@router.patch("/{opportunity_id}/nodes/{node_id}")
async def patch_node(
    opportunity_id: int,
    node_id: int,
    body: NodeStatePatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await decision_graph_service.update_node_state(
        db,
        opportunity_id,
        node_id,
        state=body.state,
        blocker_reason=body.blocker_reason,
        current_user=current_user,
    )
