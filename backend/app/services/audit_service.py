"""Audit logging service."""

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def log_action(
    db: AsyncSession,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int,
    changes: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Create an audit log entry.

    Args:
        db: Database session.
        user_id: ID of the user performing the action (None for system actions).
        action: Action performed (e.g., 'create', 'update', 'delete', 'approve').
        entity_type: Type of entity (e.g., 'quote', 'customer', 'spare_part').
        entity_id: ID of the entity.
        changes: Optional dict describing what changed.
        ip_address: Optional IP address of the request.
    """
    try:
        changes_json = json.dumps(changes, ensure_ascii=False, default=str) if changes else None

        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes_json,
            ip_address=ip_address,
        )
        db.add(entry)
        await db.flush()

        logger.debug(
            "Audit log: user=%s action=%s entity=%s/%d",
            user_id,
            action,
            entity_type,
            entity_id,
        )
    except Exception as exc:
        # Audit logging should never break the main operation
        logger.error("Failed to create audit log entry: %s", exc)
