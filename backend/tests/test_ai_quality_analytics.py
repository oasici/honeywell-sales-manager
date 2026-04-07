"""D2: AI quality analytics endpoint tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.user import User


async def _create_manager(db: AsyncSession) -> tuple[User, dict]:
    user = User(
        email="ai_analytics_mgr@test.com",
        full_name="AI Analytics Tester",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}
    return user, headers


async def _create_rep(db: AsyncSession) -> tuple[User, dict]:
    user = User(
        email="ai_analytics_rep@test.com",
        full_name="AI Rep",
        hashed_password=hash_password("Test1234"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}
    return user, headers


@pytest.mark.asyncio
async def test_ai_quality_returns_200_for_manager(client: AsyncClient, db: AsyncSession):
    _, headers = await _create_manager(db)

    response = await client.get("/api/v1/analytics/ai-quality", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "total_parsed" in data
    assert "success_rate_pct" in data
    assert "fallback_rate_pct" in data
    assert "correction_trend" in data
    assert isinstance(data["correction_trend"], list)


@pytest.mark.asyncio
async def test_ai_quality_empty_db_returns_zeros(client: AsyncClient, db: AsyncSession):
    _, headers = await _create_manager(db)

    response = await client.get("/api/v1/analytics/ai-quality", headers=headers)
    data = response.json()

    assert data["total_parsed"] == 0
    assert data["parse_errors"] == 0
    assert data["total_corrections"] == 0


@pytest.mark.asyncio
async def test_ai_quality_forbidden_for_non_manager(client: AsyncClient, db: AsyncSession):
    _, headers = await _create_rep(db)

    response = await client.get("/api/v1/analytics/ai-quality", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_ai_usage_still_works(client: AsyncClient, db: AsyncSession):
    """Existing ai-usage endpoint must not be broken."""
    _, headers = await _create_manager(db)

    response = await client.get("/api/v1/analytics/ai-usage", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "total_parsed" in data
    assert "estimated_api_cost_usd" in data
