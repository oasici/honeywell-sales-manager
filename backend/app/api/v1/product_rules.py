"""Product rules API — CRUD for catalog rules (volume discounts, bundles, etc.)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.enums import UserRole
from app.models.user import User
from app.services.product_rule_service import ProductRuleService

router = APIRouter(prefix="/product-rules", tags=["Product Rules"])


def _require_product_rules():
    """Dependency: reject if FEATURE_PRODUCT_RULES is off."""
    if not getattr(settings, "FEATURE_PRODUCT_RULES", False):
        raise HTTPException(status_code=404, detail="Not found")


# ── Schemas ──

class ProductRuleCreate(BaseModel):
    spare_part_id: int | None = None
    category: str | None = None
    rule_type: str = Field(..., min_length=1, max_length=30)
    condition_json: str = Field(..., min_length=2)
    action_json: str = Field(..., min_length=2)
    priority: int = 0
    is_active: bool = True


class ProductRuleEvaluateItem(BaseModel):
    spare_part_id: int | None = None
    category: str | None = None
    quantity: int = Field(1, ge=1)
    unit_price: float = Field(0.0, ge=0)


# ── Endpoints ──

@router.get("/")
async def list_product_rules(
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_product_rules),
):
    """List all product rules."""
    service = ProductRuleService(db)
    rules = await service.list_rules()
    return {
        "items": [_rule_to_dict(r) for r in rules],
    }


@router.post("/", status_code=201)
async def create_product_rule(
    data: ProductRuleCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_product_rules),
):
    """Create a new product rule (manager only)."""
    service = ProductRuleService(db)
    rule = await service.create_rule(
        spare_part_id=data.spare_part_id,
        category=data.category,
        rule_type=data.rule_type,
        condition_json=data.condition_json,
        action_json=data.action_json,
        priority=data.priority,
        is_active=data.is_active,
    )
    return _rule_to_dict(rule)


@router.delete("/{rule_id}")
async def delete_product_rule(
    rule_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_product_rules),
):
    """Delete a product rule (manager only)."""
    service = ProductRuleService(db)
    await service.delete_rule(rule_id)
    return {"message": "Urun kurali silindi"}


@router.post("/evaluate")
async def evaluate_rules(
    data: ProductRuleEvaluateItem,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_product_rules),
):
    """Evaluate rules for a single item (preview)."""
    service = ProductRuleService(db)
    actions = await service.evaluate_for_item(
        spare_part_id=data.spare_part_id,
        category=data.category,
        quantity=data.quantity,
        unit_price=data.unit_price,
    )
    return {"actions": actions}


# ── Helper ──

def _rule_to_dict(rule) -> dict:
    import json

    return {
        "id": rule.id,
        "spare_part_id": rule.spare_part_id,
        "category": rule.category,
        "rule_type": rule.rule_type,
        "condition_json": json.loads(rule.condition_json) if rule.condition_json else None,
        "action_json": json.loads(rule.action_json) if rule.action_json else None,
        "priority": rule.priority,
        "is_active": rule.is_active,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }
