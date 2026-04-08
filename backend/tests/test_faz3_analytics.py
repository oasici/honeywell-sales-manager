"""Faz-3: Analytics endpoint tests — forecast, slippage, funnel, rep-scorecards, discounts, SLA, data-quality, win-loss."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.user import User


async def _mgr(db: AsyncSession) -> tuple[User, dict]:
    user = User(
        email="faz3_mgr@test.com",
        full_name="Faz3 Manager",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


async def _rep(db: AsyncSession) -> tuple[User, dict]:
    user = User(
        email="faz3_rep@test.com",
        full_name="Faz3 Rep",
        hashed_password=hash_password("Test1234"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


@pytest.mark.asyncio
async def test_forecast_empty_db(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/analytics/forecast?window=30", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "open_quotes_total" in d
    assert "forecast_total" in d
    assert "by_day" in d


@pytest.mark.asyncio
async def test_forecast_forbidden_for_rep(client: AsyncClient, db: AsyncSession):
    _, h = await _rep(db)
    r = await client.get("/api/v1/analytics/forecast", headers=h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_slippage_empty_db(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/analytics/slippage?no_touch_days=7", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "risky_quotes" in d
    assert "aging_buckets" in d


@pytest.mark.asyncio
async def test_funnel_empty_db(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/analytics/funnel?window=30", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "funnel" in d
    assert "conversions" in d


@pytest.mark.asyncio
async def test_rep_scorecards(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/analytics/rep-scorecards?window=30", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "scorecards" in d


@pytest.mark.asyncio
async def test_discounts_empty_db(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/analytics/discounts?window=90", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "p50_discount_rate" in d
    assert "outliers" in d


@pytest.mark.asyncio
async def test_sla_empty_db(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/analytics/sla?window=30", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "median_first_action_minutes" in d
    assert "breaches" in d


@pytest.mark.asyncio
async def test_win_loss_reasons_empty_db(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/analytics/win-loss-reasons", headers=h)
    assert r.status_code == 200
    assert "reasons" in r.json()


@pytest.mark.asyncio
async def test_data_quality_empty_db(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/analytics/data-quality", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "customers" in d
    assert "quotes" in d


@pytest.mark.asyncio
async def test_ops_queues_empty_db(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/ops/queues", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "review_pending" in d
    assert "quote_approval_pending" in d
    assert "expiring_quotes" in d


@pytest.mark.asyncio
async def test_saved_views_crud(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)

    # Create
    r = await client.post("/api/v1/saved-views/", json={
        "name": "Test View",
        "route": "/emails",
        "query_json": '{"status": "parsed"}',
    }, headers=h)
    assert r.status_code == 201
    view_id = r.json()["id"]

    # List
    r = await client.get("/api/v1/saved-views/", headers=h)
    assert r.status_code == 200
    assert len(r.json()["views"]) >= 1

    # Delete
    r = await client.delete(f"/api/v1/saved-views/{view_id}", headers=h)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_customer_timeline_empty(client: AsyncClient, db: AsyncSession):
    from app.models.customer import Customer
    _, h = await _mgr(db)

    cust = Customer(name="Timeline Test", email="timeline@test.com")
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    r = await client.get(f"/api/v1/customers/{cust.id}/timeline", headers=h)
    assert r.status_code == 200
    assert r.json()["events"] == []
