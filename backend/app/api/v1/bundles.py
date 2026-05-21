"""Product Bundles API — CPQ bundle management and expansion."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import NotFoundException
from app.models.enums import UserRole
from app.models.product_bundle import ProductBundle
from app.models.spare_part import SparePart
from app.models.user import User
from app.services.tenant_context import assert_same_tenant, scoped_for_user
from app.schemas.common import MessageResponse
from app.schemas.round16_aggregates import (
    BundleCreateAckResponse,
    BundleExpandResponse,
    BundleListResponse,
)

router = APIRouter(tags=["Bundles (CPQ)"])


class BundleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    items: list[dict]  # [{spare_part_id, quantity}]
    bundle_price: float | None = None
    discount_pct: float = 0.0


@router.get("/bundles/", response_model=BundleListResponse)
async def list_bundles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active product bundles."""
    # Round-4 R4-TEN-15 — scope bundle catalog by tenant.
    query = scoped_for_user(
        select(ProductBundle).where(ProductBundle.is_active.is_(True)).order_by(ProductBundle.name),
        current_user,
        column=ProductBundle.tenant_id,
    )
    result = await db.execute(query)
    bundles = result.scalars().all()
    return {
        "bundles": [
            {
                "id": b.id,
                # Round-4 R4-DTO-6 — round-trip tenant_id (R4-TEN-15).
                "tenant_id": getattr(b, "tenant_id", None),
                "name": b.name,
                "description": b.description,
                "items": json.loads(b.items_json) if b.items_json else [],
                "bundle_price": b.bundle_price,
                "discount_pct": b.discount_pct,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in bundles
        ],
    }


@router.post("/bundles/", status_code=201, response_model=BundleCreateAckResponse)
async def create_bundle(
    body: BundleCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a product bundle (manager only)."""
    bundle = ProductBundle(
        tenant_id=getattr(current_user, "tenant_id", None),
        name=body.name,
        description=body.description,
        items_json=json.dumps(body.items, ensure_ascii=False),
        bundle_price=body.bundle_price,
        discount_pct=body.discount_pct,
    )
    db.add(bundle)
    await db.flush()
    await db.refresh(bundle)
    return {"id": bundle.id, "name": bundle.name}


@router.delete("/bundles/{bundle_id}", response_model=MessageResponse)
async def delete_bundle(
    bundle_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a bundle by deactivating it."""
    bundle = (await db.execute(
        select(ProductBundle).where(ProductBundle.id == bundle_id),
    )).scalar_one_or_none()
    if not bundle:
        raise NotFoundException("Paket bulunamadi")
    # Round-4 R4-TEN-15 — block deactivating a foreign tenant's bundle.
    assert_same_tenant(bundle, current_user, exception_cls=NotFoundException)
    bundle.is_active = False
    await db.flush()
    return {"message": "Paket silindi"}


@router.post("/bundles/{bundle_id}/to-quote-items", response_model=BundleExpandResponse)
async def expand_bundle_to_quote_items(
    bundle_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Expand a bundle into individual quote items with prices."""
    bundle = (await db.execute(
        select(ProductBundle).where(ProductBundle.id == bundle_id),
    )).scalar_one_or_none()
    if not bundle:
        raise NotFoundException("Paket bulunamadi")
    # Round-4 R4-TEN-15 — block expanding a foreign tenant's bundle.
    assert_same_tenant(bundle, current_user, exception_cls=NotFoundException)

    items = json.loads(bundle.items_json) if bundle.items_json else []
    quote_items = []

    for item in items:
        spare_part_id = item.get("spare_part_id")
        quantity = item.get("quantity", 1)

        part = (await db.execute(
            select(SparePart).where(SparePart.id == spare_part_id),
        )).scalar_one_or_none()

        if part:
            unit_price = part.supplier_price or part.transfer_price or 0
            quote_items.append({
                "spare_part_id": part.id,
                "honeywell_code": part.honeywell_code,
                "description": part.name_tr or part.name_en,
                "quantity": quantity,
                "unit_price": unit_price,
                "discount_pct": bundle.discount_pct,
            })

    return {"items": quote_items, "bundle_name": bundle.name}
