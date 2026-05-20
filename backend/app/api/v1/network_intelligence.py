"""Network Intelligence API.

Plan adoption — Phase 5 / Sprints 21-24 unified read façade.
Composes existing benchmark services into manager-facing insight cards.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.models.user import User
from app.services import network_intelligence_service
from app.schemas.common import PaginatedResponse
from app.schemas.round15_pagination import NetworkSegmentRow, FederatedBenchmarkRow

router = APIRouter(prefix="/network-intelligence", tags=["Network Intelligence"])


def _require_network_intelligence() -> None:
    """Round-8 R8-FLAG-2 — paired feature gate."""
    if not settings.FEATURE_NETWORK_INTELLIGENCE:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/segments", response_model=PaginatedResponse[NetworkSegmentRow])
async def list_segments(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_network_intelligence),
):
    items = await network_intelligence_service.list_segments(db, current_user)
    return {"items": items, "total": len(items), "page": 1, "page_size": len(items), "pages": 1 if items else 0}


@router.get("/overview")
async def get_overview(
    segment_key: str | None = Query(None, description="Segment key (e.g. 'stage:qualified')"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_network_intelligence),
):
    """Manager insight cards: tenant vs. segment median across the 5 key metrics."""
    return await network_intelligence_service.get_segment_overview(
        db, current_user, segment_key=segment_key
    )


@router.get("/federated/{benchmark_key}", response_model=PaginatedResponse[FederatedBenchmarkRow])
async def get_federated(
    benchmark_key: str,
    include_suppressed: bool = Query(False),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_network_intelligence),
):
    items = await network_intelligence_service.list_federated(
        db, current_user, benchmark_key=benchmark_key, include_suppressed=include_suppressed
    )
    return {"items": items, "total": len(items), "page": 1, "page_size": len(items), "pages": 1 if items else 0}
