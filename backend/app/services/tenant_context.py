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
