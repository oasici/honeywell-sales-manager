"""V13 audit_logs.tenant_id forensics — tests.

Covers:
- ``log_action`` auto-resolves tenant_id from the user record when
  the caller doesn't pass it.
- Audit list endpoint scopes results to ``current_user.tenant_id``
  (cross-tenant leakage blocked at the read path too).
- Single-tenant deployments (user.tenant_id is None) keep seeing
  every row, matching legacy behaviour.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.v7_tenant import Tenant
from app.services.audit_service import log_action


# ─────────────────────── helpers ─────────────────────────────────────


async def _seed_tenant(db: AsyncSession, name: str) -> Tenant:
    t = Tenant(name=name, region="TR", plan_tier="standard")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def _seed_user(
    db: AsyncSession, *, email: str, role: str = "sales_manager",
    tenant_id: int | None = None,
) -> User:
    u = User(
        email=email,
        full_name="Test",
        hashed_password=hash_password("x"),
        role=role,
        is_active=True,
        tenant_id=tenant_id,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


# ─────────────────────── log_action service tests ────────────────────


@pytest.mark.asyncio
async def test_log_action_auto_resolves_tenant_id_from_user(db: AsyncSession):
    t = await _seed_tenant(db, "T-resolve")
    u = await _seed_user(db, email="resolve@test.com", tenant_id=t.id)

    await log_action(
        db,
        user_id=u.id,
        action="test_action",
        entity_type="quote",
        entity_id=99,
    )
    await db.commit()

    rows = (
        await db.execute(
            select(AuditLog).where(AuditLog.user_id == u.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].tenant_id == t.id


@pytest.mark.asyncio
async def test_log_action_explicit_tenant_id_wins(db: AsyncSession):
    t1 = await _seed_tenant(db, "T-explicit-1")
    t2 = await _seed_tenant(db, "T-explicit-2")
    u = await _seed_user(db, email="explicit@test.com", tenant_id=t1.id)

    # System action overrides the user's tenant — used by cron jobs
    # that operate across tenants but want the audit row tagged.
    await log_action(
        db,
        user_id=u.id,
        action="cron_audit",
        entity_type="opportunity",
        entity_id=1,
        tenant_id=t2.id,
    )
    await db.commit()

    row = (
        await db.execute(
            select(AuditLog).where(AuditLog.action == "cron_audit")
        )
    ).scalar_one()
    assert row.tenant_id == t2.id  # explicit wins over auto-resolve


@pytest.mark.asyncio
async def test_log_action_with_null_user_keeps_tenant_null(db: AsyncSession):
    """System actions (user_id=None) without an explicit tenant_id
    leave tenant_id NULL — there's nothing to auto-resolve from."""
    await log_action(
        db,
        user_id=None,
        action="system_cleanup",
        entity_type="cron",
        entity_id=0,
    )
    await db.commit()

    row = (
        await db.execute(
            select(AuditLog).where(AuditLog.action == "system_cleanup")
        )
    ).scalar_one()
    assert row.tenant_id is None


# ─────────────────────── list endpoint scoping ───────────────────────


@pytest.mark.asyncio
async def test_audit_list_scoped_to_caller_tenant(
    client: AsyncClient, db: AsyncSession
):
    t1 = await _seed_tenant(db, "List-T1")
    t2 = await _seed_tenant(db, "List-T2")
    mgr_a = await _seed_user(db, email="list-a@test.com", tenant_id=t1.id)
    mgr_b = await _seed_user(db, email="list-b@test.com", tenant_id=t2.id)

    # Seed audit rows in each tenant.
    await log_action(
        db, user_id=mgr_a.id, action="alpha_action",
        entity_type="customer", entity_id=1,
    )
    await log_action(
        db, user_id=mgr_b.id, action="beta_action",
        entity_type="customer", entity_id=2,
    )
    await db.commit()

    r = await client.get("/api/v1/audit/", headers=_auth(mgr_a))
    assert r.status_code == 200
    actions = {item["action"] for item in r.json()["items"]}
    assert "alpha_action" in actions
    assert "beta_action" not in actions  # Beta's row hidden from Alpha


@pytest.mark.asyncio
async def test_audit_list_unscoped_for_legacy_user(
    client: AsyncClient, db: AsyncSession
):
    """A user with tenant_id=NULL (legacy single-tenant) sees every
    audit row regardless of tenant_id, matching pre-V13 behaviour.
    """
    mgr_legacy = await _seed_user(db, email="legacy-mgr@test.com", tenant_id=None)
    t1 = await _seed_tenant(db, "Legacy-T1")
    other_user = await _seed_user(
        db, email="other@test.com", tenant_id=t1.id
    )
    await log_action(
        db, user_id=other_user.id, action="other_action",
        entity_type="customer", entity_id=10,
    )
    await db.commit()

    r = await client.get("/api/v1/audit/", headers=_auth(mgr_legacy))
    assert r.status_code == 200
    actions = {item["action"] for item in r.json()["items"]}
    assert "other_action" in actions  # legacy user sees the tenant'd row
