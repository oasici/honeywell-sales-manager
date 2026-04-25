from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity
from app.models.user import User


async def _user(db: AsyncSession, email: str, role: str) -> User:
    u = User(
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
async def test_sales_dna_flag_off_returns_404(client: AsyncClient, db: AsyncSession):
    mgr = await _user(db, "dna_off@test.com", "sales_manager")
    r = await client.get("/api/v1/v4/dna/opportunities/1/latest", headers=_auth(mgr))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_sales_dna_materialize_read_latest(client: AsyncClient, db: AsyncSession):
    with patch("app.api.v1.sales_dna.settings") as s:
        s.FEATURE_V4_SALES_DNA = True
        mgr = await _user(db, "dna_mgr@test.com", "sales_manager")
        cust = Customer(name="C", company="C", email="cdna@test.com", phone="", address="", tax_id="")
        db.add(cust)
        await db.commit()
        await db.refresh(cust)

        opp = Opportunity(
            customer_id=cust.id,
            owner_id=mgr.id,
            title="O",
            stage="qualified",
            status="active",
            amount=1,
            currency="TRY",
            created_at=datetime.now(timezone.utc) - timedelta(days=5),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(opp)
        await db.commit()
        await db.refresh(opp)

        snap = date(2026, 4, 22)
        db.add(
            OpportunityFeaturesDaily(
                opportunity_id=opp.id,
                snapshot_date=snap,
                deal_age_days=5,
                days_since_last_rep_touch=3,
                days_since_last_buyer_touch=4,
                rep_touch_count_14d=2,
                buyer_reply_count_14d=1,
                meeting_count_30d=0,
                quote_count=0,
                competitor_mentions_30d=0,
                pricing_objections_30d=0,
                positive_signal_count_14d=0,
                negative_signal_count_14d=1,
                momentum_band="steady",
                momentum_score=55,
                buyer_state="evaluating",
            )
        )
        db.add(
            ActivityLog(
                activity_type="note_added",
                entity_type="opportunity",
                entity_id=opp.id,
                opportunity_id=opp.id,
                customer_id=cust.id,
                user_id=mgr.id,
                summary="dna",
                created_at=datetime.combine(snap, datetime.min.time()).replace(tzinfo=timezone.utc)
                + timedelta(hours=10),
            )
        )
        await db.commit()

        r = await client.post(
            f"/api/v1/v4/dna/opportunities/{opp.id}/materialize",
            params={"snapshot_date": snap.isoformat()},
            headers=_auth(mgr),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["risk_posture"] in ("low", "moderate", "high")

        r2 = await client.get(f"/api/v1/v4/dna/opportunities/{opp.id}/latest", headers=_auth(mgr))
        assert r2.status_code == 200
        j = r2.json()
        assert j["traits"]["engagement_30d"]["activity_log_count"] >= 1
        assert j["traits"]["feature_store_row"] is not None


@pytest.mark.asyncio
async def test_sales_dna_rep_other_opp_forbidden(client: AsyncClient, db: AsyncSession):
    with patch("app.api.v1.sales_dna.settings") as s:
        s.FEATURE_V4_SALES_DNA = True
        mgr = await _user(db, "dna_own@test.com", "sales_manager")
        rep = await _user(db, "dna_rep@test.com", "sales_rep")
        cust = Customer(name="C2", company="C2", email="c2dna@test.com", phone="", address="", tax_id="")
        db.add(cust)
        await db.commit()
        await db.refresh(cust)

        opp = Opportunity(
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

        r = await client.get(f"/api/v1/v4/dna/opportunities/{opp.id}/latest", headers=_auth(rep))
        assert r.status_code == 403
