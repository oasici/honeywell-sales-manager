"""Webhook management endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session, get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.core.exceptions import NotFoundException
from app.models.user import User
from app.models.webhook import WebhookDelivery, WebhookSubscription
from app.schemas.common import PaginatedResponse
from app.schemas.webhook import WebhookSubscriptionResponse
from app.schemas.round16_aggregates import (
    WebhookDeliveriesResponse,
    WebhookRetryResponse,
    WebhookTestResponse,
)
from app.services.tenant_context import assert_same_tenant, scoped_for_user
from app.services.webhook_service import WebhookService, validate_webhook_url

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _check_feature_flag() -> None:
    if not settings.FEATURE_WEBHOOKS:
        raise HTTPException(
            status_code=403,
            detail="Webhook ozelligi aktif degil.",
        )


class WebhookCreateRequest(BaseModel):
    name: str = Field(..., max_length=200)
    url: str = Field(..., max_length=500)
    event_types: list[str] = Field(..., min_length=1)
    secret: str | None = Field(None, max_length=255)


class WebhookUpdateRequest(BaseModel):
    name: str | None = Field(None, max_length=200)
    url: str | None = Field(None, max_length=500)
    event_types: list[str] | None = Field(None, min_length=1)
    secret: str | None = Field(None, max_length=255)
    is_active: bool | None = None


def _subscription_to_dict(sub: WebhookSubscription) -> dict:
    try:
        event_types = json.loads(sub.event_types)
    except (json.JSONDecodeError, TypeError):
        event_types = []

    # Round-4 R4-TEN-10 — never echo the HMAC secret back to the API.
    # Even managers within the tenant should not be able to retrieve
    # the secret value through GET; only an "is it set?" indicator.
    return {
        "id": sub.id,
        "tenant_id": getattr(sub, "tenant_id", None),
        "name": sub.name,
        "url": sub.url,
        "event_types": event_types,
        "secret_present": bool(sub.secret),
        "is_active": sub.is_active,
        "created_by": sub.created_by,
        "last_triggered_at": sub.last_triggered_at.isoformat() if sub.last_triggered_at else None,
        "failure_count": sub.failure_count,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
    }


def _delivery_to_dict(delivery: WebhookDelivery) -> dict:
    return {
        "id": delivery.id,
        "tenant_id": getattr(delivery, "tenant_id", None),
        "subscription_id": delivery.subscription_id,
        "event_type": delivery.event_type,
        "status_code": delivery.status_code,
        "response_body": delivery.response_body,
        "retry_count": delivery.retry_count,
        "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
    }


@router.get("/", response_model=PaginatedResponse[WebhookSubscriptionResponse])
async def list_webhooks(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Tum webhook aboneliklerini listele.

    Round-13 R13-API-1 → Sprint 7b — emit only the canonical pagination
    envelope. The legacy ``count`` / ``webhooks`` aliases that R13-API-1
    kept for migration were dropped here after every SPA consumer
    confirmed it reads ``items`` first (WebhookSettings.tsx reads
    ``data?.items ?? data?.webhooks``, so the second fallback is now
    dead code).
    """
    _check_feature_flag()

    stmt = scoped_for_user(
        select(WebhookSubscription),
        current_user,
        column=WebhookSubscription.tenant_id,
    )
    result = await db.execute(stmt.order_by(WebhookSubscription.created_at.desc()))
    subscriptions = result.scalars().all()
    items = [_subscription_to_dict(s) for s in subscriptions]

    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": len(items) if items else 0,
        "pages": 1 if items else 0,
    }


@router.post("/", status_code=201, response_model=WebhookSubscriptionResponse)
async def create_webhook(
    body: WebhookCreateRequest,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Yeni webhook aboneligi olustur."""
    _check_feature_flag()

    try:
        validate_webhook_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    subscription = WebhookSubscription(
        name=body.name,
        url=body.url,
        event_types=json.dumps(body.event_types),
        secret=body.secret,
        is_active=True,
        created_by=current_user.id,
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    db.add(subscription)
    await db.flush()
    await db.refresh(subscription)

    return _subscription_to_dict(subscription)


@router.get("/{webhook_id}", response_model=WebhookSubscriptionResponse)
async def get_webhook(
    webhook_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Webhook abonelik detayi."""
    _check_feature_flag()

    result = await db.execute(
        select(WebhookSubscription).where(WebhookSubscription.id == webhook_id)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise NotFoundException(f"Webhook bulunamadi: {webhook_id}")
    assert_same_tenant(subscription, current_user, exception_cls=NotFoundException)

    return _subscription_to_dict(subscription)


@router.patch("/{webhook_id}", response_model=WebhookSubscriptionResponse)
async def update_webhook(
    webhook_id: int,
    body: WebhookUpdateRequest,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Webhook aboneligini guncelle."""
    _check_feature_flag()

    result = await db.execute(
        select(WebhookSubscription).where(WebhookSubscription.id == webhook_id)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise NotFoundException(f"Webhook bulunamadi: {webhook_id}")
    assert_same_tenant(subscription, current_user, exception_cls=NotFoundException)

    if body.name is not None:
        subscription.name = body.name
    if body.url is not None:
        try:
            validate_webhook_url(body.url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        subscription.url = body.url
    if body.event_types is not None:
        subscription.event_types = json.dumps(body.event_types)
    if body.secret is not None:
        subscription.secret = body.secret
    if body.is_active is not None:
        subscription.is_active = body.is_active
        if body.is_active:
            subscription.failure_count = 0

    await db.flush()
    await db.refresh(subscription)

    return _subscription_to_dict(subscription)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Webhook aboneligini sil."""
    _check_feature_flag()

    result = await db.execute(
        select(WebhookSubscription).where(WebhookSubscription.id == webhook_id)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise NotFoundException(f"Webhook bulunamadi: {webhook_id}")
    assert_same_tenant(subscription, current_user, exception_cls=NotFoundException)

    await db.delete(subscription)


@router.get("/{webhook_id}/deliveries", response_model=WebhookDeliveriesResponse)
async def get_webhook_deliveries(
    webhook_id: int,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Webhook teslimat gecmisi."""
    _check_feature_flag()

    # Verify subscription exists *and* belongs to caller's tenant.
    sub_result = await db.execute(
        select(WebhookSubscription).where(WebhookSubscription.id == webhook_id)
    )
    subscription = sub_result.scalar_one_or_none()
    if subscription is None:
        raise NotFoundException(f"Webhook bulunamadi: {webhook_id}")
    assert_same_tenant(subscription, current_user, exception_cls=NotFoundException)

    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.subscription_id == webhook_id)
        .order_by(WebhookDelivery.delivered_at.desc())
        .limit(limit)
    )
    deliveries = result.scalars().all()

    return {
        "webhook_id": webhook_id,
        "count": len(deliveries),
        "deliveries": [_delivery_to_dict(d) for d in deliveries],
    }


@router.post("/deliveries/{delivery_id}/retry", response_model=WebhookRetryResponse)
async def retry_webhook_delivery(
    delivery_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Retry a failed webhook delivery."""
    _check_feature_flag()

    result = await db.execute(
        select(WebhookDelivery).where(WebhookDelivery.id == delivery_id)
    )
    delivery = result.scalar_one_or_none()
    if delivery is None:
        raise NotFoundException(f"Teslimat bulunamadi: {delivery_id}")
    assert_same_tenant(delivery, current_user, exception_cls=NotFoundException)

    max_retries = 5
    if delivery.retry_count >= max_retries:
        raise HTTPException(
            status_code=400,
            detail=f"Maksimum yeniden deneme sayisina ulasildi ({max_retries})",
        )

    try:
        sub_result = await db.execute(
            select(WebhookSubscription).where(
                WebhookSubscription.id == delivery.subscription_id
            )
        )
        subscription = sub_result.scalar_one_or_none()
        if not subscription:
            raise NotFoundException("Webhook aboneligi bulunamadi")
        assert_same_tenant(subscription, current_user, exception_cls=NotFoundException)

        from datetime import datetime, timezone

        validate_webhook_url(subscription.url)

        # Re-deliver using the same hardened delivery semantics (SSRF guard, redirects off, timeout).
        payload_obj = json.loads(delivery.payload_json)
        service = WebhookService(async_session)
        new_delivery = await service._deliver(db, subscription, delivery.event_type, payload_obj)

        delivery.status_code = new_delivery.status_code
        delivery.response_body = new_delivery.response_body
        delivery.retry_count += 1
        delivery.delivered_at = datetime.now(timezone.utc)
        await db.flush()

        is_success = (
            delivery.status_code is not None and 200 <= delivery.status_code < 300
        )
        return {
            "status": "delivered" if is_success else "failed",
            "status_code": delivery.status_code,
            "retry_count": delivery.retry_count,
        }

    except (ValueError, json.JSONDecodeError) as exc:
        delivery.retry_count += 1
        delivery.response_body = str(exc)[:1000]
        await db.flush()
        return {
            "status": "failed",
            "error": str(exc),
            "retry_count": delivery.retry_count,
        }

    except Exception as exc:
        delivery.retry_count += 1
        delivery.response_body = str(exc)[:1000]
        await db.flush()

        return {
            "status": "failed",
            "error": str(exc),
            "retry_count": delivery.retry_count,
        }


@router.post("/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Test etkinligi gonder."""
    _check_feature_flag()

    # Tenant guard before invoking the test fan-out service.
    sub_result = await db.execute(
        select(WebhookSubscription).where(WebhookSubscription.id == webhook_id)
    )
    subscription = sub_result.scalar_one_or_none()
    if subscription is None:
        raise NotFoundException(f"Webhook bulunamadi: {webhook_id}")
    assert_same_tenant(subscription, current_user, exception_cls=NotFoundException)

    service = WebhookService(async_session)
    result = await service.deliver_test(db, webhook_id)

    if not result["success"]:
        return {"status": "failed", **result}

    return {"status": "delivered", **result}
