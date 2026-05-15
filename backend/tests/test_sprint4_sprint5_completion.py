"""Sprint 4–5 completion: calendar stub, insights trends, conversation search."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.engagement import Transcript
from app.models.enums import OpportunitySignalType
from app.models.opportunity import Opportunity, OpportunitySignal
from app.models.user import User


@pytest.fixture()
def _insights_flag(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "FEATURE_V2_BOARD", True)


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _manager(db: AsyncSession) -> tuple[User, dict]:
    u = User(
        tenant_id=_TENANT_ID,
        email="s45_mgr@test.com",
        full_name="S45 Manager",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u, {"Authorization": f"Bearer {create_access_token({'sub': str(u.id)})}"}


@pytest.mark.asyncio
async def test_schedule_meeting_placeholder(client: AsyncClient, db: AsyncSession, _insights_flag):
    mgr, h = await _manager(db)
    r = await client.post(
        "/api/v1/meetings/schedule-placeholder",
        json={
            "title": "Demo call",
            "start_at": "2026-05-01T10:00:00+00:00",
            "duration_minutes": 30,
        },
        headers=h,
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["adapter"] == "stub"
    assert data["status"] == "placeholder"


@pytest.mark.asyncio
async def test_insights_signals_trends(client: AsyncClient, db: AsyncSession, _insights_flag):
    _, h = await _manager(db)
    r = await client.get("/api/v1/insights/signals/trends?window=30", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert "series" in body
    assert isinstance(body["series"], list)


@pytest.mark.asyncio
async def test_conversation_search_transcript(
    client: AsyncClient, db: AsyncSession, _insights_flag,
):
    mgr, h = await _manager(db)
    cust = Customer(tenant_id=_TENANT_ID, name="ACME", company="ACME Ltd", email="acme@test.com")
    db.add(cust)
    await db.flush()
    opp = Opportunity(
        tenant_id=_TENANT_ID,
        title="Big deal",
        stage="qualification",
        owner_id=mgr.id,
        customer_id=cust.id,
        amount=1000.0,
    )
    db.add(opp)
    await db.flush()
    tr = Transcript(
        opportunity_id=opp.id,
        title="Call",
        content="Customer asked about fiyat and discount terms",
        source="paste",
    )
    db.add(tr)
    await db.commit()

    r = await client.get(
        "/api/v1/insights/conversation-search",
        params={"q": "fiyat", "stage": "qualification"},
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(it["type"] == "transcript" for it in body["items"])


@pytest.mark.asyncio
async def test_conversation_search_signal_filter(
    client: AsyncClient, db: AsyncSession, _insights_flag,
):
    mgr, h = await _manager(db)
    cust = Customer(tenant_id=_TENANT_ID, name="Beta", company="Beta Co", email="beta@test.com")
    db.add(cust)
    await db.flush()
    opp = Opportunity(
        tenant_id=_TENANT_ID,
        title="O2",
        stage="prospecting",
        owner_id=mgr.id,
        customer_id=cust.id,
        amount=500.0,
    )
    db.add(opp)
    await db.flush()
    sig = OpportunitySignal(
        opportunity_id=opp.id,
        signal_type=OpportunitySignalType.PRICING_CONCERN.value,
        severity="high",
        evidence="test",
        is_resolved=False,
    )
    tr = Transcript(
        opportunity_id=opp.id,
        title="Note call",
        content="We discussed timeline only",
        source="paste",
    )
    db.add_all([sig, tr])
    await db.commit()

    r = await client.get(
        "/api/v1/insights/conversation-search",
        params={"q": "timeline", "signal_type": OpportunitySignalType.PRICING_CONCERN.value},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


@pytest.mark.asyncio
async def test_prospecting_agent_facade(client: AsyncClient, db: AsyncSession):
    """High-intent list still works via ProspectingAgent-backed customers route."""
    _, h = await _manager(db)
    r = await client.get("/api/v1/customers/high-intent?limit=10", headers=h)
    assert r.status_code == 200
    assert "items" in r.json()
