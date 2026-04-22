"""Field-level audit trail - SQLAlchemy ``before_flush`` listener.

The listener is installed once at app startup (main.py lifespan) when
``FEATURE_FIELD_AUDIT`` is true. It iterates over every dirty ORM object
in the flush, detects which attributes actually changed, and inserts a
``field_audit_logs`` row per change.

Actor resolution:
    - If the session has an ``actor_id`` attribute set (request middleware
      assigns it) we use that + ``actor_kind`` stored alongside.
    - Otherwise the row is recorded with ``actor_kind="system"``.

Excluded attributes:
    - Relationship collections (we only track scalar columns).
    - ``updated_at`` timestamps — too noisy.
    - Anything listed under ``FIELD_AUDIT_EXCLUDE`` class attribute on the
      model (opt-out per model).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)


# Columns we never want in the audit trail (too noisy / rotating secrets).
_GLOBAL_EXCLUDES: frozenset[str] = frozenset(
    {
        "updated_at",
        "created_at",
        "last_seen_at",
        "hashed_password",
        "refresh_token",
        "access_token",
        "credentials_encrypted",
        "csrf_token",
    }
)

# Tables whose rows are pure audit logs themselves — avoid infinite loops.
_GLOBAL_EXCLUDE_TABLES: frozenset[str] = frozenset(
    {
        "field_audit_logs",
        "audit_logs",
        "domain_events",
        "notifications",
        "erp_sync_jobs",
    }
)


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    try:
        import json

        return json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _collect_changes(obj: Any) -> list[tuple[str, Any, Any]]:
    inspector = inspect(obj)
    changes: list[tuple[str, Any, Any]] = []
    for attr in inspector.attrs:  # type: ignore[union-attr]
        key = attr.key
        if key in _GLOBAL_EXCLUDES:
            continue
        history = attr.load_history()
        if not history.has_changes():
            continue
        old_values = list(history.deleted or [])
        new_values = list(history.added or [])
        old_value = old_values[0] if old_values else None
        new_value = new_values[0] if new_values else None
        if old_value == new_value:
            continue
        changes.append((key, old_value, new_value))
    return changes


def _on_before_flush(session: Session, flush_context: Any, instances: Any) -> None:
    if not settings.FEATURE_FIELD_AUDIT:
        return

    from app.models.field_audit import FieldAuditLog

    actor_id: int | None = getattr(session, "audit_actor_id", None)
    actor_kind: str = getattr(session, "audit_actor_kind", "system")
    correlation_id: str | None = getattr(session, "audit_correlation_id", None)

    queued_rows: list[FieldAuditLog] = []
    for obj in list(session.dirty):
        if not session.is_modified(obj, include_collections=False):
            continue
        table = getattr(obj, "__tablename__", None)
        if table in _GLOBAL_EXCLUDE_TABLES:
            continue

        entity_id = getattr(obj, "id", None)
        if entity_id is None:
            continue
        per_model_excludes = set(getattr(obj, "FIELD_AUDIT_EXCLUDE", ()))
        for field, old_value, new_value in _collect_changes(obj):
            if field in per_model_excludes:
                continue
            queued_rows.append(
                FieldAuditLog(
                    entity_type=table,
                    entity_id=int(entity_id),
                    field_name=field,
                    old_value=_stringify(old_value),
                    new_value=_stringify(new_value),
                    actor_id=actor_id,
                    actor_kind=actor_kind,
                    correlation_id=correlation_id,
                )
            )

    if queued_rows:
        session.add_all(queued_rows)


_installed = False


def install_field_audit_listener() -> None:
    """Attach the before_flush listener once. Idempotent."""
    global _installed
    if _installed:
        return
    event.listen(Session, "before_flush", _on_before_flush)
    _installed = True
    logger.info("Field audit listener installed (FEATURE_FIELD_AUDIT on)")
