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
    tenant_id: int | None = None,
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
        tenant_id: V13 — caller's tenant id, denormalised for fast
            forensics queries. When omitted, attempts to resolve from
            the user record so legacy callers don't need to plumb it.
    """
    try:
        changes_json = json.dumps(changes, ensure_ascii=False, default=str) if changes else None

        # If the caller didn't pass tenant_id but we have a user_id,
        # resolve it lazily — most callers already have the user
        # loaded but historically didn't propagate tenant. Cheap
        # lookup vs. forensics value (per-tenant audit queries).
        resolved_tenant_id = tenant_id
        if resolved_tenant_id is None and user_id is not None:
            try:
                from app.models.user import User

                user = await db.get(User, user_id)
                if user is not None:
                    resolved_tenant_id = getattr(user, "tenant_id", None)
            except Exception:
                pass  # never let audit lookups break the main operation

        entry = AuditLog(
            user_id=user_id,
            tenant_id=resolved_tenant_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes_json,
            ip_address=ip_address,
        )
        db.add(entry)
        await db.flush()

        logger.debug(
            "Audit log: user=%s tenant=%s action=%s entity=%s/%d",
            user_id,
            resolved_tenant_id,
            action,
            entity_type,
            entity_id,
        )
    except Exception as exc:
        # Audit logging should never break the main operation
        logger.error("Failed to create audit log entry: %s", exc)
