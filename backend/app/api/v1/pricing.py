"""Advanced pricing API — tiered pricing and customer-specific contracted prices."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.customer import Customer
from app.models.price_entry import PriceEntry
from app.models.pricing import CustomerPricing, PriceTier
from app.models.spare_part import SparePart
from app.models.user import User
from app.services.tenant_context import assert_same_tenant, scoped_for_user
from app.schemas.common import PaginatedResponse
from app.schemas.round15_pagination import PriceTierRow

router = APIRouter(prefix="/pricing", tags=["Pricing (Advanced)"])


# ── Schemas ──

class PriceTierCreate(BaseModel):
    price_entry_id: int
    min_qty: int = 1
    max_qty: int | None = None
    unit_price: float
    discount_pct: float = 0.0


class CustomerPricingCreate(BaseModel):
    spare_part_id: int
    contracted_price: float
    currency: str = "TRY"
    discount_pct: float = 0.0
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    notes: str | None = None


class CustomerPricingUpdate(BaseModel):
    contracted_price: float | None = None
    currency: str | None = None
    discount_pct: float | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    notes: str | None = None


# ── Helper ──

def _serialize_tier(t: PriceTier) -> dict:
    return {
        "id": t.id,
        "price_entry_id": t.price_entry_id,
        "min_qty": t.min_qty,
        "max_qty": t.max_qty,
        "unit_price": t.unit_price,
        "discount_pct": t.discount_pct,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _serialize_customer_pricing(cp: CustomerPricing) -> dict:
    return {
        "id": cp.id,
        # Round-4 R4-DTO-6 — round-trip tenant_id (R4-TEN-15).
        "tenant_id": getattr(cp, "tenant_id", None),
        "customer_id": cp.customer_id,
        "spare_part_id": cp.spare_part_id,
        "contracted_price": cp.contracted_price,
        "currency": cp.currency,
        "discount_pct": cp.discount_pct,
        "valid_from": cp.valid_from.isoformat() if cp.valid_from else None,
        "valid_until": cp.valid_until.isoformat() if cp.valid_until else None,
        "notes": cp.notes,
        "created_by": cp.created_by,
        "created_at": cp.created_at.isoformat() if cp.created_at else None,
        "updated_at": cp.updated_at.isoformat() if cp.updated_at else None,
    }


# ══════════════════════════════════════════
# TIERED PRICING
# ══════════════════════════════════════════

@router.get("/tiers/{price_entry_id}", response_model=PaginatedResponse[PriceTierRow])
async def list_tiers(
    price_entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all quantity-break tiers for a price entry."""
    tiers = (
        await db.execute(
            select(PriceTier)
            .where(PriceTier.price_entry_id == price_entry_id)
            .order_by(PriceTier.min_qty.asc())
        )
    ).scalars().all()
    items = [_serialize_tier(t) for t in tiers]
    total = len(items)
    # R7-API-4 — canonical pagination envelope; legacy keys retained.
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
        "price_entry_id": price_entry_id,
        "tiers": items,
    }


@router.post("/tiers", status_code=201)
async def create_tier(
    body: PriceTierCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a quantity-break tier for a price entry."""
    price_entry = (
        await db.execute(select(PriceEntry).where(PriceEntry.id == body.price_entry_id))
    ).scalar_one_or_none()
    if not price_entry:
        raise HTTPException(status_code=404, detail="Price entry not found")

    tier = PriceTier(
        price_entry_id=body.price_entry_id,
        min_qty=body.min_qty,
        max_qty=body.max_qty,
        unit_price=body.unit_price,
        discount_pct=body.discount_pct,
    )
    db.add(tier)
    await db.commit()
    await db.refresh(tier)
    return _serialize_tier(tier)


@router.delete("/tiers/{tier_id}", status_code=204)
async def delete_tier(
    tier_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a price tier."""
    tier = (
        await db.execute(select(PriceTier).where(PriceTier.id == tier_id))
    ).scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=404, detail="Price tier not found")
    await db.delete(tier)
    await db.commit()


# ══════════════════════════════════════════
# CUSTOMER CONTRACTED PRICING
# ══════════════════════════════════════════

async def _load_customer_for_tenant(
    db: AsyncSession, customer_id: int, current_user: User
) -> Customer:
    """Load a Customer and refuse cross-tenant access.

    Round-4 R4-TEN-15 — the customer-pricing endpoints previously
    matched ``CustomerPricing.customer_id == customer_id`` without ever
    confirming the customer belonged to the requesting tenant.
    """
    customer = (
        await db.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if customer is None:
        raise NotFoundException("Customer not found")
    assert_same_tenant(customer, current_user, exception_cls=NotFoundException)
    return customer


@router.get("/customer/{customer_id}")
async def list_customer_pricing(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all contracted prices for a customer."""
    await _load_customer_for_tenant(db, customer_id, current_user)
    query = scoped_for_user(
        select(CustomerPricing)
        .where(CustomerPricing.customer_id == customer_id)
        .order_by(CustomerPricing.created_at.desc()),
        current_user,
        column=CustomerPricing.tenant_id,
    )
    rows = (await db.execute(query)).scalars().all()
    return {
        "customer_id": customer_id,
        "pricing": [_serialize_customer_pricing(cp) for cp in rows],
    }


@router.post("/customer/{customer_id}", status_code=201)
async def create_customer_pricing(
    customer_id: int,
    body: CustomerPricingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a contracted price for a customer / spare part pair."""
    await _load_customer_for_tenant(db, customer_id, current_user)
    cp = CustomerPricing(
        tenant_id=getattr(current_user, "tenant_id", None),
        customer_id=customer_id,
        spare_part_id=body.spare_part_id,
        contracted_price=body.contracted_price,
        currency=body.currency,
        discount_pct=body.discount_pct,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        notes=body.notes,
        created_by=current_user.id,
    )
    db.add(cp)
    await db.commit()
    await db.refresh(cp)
    return _serialize_customer_pricing(cp)


@router.put("/customer/{customer_id}/{pricing_id}")
async def update_customer_pricing(
    customer_id: int,
    pricing_id: int,
    body: CustomerPricingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a contracted price record."""
    await _load_customer_for_tenant(db, customer_id, current_user)
    cp = (
        await db.execute(
            select(CustomerPricing).where(
                CustomerPricing.id == pricing_id,
                CustomerPricing.customer_id == customer_id,
            )
        )
    ).scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=404, detail="Customer pricing record not found")
    assert_same_tenant(cp, current_user, exception_cls=NotFoundException)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(cp, field, value)

    await db.commit()
    await db.refresh(cp)
    return _serialize_customer_pricing(cp)


@router.delete("/customer/{customer_id}/{pricing_id}", status_code=204)
async def delete_customer_pricing(
    customer_id: int,
    pricing_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a contracted price record."""
    await _load_customer_for_tenant(db, customer_id, current_user)
    cp = (
        await db.execute(
            select(CustomerPricing).where(
                CustomerPricing.id == pricing_id,
                CustomerPricing.customer_id == customer_id,
            )
        )
    ).scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=404, detail="Customer pricing record not found")
    assert_same_tenant(cp, current_user, exception_cls=NotFoundException)
    await db.delete(cp)
    await db.commit()


# ══════════════════════════════════════════
# MARGIN RULES
# ══════════════════════════════════════════


class MarginUpdate(BaseModel):
    min_margin_pct: float


@router.patch("/margin/{spare_part_id}")
async def update_margin(
    spare_part_id: int,
    body: MarginUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update minimum margin percentage for a spare part."""
    part = (
        await db.execute(select(SparePart).where(SparePart.id == spare_part_id))
    ).scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail="Spare part not found")
    if body.min_margin_pct < 0 or body.min_margin_pct > 100:
        raise HTTPException(status_code=400, detail="Marj degeri 0-100 arasinda olmalidir")

    part.min_margin_pct = body.min_margin_pct
    await db.commit()
    await db.refresh(part)

    return {"id": part.id, "honeywell_code": part.honeywell_code, "min_margin_pct": part.min_margin_pct}


# ══════════════════════════════════════════
# PRICE LOOKUP
# ══════════════════════════════════════════

@router.get("/lookup")
async def lookup_price(
    spare_part_id: int,
    customer_id: int,
    quantity: int = 1,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve the best unit price for a (spare_part, customer, quantity) combination.

    Resolution order:
    1. Customer contracted price (if active).
    2. Tier pricing matched by quantity.
    3. Standard net price from the latest active price entry.
    """
    now = datetime.now(timezone.utc)

    # 1. Customer contracted price — round-4 R4-TEN-15: scope by tenant.
    cp = (
        await db.execute(
            scoped_for_user(
                select(CustomerPricing).where(
                    CustomerPricing.customer_id == customer_id,
                    CustomerPricing.spare_part_id == spare_part_id,
                ),
                current_user,
                column=CustomerPricing.tenant_id,
            )
        )
    ).scalar_one_or_none()

    if cp:
        is_valid = True
        if cp.valid_from and cp.valid_from > now:
            is_valid = False
        if cp.valid_until and cp.valid_until < now:
            is_valid = False
        if is_valid:
            return {
                "source": "customer_contract",
                "unit_price": cp.contracted_price,
                "discount_pct": cp.discount_pct,
                "currency": cp.currency,
            }

    # 2. Tier pricing — find latest price entry, then match tier
    price_entry = (
        await db.execute(
            select(PriceEntry)
            .where(PriceEntry.spare_part_id == spare_part_id)
            .order_by(PriceEntry.created_at.desc())
        )
    ).scalars().first()

    if price_entry:
        tiers = (
            await db.execute(
                select(PriceTier)
                .where(PriceTier.price_entry_id == price_entry.id)
                .order_by(PriceTier.min_qty.asc())
            )
        ).scalars().all()

        matched_tier: PriceTier | None = None
        for tier in tiers:
            if tier.min_qty <= quantity:
                if tier.max_qty is None or tier.max_qty >= quantity:
                    matched_tier = tier

        if matched_tier:
            return {
                "source": "tier",
                "unit_price": matched_tier.unit_price,
                "discount_pct": matched_tier.discount_pct,
                "currency": price_entry.currency,
            }

        # 3. Standard price entry net price
        return {
            "source": "standard",
            "unit_price": price_entry.net_price,
            "discount_pct": price_entry.discount_pct,
            "currency": price_entry.currency,
        }

    # No price found at all
    spare_part = (
        await db.execute(select(SparePart).where(SparePart.id == spare_part_id))
    ).scalar_one_or_none()
    if not spare_part:
        raise HTTPException(status_code=404, detail="Spare part not found")

    raise HTTPException(status_code=404, detail="No price found for this spare part")
