from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.sequence_v2 import Stakeholder
from app.models.user import User
from app.services.decision_gap_service import rebuild_decision_gaps_for_opportunity


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
    with patch("app.api.v1.decision_gaps.settings") as ms:
        ms.FEATURE_V4_FEATURE_STORE = True
        yield


@pytest.mark.asyncio
async def test_gap_engine_creates_missing_economic(db: AsyncSession):
    mgr = await _create_user(db, "dg_mgr@test.com", "sales_manager")
    cust = Customer(tenant_id=_TENANT_ID, name="ACME", company="ACME", email="acme@test.com", phone="", address="", tax_id="")
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    opp = Opportunity(
        tenant_id=_TENANT_ID,
        customer_id=cust.id,
        owner_id=mgr.id,
        title="Deal",
        stage="proposal",
        status="active",
        amount=1000,
        currency="TRY",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    # Only technical stakeholder → should miss economic/champion
    db.add(
        Stakeholder(
            opportunity_id=opp.id,
            customer_id=cust.id,
            name="Tech Person",
            department_group="tech",
            buyer_role="influencer",
        )
    )
    await db.commit()

    gaps = await rebuild_decision_gaps_for_opportunity(db, opportunity_id=int(opp.id))
    assert any(g.gap_type == "missing_economic" for g in gaps) or any(
        g.gap_type == "missing_economic_buyer" for g in gaps
    )


@pytest.mark.asyncio
async def test_decision_gaps_endpoint_lists(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "dg_mgr2@test.com", "sales_manager")
    cust = Customer(tenant_id=_TENANT_ID, name="ACME2", company="ACME2", email="acme2@test.com", phone="", address="", tax_id="")
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    opp = Opportunity(
        tenant_id=_TENANT_ID,
        customer_id=cust.id,
        owner_id=mgr.id,
        title="Deal2",
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

    await rebuild_decision_gaps_for_opportunity(db, opportunity_id=int(opp.id))

    r = await client.get(f"/api/v1/decision-gaps/opportunities/{opp.id}", headers=_auth(mgr))
    assert r.status_code == 200
    assert r.json()["opportunity_id"] == opp.id

