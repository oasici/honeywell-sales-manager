"""Guided Selling / CPQ Wizard API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import NotFoundException
from app.core.rate_limit import enforce_ai_rate_limit, enforce_tenant_ai_rate_limit
from app.models.enums import UserRole
from app.models.selling_guide import SellingGuide
from app.models.user import User
from app.services.guided_selling_service import GuidedSellingService

# R5-RL-8 — guided-selling wizard services may call Claude for product
# recommendation narratives.
router = APIRouter(
    tags=["Guided Selling (CPQ)"],
    dependencies=[
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


@router.get("/guided-selling/")
async def list_guides(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active selling guides."""
    service = GuidedSellingService(db)
    guides = await service.list_guides()
    return {"guides": guides}


@router.post("/guided-selling/", status_code=201)
async def create_guide(
    body: GuideCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a selling guide (manager only)."""
    service = GuidedSellingService(db)
    guide = await service.create_guide({
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
