from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.feature_store_builder import build_daily_feature_store
from app.models.buyer_state_history import BuyerStateHistory


async def _create_user(db: AsyncSession, email: str, role: str) -> User:
    u = User(
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
    with patch("app.api.v1.buyer_state.settings") as ms:
        ms.FEATURE_V4_FEATURE_STORE = True
        yield


@pytest.mark.asyncio
async def test_buyer_state_timeline_requires_flag(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "bs_mgr@test.com", "sales_manager")
    with patch("app.api.v1.buyer_state.settings") as ms:
        ms.FEATURE_V4_FEATURE_STORE = False
        r = await client.get("/api/v1/buyer-state/opportunities/1/timeline", headers=_auth(mgr))
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_buyer_state_history_written_and_timeline_returns(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "bs_mgr2@test.com", "sales_manager")

    cust = Customer(name="ACME", company="ACME", email="acme@test.com", phone="", address="", tax_id="")
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    opp = Opportunity(
        customer_id=cust.id,
        owner_id=mgr.id,
        title="Deal",
        stage="qualified",
        status="active",
        amount=1000,
        currency="TRY",
        created_at=datetime.now(timezone.utc) - timedelta(days=20),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    # Ensure stalling: no buyer replies, no meetings, buyer last touch far in past
    db.add(
        ActivityLog(
            activity_type="note_added",
            entity_type="opportunity",
            entity_id=opp.id,
            user_id=mgr.id,
            opportunity_id=opp.id,
            customer_id=cust.id,
            summary="Touched",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    await db.commit()

    await build_daily_feature_store(db)

    hist = (
        await db.execute(
            select(BuyerStateHistory).where(BuyerStateHistory.opportunity_id == opp.id)
        )
    ).scalar_one_or_none()
    assert hist is not None
    assert hist.state in ("stalling", "exploring", "evaluating", "negotiating")

    r = await client.get(f"/api/v1/buyer-state/opportunities/{opp.id}/timeline", headers=_auth(mgr))
    assert r.status_code == 200
    payload = r.json()
    assert payload["total"] >= 1

