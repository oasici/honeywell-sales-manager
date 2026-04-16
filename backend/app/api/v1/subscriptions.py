from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.user import User
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


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


def _serialize(sub) -> dict:
    return {
        "id": sub.id,
        "customer_id": sub.customer_id,
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


@router.get("/mrr-dashboard")
async def mrr_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    return await service.get_mrr_dashboard()


@router.get("/renewals")
async def upcoming_renewals(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    subs = await service.get_upcoming_renewals(days)
    return {"items": [_serialize(s) for s in subs]}


@router.get("/")
async def list_subscriptions(
    customer_id: int | None = Query(None),
    status: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    subs = await service.list_subscriptions(customer_id=customer_id, status=status)
    return {"items": [_serialize(s) for s in subs]}


@router.post("/")
async def create_subscription(
    body: SubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.create_subscription(body.model_dump(), current_user.id)
    await db.commit()
    return _serialize(sub)


@router.get("/{sub_id}")
async def get_subscription(
    sub_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.get_subscription(sub_id)
    if sub is None:
        raise NotFoundException("Abonelik bulunamadi")
    return _serialize(sub)


@router.post("/{sub_id}/cancel")
async def cancel_subscription(
    sub_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.get_subscription(sub_id)
    if sub is None:
        raise NotFoundException("Abonelik bulunamadi")
    await service.cancel_subscription(sub_id)
    await db.commit()
    return {"status": "cancelled"}


@router.post("/{sub_id}/renew")
async def renew_subscription(
    sub_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SubscriptionService(db)
    sub = await service.renew_subscription(sub_id)
    if sub is None:
        raise NotFoundException("Abonelik bulunamadi")
    await db.commit()
    return _serialize(sub)
