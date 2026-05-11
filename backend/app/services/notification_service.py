"""User notification service."""

import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    user_id: int,
    type: str,
    title: str,
    message: str = "",
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> None:
    """Create a notification for a user.

    Args:
        db: Database session.
        user_id: Target user ID.
        type: Notification type (e.g., 'new_email', 'quote_approved', 'system').
        title: Short notification title.
        message: Optional longer message body.
        entity_type: Optional related entity type.
        entity_id: Optional related entity ID.

    Round-10 R10-DB-5 — Notification.tenant_id is NOT NULL; look it up
    from the target user (single point of write so callers don't have
    to pass tenant_id through every layer).
    """
    try:
        target = (
            await db.execute(select(User.tenant_id).where(User.id == user_id))
        ).scalar_one_or_none()
        if target is None:
            logger.warning("create_notification: target user %d not found", user_id)
            return
        notification = Notification(
            tenant_id=target,
            user_id=user_id,
            type=type,
            title=title,
            message=message or None,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        db.add(notification)
        await db.flush()

        logger.debug(
            "Notification created: user=%d type=%s title='%s'",
            user_id,
            type,
            title,
        )
    except Exception as exc:
        logger.error("Failed to create notification: %s", exc)


async def get_notifications(
    db: AsyncSession,
    user_id: int,
    unread_only: bool = False,
    limit: int = 20,
) -> list[dict]:
    """Get notifications for a user.

    Args:
        db: Database session.
        user_id: Target user ID.
        unread_only: If True, return only unread notifications.
        limit: Maximum number of notifications to return.

    Returns:
        List of notification dicts.
    """
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )

    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))

    result = await db.execute(stmt)
    notifications = result.scalars().all()

    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "entity_type": n.entity_type,
            "entity_id": n.entity_id,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]


async def mark_as_read(
    db: AsyncSession,
    notification_id: int,
    user_id: int,
    tenant_id: int | None = None,
) -> None:
    """Mark a notification as read.

    Args:
        db: Database session.
        notification_id: Notification ID to mark.
        user_id: User ID (for ownership verification).
        tenant_id: Caller tenant (Round-11 R11-AUTH-3). When provided,
            the update is additionally scoped to ``Notification.tenant_id``
            so a user_id collision across tenants cannot tamper with
            foreign notifications.
    """
    conditions = [Notification.id == notification_id, Notification.user_id == user_id]
    if tenant_id is not None:
        conditions.append(Notification.tenant_id == tenant_id)
    stmt = update(Notification).where(*conditions).values(is_read=True)
    await db.execute(stmt)
    await db.flush()
    logger.debug("Notification %d marked as read for user %d", notification_id, user_id)
