"""V12 multi-tenant enforcement — end-to-end API tests.

Complements ``test_v12_multi_tenant_enforcement.py`` (helper-level
unit tests) with full HTTP cycle coverage:

- Two real users in two real tenants.
- POST creates inherit the caller's ``tenant_id``.
- GET list scopes results to the caller's tenant.
- GET / PATCH detail returns 404 when probing a sibling tenant's id
  (cross-tenant access is indistinguishable from "not found").
- Single-tenant deployments (tenant_id NULL) keep old behaviour
  — the helpers are no-ops.

These tests ARE database-backed and rely on the PG test container
(see ``conftest.py``) so the FK constraints behave the same as
production.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.user import User
from app.models.v7_tenant import Tenant


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


@pytest_asyncio.fixture(autouse=True)
def _enable_v2_board():
    """V12 enforcement is wired through opportunities/customers/leads
    endpoints which sit behind FEATURE_V2_BOARD on the opportunity side.
    Patch the flag for the duration of these tests.
    """
    with patch("app.api.v1.opportunities.settings") as ms:
        ms.FEATURE_V2_BOARD = True
        yield


async def _seed_tenant(db: AsyncSession, name: str) -> Tenant:
    tenant = Tenant(name=name, region="TR", plan_tier="standard")
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def _seed_user(
    db: AsyncSession, *, email: str, tenant_id: int | None
) -> User:
    user = User(
        email=email,
        full_name="V12 E2E User",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
        tenant_id=tenant_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seed_opportunity(
    db: AsyncSession, *, owner_id: int, title: str, tenant_id: int | None
) -> Opportunity:
    opp = Opportunity(
        title=title,
        stage="prospecting",
        status="active",
        owner_id=owner_id,
        tenant_id=tenant_id,
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


# ─────────────────────── opportunity scoping ─────────────────────────


@pytest.mark.asyncio
async def test_opportunity_list_scoped_to_caller_tenant(
    client: AsyncClient, db: AsyncSession
):
    """User A in tenant 1 should only see tenant 1's opportunities."""
    t1 = await _seed_tenant(db, "Tenant Alpha")
    t2 = await _seed_tenant(db, "Tenant Beta")
    user_a = await _seed_user(db, email="alpha-mgr@test.com", tenant_id=t1.id)
    user_b = await _seed_user(db, email="beta-mgr@test.com", tenant_id=t2.id)

    await _seed_opportunity(db, owner_id=user_a.id, title="Alpha Deal", tenant_id=t1.id)
    await _seed_opportunity(db, owner_id=user_b.id, title="Beta Deal", tenant_id=t2.id)

    r = await client.get("/api/v1/opportunities/", headers=_auth(user_a))
    assert r.status_code == 200
    titles = {item["title"] for item in r.json()["items"]}
    assert "Alpha Deal" in titles
    assert "Beta Deal" not in titles


@pytest.mark.asyncio
async def test_opportunity_detail_cross_tenant_returns_404(
    client: AsyncClient, db: AsyncSession
):
    """Cross-tenant ID probe must look like 'not found'."""
    t1 = await _seed_tenant(db, "T1")
    t2 = await _seed_tenant(db, "T2")
    user_a = await _seed_user(db, email="a-detail@test.com", tenant_id=t1.id)
    user_b = await _seed_user(db, email="b-detail@test.com", tenant_id=t2.id)
    opp_b = await _seed_opportunity(
        db, owner_id=user_b.id, title="Beta Secret", tenant_id=t2.id
    )

    # User A probes B's opportunity — must be 404, not 403, so the API
    # cannot leak whether the ID exists in another tenant.
    r = await client.get(
        f"/api/v1/opportunities/{opp_b.id}", headers=_auth(user_a)
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_opportunity_create_propagates_caller_tenant(
    client: AsyncClient, db: AsyncSession
):
    """POST should set tenant_id from the caller, not from the body."""
    t1 = await _seed_tenant(db, "Tenant Create-Test")
    user_a = await _seed_user(db, email="create-mgr@test.com", tenant_id=t1.id)

    r = await client.post(
        "/api/v1/opportunities/",
        json={"title": "Newly Created"},
        headers=_auth(user_a),
    )
    assert r.status_code == 201
    new_id = r.json()["id"]

    # Reload from DB and confirm the row has the caller's tenant.
    from sqlalchemy import select

    opp = (
        await db.execute(
            select(Opportunity).where(Opportunity.id == new_id)
        )
    ).scalar_one()
    assert opp.tenant_id == t1.id


@pytest.mark.asyncio
async def test_opportunity_update_cross_tenant_returns_404(
    client: AsyncClient, db: AsyncSession
):
    """PATCH on a sibling-tenant opportunity must 404, not 403/200."""
    t1 = await _seed_tenant(db, "T1-update")
    t2 = await _seed_tenant(db, "T2-update")
    user_a = await _seed_user(db, email="a-update@test.com", tenant_id=t1.id)
    user_b = await _seed_user(db, email="b-update@test.com", tenant_id=t2.id)
    opp_b = await _seed_opportunity(
        db, owner_id=user_b.id, title="Beta Original", tenant_id=t2.id
    )

    r = await client.patch(
        f"/api/v1/opportunities/{opp_b.id}",
        json={"title": "Hijacked"},
        headers=_auth(user_a),
    )
    assert r.status_code == 404

    # Sanity: the row was NOT modified.
    await db.refresh(opp_b)
    assert opp_b.title == "Beta Original"


# ─────────────────────── customer scoping ────────────────────────────


@pytest.mark.asyncio
async def test_customer_detail_cross_tenant_returns_404(
    client: AsyncClient, db: AsyncSession
):
    t1 = await _seed_tenant(db, "T1-cust")
    t2 = await _seed_tenant(db, "T2-cust")
    user_a = await _seed_user(db, email="cust-a@test.com", tenant_id=t1.id)
    cust_b = Customer(
        name="Beta Co",
        email="beta-co@test.com",
        company="Beta",
        tenant_id=t2.id,
    )
    db.add(cust_b)
    await db.commit()
    await db.refresh(cust_b)

    r = await client.get(
        f"/api/v1/customers/{cust_b.id}", headers=_auth(user_a)
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_customer_create_propagates_caller_tenant(
    client: AsyncClient, db: AsyncSession
):
    t1 = await _seed_tenant(db, "Tenant Cust-Create")
    user_a = await _seed_user(db, email="cust-mgr@test.com", tenant_id=t1.id)

    r = await client.post(
        "/api/v1/customers/",
        json={
            "name": "New Cust",
            "email": "new-cust@test.com",
            "company": "NC Inc",
        },
        headers=_auth(user_a),
    )
    assert r.status_code == 201
    cust_id = r.json()["id"]

    from sqlalchemy import select

    cust = (
        await db.execute(select(Customer).where(Customer.id == cust_id))
    ).scalar_one()
    assert cust.tenant_id == t1.id


# ─────────────────────── single-tenant compatibility ──────────────────


@pytest.mark.asyncio
async def test_single_tenant_user_unaffected_by_v12(
    client: AsyncClient, db: AsyncSession
):
    """A user with tenant_id=NULL must still see all unscoped data.

    This is the legacy single-tenant deployment path. The helpers
    treat ``user.tenant_id is None`` as a no-op so we don't break
    existing installs that haven't run the bootstrap script.
    """
    legacy_user = await _seed_user(db, email="legacy@test.com", tenant_id=None)
    await _seed_opportunity(
        db, owner_id=legacy_user.id, title="Legacy Deal", tenant_id=None
    )

    r = await client.get("/api/v1/opportunities/", headers=_auth(legacy_user))
    assert r.status_code == 200
    titles = {item["title"] for item in r.json()["items"]}
    assert "Legacy Deal" in titles
