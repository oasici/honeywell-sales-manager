"""F-007 — soft delete policy + helpers.

The Round-19 audit found the codebase mixed hard and soft delete
ad-hoc, with no documented policy. This module establishes the
canonical policy + the helpers every entity uses.

POLICY MATRIX
=============

============== ================  =================================
Entity         Strategy          Rationale
============== ================  =================================
users          soft+anonymise    Audit log integrity (referenced FKs)
customers      soft              Revenue history; KVKK request hook
leads          soft → hard 24mo  KVKK retention
opportunities  soft              Forecast history
quotes         soft              Audit chain
contracts      soft (never hard) TR legal retention 10y
invoices       soft (never hard) TR tax retention 10y
email_requests soft → hard 36mo  Volume management
notes          soft → hard 12mo  Volume management
ai_tasks       hard              Ephemeral
============== ================  =================================

Phase 4 ships the schema (deleted_at, deleted_by, delete_reason on
every "softable" table) + the universal helpers below. Phase 5
adds the retention cron that promotes soft→hard for the entities
with a TTL.

The helpers in this module are entity-agnostic — callers pass any
ORM row with the standard tombstone columns and we do the right
thing. Tenant scoping is the caller's responsibility (we don't load
the row here, just mutate it).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect


class SoftDeleteRefused(Exception):
    """Raised when a soft delete is blocked by dependent active rows."""

    def __init__(self, *, entity: str, id_: int, dependents: dict[str, int]):
        self.entity = entity
        self.id_ = id_
        self.dependents = dependents
        super().__init__(
            f"{entity}[{id_}] has dependent active rows: {dependents}"
        )


def is_soft_deletable(model: Any) -> bool:
    """Static check — does the model carry the tombstone columns?"""
    mapper = inspect(model)
    cols = {c.key for c in mapper.column_attrs}
    return {"deleted_at", "deleted_by"}.issubset(cols)


def is_deleted(row: Any) -> bool:
    """True iff the row is currently soft-deleted."""
    return getattr(row, "deleted_at", None) is not None


def mark_deleted(
    row: Any,
    *,
    actor_id: int | None,
    reason: str | None = None,
) -> None:
    """In-memory tombstone. Caller commits.

    Idempotent: marking an already-deleted row leaves ``deleted_at``
    unchanged (preserves the original deletion timestamp for audit).
    """
    if is_deleted(row):
        return
    row.deleted_at = datetime.now(timezone.utc)
    row.deleted_by = actor_id
    if reason:
        row.delete_reason = reason[:500]


def restore(row: Any) -> None:
    """Un-tombstone. Used by the "Trash → restore" admin flow."""
    row.deleted_at = None
    row.deleted_by = None
    row.delete_reason = None


def refuse_if_has_active(
    *,
    entity: str,
    id_: int,
    dependent_counts: dict[str, int],
    allow_force: bool = False,
) -> None:
    """Raise ``SoftDeleteRefused`` when any dependent has active rows.

    ``dependent_counts``: {"opportunities": 3, "quotes": 1} — caller
    computed these with active-only queries (excluding deleted rows).
    ``allow_force``: pass True for the "force_delete" privileged path.
    """
    if allow_force:
        return
    blocking = {k: v for k, v in dependent_counts.items() if v > 0}
    if blocking:
        raise SoftDeleteRefused(entity=entity, id_=id_, dependents=blocking)


def active_filter(model: Any):
    """SQLAlchemy clause: ``Model.deleted_at IS NULL``.

    Used by every list endpoint::

        stmt = select(Customer).where(active_filter(Customer))
    """
    return model.deleted_at.is_(None)


def anonymise_user_pii(user_row: Any) -> None:
    """Special case for users (F-007 policy: soft + anonymise after 30d).

    Replaces PII fields with stable but non-identifying placeholders.
    The user row itself stays so FK references (audit_log.user_id,
    customer.created_by) don't break.
    """
    uid = getattr(user_row, "id", "unknown")
    if hasattr(user_row, "email"):
        user_row.email = f"deleted-{uid}@anonymised.local"
    if hasattr(user_row, "full_name"):
        user_row.full_name = f"deleted-user-{uid}"
    if hasattr(user_row, "phone"):
        user_row.phone = None
    if hasattr(user_row, "password_hash"):
        # Bcrypt of a random string — no human can log in with this.
        import secrets

        user_row.password_hash = f"!disabled:{secrets.token_hex(16)}"
    if hasattr(user_row, "is_active"):
        user_row.is_active = False
