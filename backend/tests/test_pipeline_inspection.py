"""Tests for pipeline inspection endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.opportunity import Opportunity
from app.models.user import User


@pytest_asyncio.fixture
async def manager_user(db: AsyncSession) -> User:
    user = User(
        email="mgr_pipeline@test.com",
        full_name="Pipeline Manager",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def manager_headers(manager_user: User) -> dict:
    token = create_access_token({"sub": str(manager_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def sample_opportunities(db: AsyncSession, manager_user: User) -> list[Opportunity]:
    """Create opportunities across multiple stages."""
    opps = []
    stages_data = [
        ("Opp A", "prospecting", 10000.0),
        ("Opp B", "prospecting", 20000.0),
        ("Opp C", "qualified", 50000.0),
        ("Opp D", "proposal", 75000.0),
        ("Opp E", "negotiation", 100000.0),
    ]
    for title, stage, amount in stages_data:
        opp = Opportunity(
            title=title,
            stage=stage,
            amount=amount,
            owner_id=manager_user.id,
            status="active",
        )
        db.add(opp)
        opps.append(opp)

    await db.commit()
    for opp in opps:
        await db.refresh(opp)
    return opps


@pytest.fixture(autouse=True)
def _enable_v2_board():
    with patch("app.api.v1.opportunities.settings") as mock_settings:
        mock_settings.FEATURE_V2_BOARD = True
        mock_settings.FEATURE_GUIDED_SELLING = False
        yield


@pytest.mark.asyncio
async def test_pipeline_inspection_returns_stage_breakdown(
    client: AsyncClient,
    manager_headers: dict,
    sample_opportunities: list[Opportunity],
):
    """Pipeline inspection returns per-stage data with health scores."""
    response = await client.get(
        "/api/v1/opportunities/pipeline-inspection",
        headers=manager_headers,
    )

    assert response.status_code == 200
    data = response.json()

    assert "stages" in data
    assert "pipeline_total" in data
    assert "weighted_forecast" in data
    assert "coverage_ratio" in data

    # Should have stages in response
    assert len(data["stages"]) > 0

    # Each stage entry should have expected fields
    for stage_info in data["stages"]:
        assert "stage" in stage_info
        assert "count" in stage_info
        assert "total_amount" in stage_info
        assert "avg_health_score" in stage_info
        assert "stale_count" in stage_info

    # Pipeline total should reflect sum of opportunity amounts
    assert data["pipeline_total"] > 0


@pytest.mark.asyncio
async def test_pipeline_inspection_weighted_forecast(
    client: AsyncClient,
    manager_headers: dict,
    sample_opportunities: list[Opportunity],
):
    """Weighted forecast should reflect stage probabilities."""
    response = await client.get(
        "/api/v1/opportunities/pipeline-inspection",
        headers=manager_headers,
    )

    assert response.status_code == 200
    data = response.json()

    # Weighted forecast should be less than or equal to pipeline total
    # because probabilities are <= 1.0
    assert data["weighted_forecast"] <= data["pipeline_total"]
    assert data["weighted_forecast"] > 0
