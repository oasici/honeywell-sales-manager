"""F-011 — Operations role split.

Pre-Round-19 a single ``operations`` role could:
  - manage users
  - edit field permissions
  - read audit logs
  - manage integrations (secrets)
  - merge entities
  - run KVKK exports
  - edit pricing
  - edit workflow rules

That's a god account. The Round-19 audit demanded separation-of-
duties; this module ships the *minimum-viable* split for 20-30
users:

    ops_users         — User CRUD, password reset, role grants
    ops_data          — Custom fields, workflow rules, merge, imports
    ops_billing       — Invoices, payments, pricing, subscriptions
    ops_audit         — READ-ONLY access to audit logs + ops dashboards

A single human can hold multiple sub-roles; existing ``operations``
users are auto-granted ``ops_users + ops_data + ops_billing`` by
the Phase 4 migration so nothing breaks. ``ops_audit`` is *not*
auto-granted — it's an explicit choice by Ops leadership.

Routes still check the legacy single role via
``require_role(UserRole.OPERATIONS)`` for backward compat. Over
Phase 5+ those calls migrate to ``require_any_role("ops_users")``
etc. (one route at a time).

This module is intentionally small — it's the *policy* layer.
``has_role()`` reads from the new ``user_roles`` table; the
many-to-many model is in ``app/models/user_role.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# Stable enum-string identifiers. NEVER renumber / rename. Migrations
# inserted these literally during the Phase 4 backfill.
ROLE_SALES_REP        = "sales_rep"
ROLE_SALES_MANAGER    = "sales_manager"
ROLE_OPS_USERS        = "ops_users"
ROLE_OPS_DATA         = "ops_data"
ROLE_OPS_BILLING      = "ops_billing"
ROLE_OPS_AUDIT        = "ops_audit"
# Legacy umbrella role. Still present in users.role for backward
# compat; new code prefers the sub-roles via has_role() / has_any().
ROLE_OPERATIONS       = "operations"


# What used to be "operations" decomposes into these sub-roles.
LEGACY_OPS_SUBROLES: FrozenSet[str] = frozenset(
    {ROLE_OPS_USERS, ROLE_OPS_DATA, ROLE_OPS_BILLING}
)


# Conflict flags surfaced in the UI when an admin grants two roles
# that violate segregation of duties. The grant is still *allowed*
# (Ops can override) but the UI shows a warning.
SOD_CONFLICTS: tuple[tuple[str, str, str], ...] = (
    (ROLE_OPS_AUDIT, ROLE_OPS_USERS,
     "Read-only auditor should not also manage users (no self-review)."),
    (ROLE_OPS_AUDIT, ROLE_OPS_BILLING,
     "Read-only auditor should not also manage billing."),
    (ROLE_OPS_AUDIT, ROLE_OPS_DATA,
     "Read-only auditor should not also manage data / merges."),
)


@dataclass(frozen=True)
class SodViolation:
    role_a: str
    role_b: str
    explanation: str


def find_sod_violations(roles: set[str]) -> list[SodViolation]:
    """Pure function. Returns the conflicts present in a role set."""
    violations: list[SodViolation] = []
    for a, b, msg in SOD_CONFLICTS:
        if a in roles and b in roles:
            violations.append(SodViolation(role_a=a, role_b=b, explanation=msg))
    return violations


async def get_user_roles(db: AsyncSession, user_id: int) -> set[str]:
    """Return every role the user holds.

    Includes the legacy ``users.role`` value so any code path still
    checking ``user.role == 'operations'`` works alongside the new
    sub-roles.
    """
    rows = await db.execute(
        text("SELECT role FROM user_roles WHERE user_id = :uid"),
        {"uid": user_id},
    )
    result = {row[0] for row in rows.fetchall()}
    # Also pick up the legacy column.
    legacy = await db.execute(
        text("SELECT role FROM users WHERE id = :uid"),
        {"uid": user_id},
    )
    legacy_row = legacy.first()
    if legacy_row and legacy_row[0]:
        result.add(legacy_row[0])
        # Synthetic expansion: if user.role='operations' but the new
        # user_roles table doesn't have the sub-roles yet (partial
        # migration / new user inserted with old API), pretend the
        # sub-roles are present.
        if legacy_row[0] == ROLE_OPERATIONS:
            result.update(LEGACY_OPS_SUBROLES)
    return result


async def has_role(db: AsyncSession, user_id: int, role: str) -> bool:
    """True iff the user holds ``role``."""
    return role in await get_user_roles(db, user_id)


async def has_any(db: AsyncSession, user_id: int, *roles: str) -> bool:
    """True iff the user holds at least one of ``roles``."""
    held = await get_user_roles(db, user_id)
    return bool(held & set(roles))


async def grant_role(
    db: AsyncSession,
    *,
    user_id: int,
    role: str,
    granted_by: int | None,
) -> None:
    """Idempotent grant. UNIQUE constraint makes double-grant a no-op."""
    await db.execute(
        text(
            """
            INSERT INTO user_roles (user_id, role, granted_by)
            VALUES (:uid, :role, :by)
            ON CONFLICT (user_id, role) DO NOTHING
            """
        ),
        {"uid": user_id, "role": role, "by": granted_by},
    )
    await db.flush()


async def revoke_role(
    db: AsyncSession, *, user_id: int, role: str
) -> None:
    """Remove a single role grant."""
    await db.execute(
        text(
            "DELETE FROM user_roles WHERE user_id = :uid AND role = :role"
        ),
        {"uid": user_id, "role": role},
    )
    await db.flush()
