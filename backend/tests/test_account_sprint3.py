"""Sprint 3 — Account Intelligence (account-360 + meeting prep)."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.user import User


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _mgr(db: AsyncSession) -> tuple[User, dict]:
    user = User(
        tenant_id=_TENANT_ID,
        email="s3_mgr@test.com",
        full_name="S3 Manager",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    h = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}
    return user, h


@pytest.mark.asyncio
async def test_account_360_creates_enrichment_and_open_deals(client: AsyncClient, db: AsyncSession):
    mgr, h = await _mgr(db)
    cust = Customer(
        tenant_id=_TENANT_ID,
        name="Acct360 Co",
        email="acct360@test.com",
        company="Acct360",
        created_by=mgr.id,
    )
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    opp = Opportunity(
        tenant_id=_TENANT_ID,
        title="Pipeline deal",
        stage="qualified",
        status="active",
        owner_id=mgr.id,
        customer_id=cust.id,
        amount=120000.0,
        currency="EUR",
    )
    db.add(opp)
    await db.commit()

    r = await client.get(f"/api/v1/customers/{cust.id}/account-360", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["customer_id"] == cust.id
    assert "enrichment" in data
    assert data["enrichment"].get("currency") == "EUR"
    assert data["enrichment"]["active_deal_count"] >= 1
    assert data["enrichment"]["pipeline_open_amount"] >= 120000.0
    assert "last_touch" in data
    assert "open_deals" in data and len(data["open_deals"]) >= 1
    assert "risk_summary" in data
    assert "timeline" in data


@pytest.mark.asyncio
async def test_meeting_prep_fallback_without_claude(client: AsyncClient, db: AsyncSession):
    mgr, h = await _mgr(db)
    cust = Customer(
        tenant_id=_TENANT_ID,
        name="MeetPrep Co",
        email="meetprep@test.com",
        company="MeetPrep",
        created_by=mgr.id,
    )
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    with patch("app.api.v1.ai.settings") as ms:
        ms.FEATURE_AI_SUMMARIES = True
        ms.ANTHROPIC_API_KEY = ""
        r = await client.post(
            "/api/v1/ai/meeting-prep",
            json={"customer_id": cust.id},
            headers=h,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["customer_id"] == cust.id
    assert "prep" in body
    assert len(body["prep"]) > 20
