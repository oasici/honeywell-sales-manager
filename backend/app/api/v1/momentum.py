"""Deal momentum API.

Plan adoption — Phase 3 / Sprint 12 (Deal Momentum Engine).
Storage lives in ``opportunity_features_daily`` (populated nightly by
``feature_store_builder``). This router exposes a focused read API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services import momentum_service
from app.schemas.common import PaginatedResponse
from app.schemas.round15_pagination import MomentumHistoryRow
from app.schemas.round16_aggregates import (
    MomentumCurrentResponse,
    MomentumDistributionResponse,
)

router = APIRouter(prefix="/momentum", tags=["Momentum"])


@router.get("/distribution", response_model=MomentumDistributionResponse)
async def get_distribution(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cohort momentum bands across all open deals (tenant-scoped)."""
    return await momentum_service.get_momentum_distribution(db, current_user)


@router.get("/{opportunity_id}", response_model=MomentumCurrentResponse)
async def get_current(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Latest momentum snapshot + drivers for one deal."""
    return await momentum_service.get_current_momentum(db, opportunity_id, current_user)


@router.get("/{opportunity_id}/history", response_model=PaginatedResponse[MomentumHistoryRow])
async def get_history(
    opportunity_id: int,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Daily momentum series (chronological)."""
    items = await momentum_service.get_momentum_history(db, opportunity_id, current_user, days=days)
    return {"items": items, "total": len(items), "page": 1, "page_size": len(items), "pages": 1 if items else 0}
