"""v2 Integration hooks tests — calendar + e-sign."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.user import User


async def _mgr(db: AsyncSession) -> tuple[User, dict]:
    user = User(email="integ_mgr@test.com", full_name="Integ Manager",
                hashed_password=hash_password("Test1234"), role="sales_manager", is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


# ── Calendar ──

@pytest.mark.asyncio
async def test_calendar_connect(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.post("/api/v1/integrations/calendar/connect", json={
        "provider": "google", "config": {"client_id": "test"},
    }, headers=h)
    assert r.status_code == 200
    assert r.json()["provider"] == "google"


@pytest.mark.asyncio
async def test_calendar_status_not_configured(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/integrations/calendar/status", headers=h)
    assert r.status_code == 200
    # May or may not be connected depending on test order


@pytest.mark.asyncio
async def test_calendar_link_event(client: AsyncClient, db: AsyncSession):
    user, h = await _mgr(db)
    opp = Opportunity(title="Calendar Test", stage="proposal", owner_id=user.id)
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    r = await client.post("/api/v1/integrations/calendar/link-event", json={
        "opportunity_id": opp.id,
        "event_title": "Kordsa Toplantisi",
        "event_date": "2026-04-15T14:00:00",
        "attendees": "ahmet@kordsa.com, ali@honeywell.com",
    }, headers=h)
    assert r.status_code == 200
    assert r.json()["event_id"] > 0


@pytest.mark.asyncio
async def test_calendar_sync_stub(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.post("/api/v1/integrations/calendar/sync", headers=h)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_calendar_invalid_provider(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.post("/api/v1/integrations/calendar/connect", json={
        "provider": "invalid_provider", "config": {},
    }, headers=h)
    assert r.status_code == 400


# ── E-Sign ──

@pytest.mark.asyncio
async def test_esign_connect(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.post("/api/v1/integrations/esign/connect", json={
        "provider": "docusign", "config": {"api_key": "test"},
    }, headers=h)
    assert r.status_code == 200
    assert r.json()["provider"] == "docusign"


@pytest.mark.asyncio
async def test_esign_status(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/integrations/esign/status", headers=h)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_esign_send_stub(client: AsyncClient, db: AsyncSession):
    user, h = await _mgr(db)
    quote = Quote(quote_number="ESIGN-001", created_by=user.id, status="approved",
                  subtotal=1000, discount_total=0, tax_rate=20, tax_amount=200, grand_total=1200)
    db.add(quote)
    await db.commit()
    await db.refresh(quote)

    r = await client.post("/api/v1/integrations/esign/send", json={
        "quote_id": quote.id,
        "signer_email": "musteri@firma.com",
        "signer_name": "Ali Veli",
    }, headers=h)
    assert r.status_code == 200
    assert r.json()["status"] in ("stub", "not_configured")


@pytest.mark.asyncio
async def test_esign_webhook_stub(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.post("/api/v1/integrations/esign/webhook", headers=h)
    assert r.status_code == 200
