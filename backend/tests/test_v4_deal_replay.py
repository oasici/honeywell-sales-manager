from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.user import User


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _user(db: AsyncSession, email: str, role: str) -> User:
    u = User(
        tenant_id=_TENANT_ID,
        email=email,
        full_name="T",
        hashed_password=hash_password("Test1234"),
        role=role,
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _auth(u: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(u.id)})}"}


@pytest.mark.asyncio
async def test_deal_replay_flag_off_returns_404(client: AsyncClient, db: AsyncSession):
    mgr = await _user(db, "replay_off@test.com", "sales_manager")
    r = await client.get("/api/v1/v4/replay/opportunities/1/snapshots", headers=_auth(mgr))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_deal_replay_materialize_and_read(client: AsyncClient, db: AsyncSession):
    with patch("app.api.v1.deal_replay.settings") as s:
        s.FEATURE_V4_DEAL_REPLAY = True
        mgr = await _user(db, "replay_mgr@test.com", "sales_manager")
        cust = Customer(tenant_id=_TENANT_ID, name="C", company="C", email="cr@test.com", phone="", address="", tax_id="")
        db.add(cust)
        await db.commit()
        await db.refresh(cust)

        opp = Opportunity(
            tenant_id=_TENANT_ID,
            customer_id=cust.id,
            owner_id=mgr.id,
            title="O",
            stage="qualified",
            status="active",
            amount=1,
            currency="TRY",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(opp)
        await db.commit()
        await db.refresh(opp)

        db.add(
            ActivityLog(
                activity_type="note_added",
                entity_type="opportunity",
                entity_id=opp.id,
                opportunity_id=opp.id,
                customer_id=cust.id,
                user_id=mgr.id,
                summary="replay note",
                created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
        )
        await db.commit()

        snap_day = date(2026, 4, 20)
        r = await client.post(
            f"/api/v1/v4/replay/opportunities/{opp.id}/materialize",
            params={"snapshot_date": snap_day.isoformat()},
            headers=_auth(mgr),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["timeline_item_count"] == 1

        r2 = await client.get(
            f"/api/v1/v4/replay/opportunities/{opp.id}/snapshots",
            headers=_auth(mgr),
        )
        assert r2.status_code == 200
        lst = r2.json()
        assert lst["total"] == 1
        assert lst["items"][0]["snapshot_date"] == snap_day.isoformat()

        r3 = await client.get(
            f"/api/v1/v4/replay/opportunities/{opp.id}/snapshots/{snap_day.isoformat()}",
            headers=_auth(mgr),
        )
        assert r3.status_code == 200
        full = r3.json()
        assert full["frames"]["items"]
        assert len(full["frames"]["items"]) == 1


@pytest.mark.asyncio
async def test_deal_replay_rep_other_opp_forbidden(client: AsyncClient, db: AsyncSession):
    with patch("app.api.v1.deal_replay.settings") as s:
        s.FEATURE_V4_DEAL_REPLAY = True
        mgr = await _user(db, "replay_owner2@test.com", "sales_manager")
        rep = await _user(db, "replay_rep2@test.com", "sales_rep")
        cust = Customer(tenant_id=_TENANT_ID, name="C2", company="C2", email="c2r@test.com", phone="", address="", tax_id="")
        db.add(cust)
        await db.commit()
        await db.refresh(cust)

        opp = Opportunity(
            tenant_id=_TENANT_ID,
            customer_id=cust.id,
            owner_id=mgr.id,
            title="O2",
            stage="qualified",
            status="active",
            amount=1,
            currency="TRY",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(opp)
        await db.commit()
        await db.refresh(opp)

        r = await client.get(
            f"/api/v1/v4/replay/opportunities/{opp.id}/snapshots",
            headers=_auth(rep),
        )
        assert r.status_code == 403
