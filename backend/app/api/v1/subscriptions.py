from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.user import User
from app.services.subscription_service import SubscriptionService


def _require_subscriptions() -> None:
    """Round-5 R5-FLAG-15 — gate behind FEATURE_SUBSCRIPTIONS."""
    if not settings.FEATURE_SUBSCRIPTIONS:
        raise HTTPException(status_code=404, detail="Not found")


router = APIRouter(
    prefix="/subscriptions",
    tags=["Subscriptions"],
    dependencies=[Depends(_require_subscriptions)],
)


class SubscriptionCreate(BaseModel):
    customer_id: int
    quote_id: int | None = None
    name: str
    billing_cycle: str = "monthly"
    start_date: str
    end_date: str | None = None
    mrr: float = 0.0
    auto_renew: bool = True
    items_json: str | None = None
    currency: str = "TRY"


class SubscriptionUpdate(BaseModel):
    """R7-FORM-2 — pre-fix the SPA had no Subscription edit path; the
    backend was missing the schema and PATCH route entirely.

    All fields are optional so partial updates work the way the inline
    edit panel needs (only fields the user touches go on the wire).
    """

    name: str | None = None
    billing_cycle: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    mrr: float | None = None
    auto_renew: bool | None = None
    items_json: str | None = None
    currency: str | None = None
    quote_id: int | None = None


def _serialize(sub) -> dict:
    # R5-RENDER-SUB-1 — surface customer summary so the list / detail
    # view can render the customer name instead of "#${customer_id}".
    # Mirrors the R5-API-1 invoice fix.
    customer_summary: dict | None = None
    if getattr(sub, "customer", None) is not None:
        customer_summary = {
            "id": sub.customer.id,
            "name": sub.customer.name,
            "company": sub.customer.company,
        }
    data = {
        "id": sub.id,
        # Round-4 R4-DTO-5 — round-trip tenant_id (R4-TEN-7).
        "tenant_id": getattr(sub, "tenant_id", None),
        "customer_id": sub.customer_id,
        "customer": customer_summary,
        "quote_id": sub.quote_id,
        "name": sub.name,
        "status": sub.status,
        "billing_cycle": sub.billing_cycle,
        "start_date": sub.start_date.isoformat() if sub.start_date else None,
        "end_date": sub.end_date.isoformat() if sub.end_date else None,
        "mrr": sub.mrr,
        "next_renewal_date": sub.next_renewal_date.isoformat() if sub.next_renewal_date else None,
        "auto_renew": sub.auto_renew,
        "items_json": sub.items_json,
        "currency": sub.currency,
        "created_by": sub.created_by,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
        "updated_at": sub.updated_at.isoformat() if sub.updated_at else None,
    }
    # R5-PERM-1 — admin-configured field-permission rules apply here.
    from app.services.field_permission_service import apply_request_perms

    return apply_request_perms(data, "subscription")


@router.get("/mrr-dashboard")
async def mrr_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Round-4 R4-TEN-7 — dashboard now sums only the caller's tenant
    # (was a global rollup that leaked competitive intelligence
    # between tenants).
    service = SubscriptionService(db)
    return await service.get_mrr_dashboard(current_user)


@router.get("/renewals")
async def upcoming_renewals(
    days: int = Query(30, ge=1, le=365),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Round-5 Phase 7 — canonical pagination envelope.

    Service still returns the full filtered list; we slice in Python
    because the renewal window is bounded (max ~365 days, single
    tenant) and the row count is naturally small. Adding cursor-level
    pagination would require a service rewrite without measurable win.
    """
    import math as _math

    service = SubscriptionService(db)
    subs = await service.get_upcoming_renewals(current_user, days=days)
    total = len(subs)
    offset = (page - 1) * page_size
    page_items = subs[offset : offset + page_size]
    return {
        "items": [_serialize(s) for s in page_items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": _math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/")
async def list_subscriptions(
    customer_id: int | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Round-5 Phase 7 — canonical pagination envelope."""
    import math as _math

    service = SubscriptionService(db)
    subs = await service.list_subscriptions(
        current_user, customer_id=customer_id, status=status
    )
    total = len(subs)
    offset = (page - 1) * page_size
    page_items = subs[offset : offset + page_size]
    return {
        "items": [_serialize(s) for s in page_items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": _math.ceil(total / page_size) if total > 0 else 0,
    }


@router.post("/")
async def create_subscription(
    body: SubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.create_subscription(body.model_dump(), current_user)
    await db.commit()
    return _serialize(sub)


@router.get("/{sub_id}")
async def get_subscription(
    sub_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.get_subscription(sub_id, current_user)
    if sub is None:
        raise NotFoundException("Abonelik bulunamadi")
    return _serialize(sub)


@router.patch("/{sub_id}")
async def update_subscription(
    sub_id: int,
    body: SubscriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """R7-FORM-2 — partial subscription update. The service helper runs
    `assert_same_tenant` internally, so cross-tenant access maps to 404."""
    service = SubscriptionService(db)
    sub = await service.get_subscription(sub_id, current_user)
    if sub is None:
        raise NotFoundException("Abonelik bulunamadi")

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise BadRequestException("Guncellenecek alan bulunamadi")

    # Coerce ISO date strings the SPA emits into date objects on the
    # ORM side. Accept either YYYY-MM-DD or full ISO datetime.
    for date_field in ("start_date", "end_date"):
        if date_field in update_data and update_data[date_field] is not None:
            raw = update_data[date_field]
            try:
                if isinstance(raw, str) and len(raw) == 10:
                    update_data[date_field] = date.fromisoformat(raw)
                elif isinstance(raw, str):
                    update_data[date_field] = datetime.fromisoformat(raw).date()
            except ValueError:
                raise BadRequestException(
                    f"Gecersiz tarih: {date_field}={raw}"
                )

    for key, value in update_data.items():
        setattr(sub, key, value)

    await db.commit()
    await db.refresh(sub)
    return _serialize(sub)


@router.post("/{sub_id}/cancel")
async def cancel_subscription(
    sub_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.get_subscription(sub_id, current_user)
    if sub is None:
        raise NotFoundException("Abonelik bulunamadi")
    await service.cancel_subscription(sub_id, current_user)
    await db.commit()
    return {"status": "cancelled"}


@router.post("/{sub_id}/renew")
async def renew_subscription(
    sub_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.renew_subscription(sub_id, current_user)
    if sub is None:
        raise NotFoundException("Abonelik bulunamadi")
    await db.commit()
    return _serialize(sub)
