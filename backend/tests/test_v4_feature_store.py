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
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.user import User
from app.services.revenue_signal_service import emit_signal


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
def _enable_feature_store_flag():
    with patch("app.api.v1.feature_store.settings") as ms:
        ms.FEATURE_V4_FEATURE_STORE = True
        yield


@pytest.mark.asyncio
async def test_v4_endpoints_404_when_flag_off(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "v4_flag_mgr@test.com", "sales_manager")
    with patch("app.api.v1.feature_store.settings") as ms:
        ms.FEATURE_V4_FEATURE_STORE = False
        r = await client.get("/api/v1/v4/opportunities/1/features/latest", headers=_auth(mgr))
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_build_and_read_latest_snapshot(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "v4_mgr@test.com", "sales_manager")

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

    # rep touch activity (14d)
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

    # quote + quote item discount
    q = Quote(
        tenant_id=_TENANT_ID,
        quote_number="Q-1",
        customer_id=cust.id,
        created_by=mgr.id,
        status="draft",
        language="tr",
        currency="TRY",
        created_at=datetime.now(timezone.utc),
        opportunity_id=opp.id,
        grand_total=1000,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    db.add(
        QuoteItem(
            quote_id=q.id,
                honeywell_code="P1",
                description="Part",
            quantity=1,
            unit_price=1000,
            discount_pct=12.5,
        )
    )
    await db.commit()

    # build
    r = await client.post("/api/v1/v4/feature-store/build", headers=_auth(mgr))
    assert r.status_code == 200
    d = r.json()
    assert d["opportunities_upserted"] >= 1

    # read
    g = await client.get(f"/api/v1/v4/opportunities/{opp.id}/features/latest", headers=_auth(mgr))
    assert g.status_code == 200
    payload = g.json()["data"]
    assert payload["opportunity_id"] == opp.id
    assert payload["deal_age_days"] >= 9
    assert payload["rep_touch_count_14d"] >= 1
    assert payload["quote_count"] >= 1
    assert payload["latest_discount_pct"] == 12.5

    # DB assertion
    row = (
        await db.execute(
            select(OpportunityFeaturesDaily).where(OpportunityFeaturesDaily.opportunity_id == opp.id)
        )
    ).scalar_one_or_none()
    assert row is not None


@pytest.mark.asyncio
async def test_emit_signal_wraps_metadata_into_explainability_envelope(db: AsyncSession):
    s = await emit_signal(
        db,
        signal_type="pricing_concern",
        source_entity_type="email",
        source_entity_id=123,
        severity="high",
        confidence=0.7,
        recommended_action="Follow up on pricing",
        metadata={"evidence": "Customer asked for discount"},
        event_key="test:pricing_concern:email:123",
    )
    assert s is not None
    assert s.metadata_json is not None
    meta = __import__("json").loads(s.metadata_json)
    assert meta.get("model_version") == "v4-mvp"
    assert "drivers" in meta
    assert "recommended_actions" in meta
    assert meta.get("raw", {}).get("evidence") == "Customer asked for discount"

