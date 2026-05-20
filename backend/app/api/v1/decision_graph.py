"""Decision graph API.

Plan adoption — Phase 3 / Sprint 14 extension. Layer the structural
process graph on top of the existing decision_gaps detector.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services import decision_graph_service

router = APIRouter(prefix="/decision-graph", tags=["Decision Graph"])


def _require_decision_graph() -> None:
    """Round-8 R8-FLAG-4 — paired feature gate."""
    if not settings.FEATURE_DECISION_GRAPH:
        raise HTTPException(status_code=404, detail="Not found")


class NodeStatePatch(BaseModel):
    state: str = Field(..., description="not_started|in_progress|blocked|complete|skipped")
    blocker_reason: str | None = None


class DecisionGraphResponse(BaseModel):
    """Surface for /decision-graph/{opportunity_id} (and POST/PATCH siblings)."""

    opportunity_id: int | None = None
    nodes: list[dict] = []
    edges: list[dict] = []
    progress: dict | None = None

    model_config = {"extra": "allow"}


@router.get("/{opportunity_id}", response_model=DecisionGraphResponse)
async def get_graph(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_decision_graph),
):
    return await decision_graph_service.get_graph(db, opportunity_id, current_user)


@router.post("/{opportunity_id}/initialize", response_model=DecisionGraphResponse)
async def initialize(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_decision_graph),
):
    return await decision_graph_service.initialize_default(db, opportunity_id, current_user)


@router.patch("/{opportunity_id}/nodes/{node_id}", response_model=DecisionGraphResponse)
async def patch_node(
    opportunity_id: int,
    node_id: int,
    body: NodeStatePatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_decision_graph),
):
    return await decision_graph_service.update_node_state(
        db,
        opportunity_id,
        node_id,
        state=body.state,
        blocker_reason=body.blocker_reason,
        current_user=current_user,
    )
