"""Relationship graph API.

Plan adoption — strategic primitive. Surfaces the relationship graph
that powers champion detection, multi-thread coverage, and influence
mapping.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services import relationship_service
from app.schemas.common import PaginatedResponse
from app.schemas.round15_pagination import RelationshipEdgeRow

router = APIRouter(prefix="/relationships", tags=["Relationships"])

VALID_KINDS = {"user", "stakeholder", "account", "opportunity"}


def _validate_kind(kind: str) -> str:
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=400, detail=f"Invalid kind: {kind}")
    return kind


@router.get("/edges/{kind}/{entity_id}", response_model=PaginatedResponse[RelationshipEdgeRow])
async def list_edges(
    kind: str,
    entity_id: int,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_kind(kind)
    items = await relationship_service.get_edges_for_endpoint(
        db, kind=kind, entity_id=entity_id, current_user=current_user, limit=limit
    )
    return {"items": items, "total": len(items), "page": 1, "page_size": len(items), "pages": 1 if items else 0}


@router.get("/score/{kind}/{entity_id}")
async def get_score(
    kind: str,
    entity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_kind(kind)
    return await relationship_service.get_score_for_endpoint(
        db, kind=kind, entity_id=entity_id, current_user=current_user
    )


@router.get("/strongest/{kind}/{entity_id}", response_model=PaginatedResponse[RelationshipEdgeRow])
async def list_strongest(
    kind: str,
    entity_id: int,
    limit: int = Query(5, ge=1, le=25),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_kind(kind)
    items = await relationship_service.get_strongest_connections(
        db,
        target_kind=kind,
        target_id=entity_id,
        current_user=current_user,
        limit=limit,
    )
    return {"items": items, "total": len(items), "page": 1, "page_size": len(items), "pages": 1 if items else 0}


@router.post("/rebuild/opportunity/{opportunity_id}")
async def rebuild_opportunity(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await relationship_service.rebuild_edges_for_opportunity(
        db, opportunity_id=opportunity_id, current_user=current_user
    )
