"""Guided Selling / CPQ Wizard API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import NotFoundException
from app.core.rate_limit import enforce_ai_rate_limit, enforce_tenant_ai_rate_limit
from app.models.enums import UserRole
from app.models.selling_guide import SellingGuide
from app.models.user import User
from app.services.guided_selling_service import GuidedSellingService
from app.schemas.common import PaginatedResponse


def _require_guided_selling() -> None:
    """R7-API-9 — gate the entire router on the FEATURE_GUIDED_SELLING
    flag. CLAUDE.md ban: "never ship a frontend-only gate". Pre-fix the
    flag was declared in config + checked inside one handler in
    opportunities.py, but every other guided-selling endpoint was live
    regardless of flag state.
    """
    if not settings.FEATURE_GUIDED_SELLING:
        raise HTTPException(status_code=404, detail="Not found")


# R5-RL-8 — guided-selling wizard services may call Claude for product
# recommendation narratives.
router = APIRouter(
    tags=["Guided Selling (CPQ)"],
    dependencies=[
        Depends(_require_guided_selling),
        Depends(enforce_tenant_ai_rate_limit),
        Depends(enforce_ai_rate_limit),
    ],
)


class GuideCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    steps: list[dict] = Field(default_factory=list)
    product_rules: list[dict] = Field(default_factory=list)


class EvaluateBody(BaseModel):
    answers: dict


@router.get("/guided-selling/", response_model=PaginatedResponse[dict])
async def list_guides(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active selling guides."""
    service = GuidedSellingService(db)
    guides = await service.list_guides()
    # R7-API-4 — canonical pagination envelope.
    total = len(guides)
    return {
        "items": guides,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
    }


@router.post("/guided-selling/", status_code=201)
async def create_guide(
    body: GuideCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a selling guide (manager only)."""
    service = GuidedSellingService(db)
    guide = await service.create_guide({
        # Round-10 R10-DB-4 — tenant_id from the creating manager.
        "tenant_id": current_user.tenant_id,
        "name": body.name,
        "description": body.description,
        "steps": body.steps,
        "product_rules": body.product_rules,
        "created_by": current_user.id,
    })
    return {"id": guide.id, "name": guide.name}


@router.get("/guided-selling/{guide_id}")
async def get_guide(
    guide_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a guide with steps and rules."""
    service = GuidedSellingService(db)
    guide = await service.get_guide(guide_id)
    if not guide:
        raise NotFoundException("Rehber bulunamadi")
    return guide


@router.delete("/guided-selling/{guide_id}")
async def delete_guide(
    guide_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a guide by deactivating it."""
    guide = await db.get(SellingGuide, guide_id)
    if not guide:
        raise NotFoundException("Rehber bulunamadi")
    guide.is_active = False
    await db.flush()
    return {"message": "Rehber silindi"}


@router.post("/guided-selling/{guide_id}/evaluate")
async def evaluate_guide(
    guide_id: int,
    body: EvaluateBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate answers and return suggested products."""
    service = GuidedSellingService(db)
    result = await service.evaluate_step(guide_id, body.answers)
    return result
