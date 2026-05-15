from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.feature_store_builder import build_daily_feature_store


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _create_user(db: AsyncSession, email: str, role: str) -> User:
    u = User(
        tenant_id=_TENANT_ID,
        email=email,
        full_name=f"Test {role}",
        hashed_password=hash_password("Test1234"),
        role=role,
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


@pytest.fixture(autouse=True)
def _enable_v4_flag():
    with patch("app.api.v1.network_benchmarks.settings") as ms:
        ms.FEATURE_V4_FEATURE_STORE = True
        yield


@pytest.mark.asyncio
async def test_segments_latest_and_gap_endpoint(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "nb_mgr@test.com", "sales_manager")
    cust = Customer(tenant_id=_TENANT_ID, name="ACME", company="ACME", email="acme@test.com", phone="", address="", tax_id="")
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    opp = Opportunity(
        tenant_id=_TENANT_ID,
        customer_id=cust.id,
        owner_id=mgr.id,
        title="Deal",
        stage="qualified",
        status="active",
        amount=1000,
        currency="TRY",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    await build_daily_feature_store(db)

    # manager list
    r = await client.get("/api/v1/v4/benchmarks/segments/latest", headers=_auth(mgr))
    assert r.status_code == 200

    # gap
    g = await client.get(f"/api/v1/v4/benchmarks/opportunities/{opp.id}/gap", headers=_auth(mgr))
    assert g.status_code == 200

