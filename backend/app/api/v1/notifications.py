"""Notification API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.notification import Notification
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.notification_service import get_notifications, mark_as_read
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/notifications", tags=["Notifications"])

DEFAULT_NOTIFICATION_LIMIT = 20
MAX_NOTIFICATION_LIMIT = 100


@router.get("/", response_model=PaginatedResponse[dict])
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(DEFAULT_NOTIFICATION_LIMIT, ge=1, le=MAX_NOTIFICATION_LIMIT),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List notifications for the current user."""
    notifications = await get_notifications(
        db,
        user_id=current_user.id,
        unread_only=unread_only,
        limit=limit,
    )
    # R7-API-4 — canonical pagination envelope. Pre-fix the SPA had to
    # special-case the {notifications:[]} shape. ``notifications`` is
    # also kept as an alias for the bell-icon header consumer that
    # hasn't migrated yet.
    total = len(notifications)
    return {
        "items": notifications,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
        # Legacy alias — drop once the header has migrated.
        "notifications": notifications,
    }


@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the number of unread notifications for badge display."""
    # Round-11 R11-AUTH-3 — tenant scope alongside user_id.
    conditions = [
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    ]
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is not None:
        conditions.append(Notification.tenant_id == tenant_id)
    stmt = select(func.count()).select_from(Notification).where(*conditions)
    result = await db.execute(stmt)
    count = result.scalar() or 0
    return {"unread_count": count}


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    await mark_as_read(
        db,
        notification_id=notification_id,
        user_id=current_user.id,
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    await db.flush()
    return {"message": "Notification marked as read"}


# ── Push Notification Subscriptions ──


class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(..., min_length=1)
    keys_json: str = Field(..., min_length=2)


@router.post("/push-subscribe", status_code=201)
async def push_subscribe(
    body: PushSubscribeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a Web Push subscription for the current user."""
    # Check if this endpoint is already registered
    existing = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == current_user.id,
            PushSubscription.endpoint == body.endpoint,
        )
    )
    if existing.scalar_one_or_none():
        return {"message": "Abonelik zaten kayitli"}

    subscription = PushSubscription(
        user_id=current_user.id,
        endpoint=body.endpoint,
        keys_json=body.keys_json,
    )
    db.add(subscription)
    await db.flush()

    return {"message": "Push aboneligi kaydedildi", "id": subscription.id}


@router.delete("/push-unsubscribe")
async def push_unsubscribe(
    endpoint: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a Web Push subscription."""
    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == current_user.id,
            PushSubscription.endpoint == endpoint,
        )
    )
    subscription = result.scalar_one_or_none()
    if not subscription:
        raise HTTPException(status_code=404, detail="Push aboneligi bulunamadi")

    await db.delete(subscription)
    await db.flush()

    return {"message": "Push aboneligi kaldirildi"}


@router.patch("/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications as read for the current user."""
    from sqlalchemy import update

    # Round-11 R11-AUTH-3 — tenant scope alongside user_id.
    conditions = [
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    ]
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is not None:
        conditions.append(Notification.tenant_id == tenant_id)
    stmt = update(Notification).where(*conditions).values(is_read=True)
    result = await db.execute(stmt)
    await db.flush()
    return {"message": f"{result.rowcount} notification(s) marked as read"}
