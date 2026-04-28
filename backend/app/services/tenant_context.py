"""Tenant context resolution + scoping helpers (V7).

V7 lays the multi-tenant *analytics* boundary: ``tenants`` table +
``tenant_id`` columns on V5/V6 analytics tables. CRM tables (
opportunities, customers, users) are intentionally untouched until
their own dedicated migration project.

This module provides the boundary helpers:

- ``current_tenant_id()`` — FastAPI dependency. Returns the resolved
  tenant id from the request (header/JWT claim/User row) or ``None``
  in single-tenant deployments.
- ``scoped(stmt, tenant_id, *, column)`` — returns ``stmt`` with a
  ``WHERE column == tenant_id`` filter when ``tenant_id`` is set, or
  ``stmt`` unchanged otherwise. So call sites can opt into the
  filter without branching on the deployment mode.
- ``ensure_tenant`` — convenience that creates a default Tenant row
  on first call so single-tenant test fixtures don't need to.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v7_tenant import Tenant

logger = logging.getLogger(__name__)


# ─────────────────────── FastAPI dependency ──────────────────────────


async def current_tenant_id(
    x_tenant_id: int | None = Header(default=None, alias="X-Tenant-Id"),
) -> int | None:
    """Resolve the current tenant id from the request headers.

    Single-tenant deployments don't send the header; this returns
    ``None`` and downstream services keep operating across the whole
    dataset.
    """
    return x_tenant_id


# ─────────────────────── query scoping ───────────────────────────────


def scoped(stmt, tenant_id: int | None, *, column):
    """Add a ``column == tenant_id`` filter to ``stmt`` when set.

    ``column`` must be the SQLAlchemy ``Column`` reference for the
    table involved (e.g. ``DnaPattern.tenant_id``). When ``tenant_id``
    is ``None`` the statement is returned unchanged so single-tenant
    callers get the same behaviour as before V7.
    """
    if tenant_id is None:
        return stmt
    return stmt.where(column == tenant_id)


# ─────────────────────── helpers ─────────────────────────────────────


async def ensure_tenant(
    db: AsyncSession,
    *,
    name: str,
    region: str | None = None,
    plan_tier: str = "standard",
) -> Tenant:
    """Idempotent tenant lookup-or-create. Useful for bootstrap."""
    existing = (
        await db.execute(select(Tenant).where(Tenant.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    tenant = Tenant(name=name, region=region, plan_tier=plan_tier)
    db.add(tenant)
    await db.flush()
    return tenant


# ─────────────────────── federated boundary ──────────────────────────


def derive_tenant_count(source_tenant_ids: list[int]) -> int:
    """Honest tenant count for federated benchmark publishing.

    Federated benchmarks must report the number of *distinct* tenants
    contributing — ``len(source_tenant_ids)`` could include duplicates
    when the same tenant produced multiple rows during aggregation.
    """
    return len({int(t) for t in source_tenant_ids if t is not None})


# ─────────────────────── V8 CRM-side helpers ──────────────────────────


def scoped_for_user(stmt, user, *, column):
    """Scope a CRM query to the user's tenant.

    Drop-in replacement for ``scoped()`` when the caller already has a
    User row. Returns the stmt unchanged when ``user.tenant_id`` is
    None (single-tenant deployments).
    """
    if user is None:
        return stmt
    tenant_id = getattr(user, "tenant_id", None)
    return scoped(stmt, tenant_id, column=column)


async def resolve_tenant_id(
    db: AsyncSession,
    *,
    header_tenant_id: int | None,
    user_tenant_id: int | None,
) -> int | None:
    """Pick the effective tenant id from the request signals.

    Header wins (admin tooling can target any tenant), falls back to
    the requesting user's tenant_id. ``None`` for both = the deployment
    is single-tenant, return None and downstream filters become no-ops.
    """
    if header_tenant_id is not None:
        return header_tenant_id
    if user_tenant_id is not None:
        return user_tenant_id
    return None


def is_cross_tenant(record: Any, user: Any) -> bool:
    """Return True when ``record`` belongs to a tenant other than ``user``'s.

    Used by detail/update/delete endpoints to convert cross-tenant
    accesses into 404s, so ID enumeration is indistinguishable from
    "not found". Single-tenant deployments (user.tenant_id is None,
    record.tenant_id is None) always return False.

    The function is intentionally tolerant: if either side is missing
    the attribute (e.g. a model that hasn't been migrated yet), we
    treat the access as same-tenant. Migrations roll out independently
    of code, so a transient mismatch should not break the API.
    """
    if record is None or user is None:
        return False
    user_tenant = getattr(user, "tenant_id", None)
    record_tenant = getattr(record, "tenant_id", None)
    if user_tenant is None or record_tenant is None:
        return False
    return user_tenant != record_tenant


def assert_same_tenant(record: Any, user: Any, *, exception_cls: Any) -> None:
    """Raise ``exception_cls`` when ``record`` is cross-tenant for ``user``.

    Pass ``NotFoundException`` (or your project's 404 class). Caller
    decides the message; we deliberately don't import the exception
    here to keep this module dependency-free for tests.
    """
    if is_cross_tenant(record, user):
        raise exception_cls("Not found")
