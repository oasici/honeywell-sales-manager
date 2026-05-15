"""Tests for forecast adjustments and pipeline snapshots."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.forecast import ForecastAdjustment, PipelineSnapshot
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.forecast_service import ForecastService, STAGE_PROBABILITIES
from tests.factories import DEFAULT_TENANT_ID, make_opportunity


@pytest_asyncio.fixture
async def manager_user(db: AsyncSession) -> User:
    user = User(
        # Round-15 Sprint 15k/l unblocker — tenant_id threaded.
        tenant_id=DEFAULT_TENANT_ID,
        email="mgr@test.com",
        full_name="Manager User",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def sample_opportunity(db: AsyncSession, manager_user: User) -> Opportunity:
    opp = await make_opportunity(
        db,
        title="Test Deal",
        stage="proposal",
        amount=100000.0,
        currency="TRY",
        owner_id=manager_user.id,
        forecast_category="best_case",
    )
    await db.commit()
    await db.refresh(opp)
    return opp


@pytest.fixture(autouse=True)
def _enable_forecast():
    with patch("app.api.v1.forecast.settings") as mock_settings:
        mock_settings.FEATURE_V2_BOARD = True
        yield


# -- Adjustment Tests --

@pytest.mark.asyncio
async def test_create_adjustment_updates_opportunity(
    db: AsyncSession, manager_user: User, sample_opportunity: Opportunity,
):
    """Adjustment saves original values and updates the opportunity."""
    service = ForecastService(db)
    adjustment = await service.create_adjustment(
        opp_id=sample_opportunity.id,
        user_id=manager_user.id,
        new_amount=120000.0,
        new_category="commit",
        reason="Increased confidence after meeting",
    )
    await db.commit()

    assert adjustment.original_amount == 100000.0
    assert adjustment.adjusted_amount == 120000.0
    assert adjustment.original_category == "best_case"
    assert adjustment.adjusted_category == "commit"
    assert adjustment.reason == "Increased confidence after meeting"

    # Verify opportunity was updated
    await db.refresh(sample_opportunity)
    assert sample_opportunity.amount == 120000.0
    assert sample_opportunity.forecast_category == "commit"


@pytest.mark.asyncio
async def test_create_adjustment_amount_only(
    db: AsyncSession, manager_user: User, sample_opportunity: Opportunity,
):
    """Adjustment with only new_amount keeps original category."""
    service = ForecastService(db)
    adjustment = await service.create_adjustment(
        opp_id=sample_opportunity.id,
        user_id=manager_user.id,
        new_amount=80000.0,
    )
    await db.commit()

    assert adjustment.adjusted_amount == 80000.0
    assert adjustment.adjusted_category == "best_case"
    assert adjustment.original_category == "best_case"

    await db.refresh(sample_opportunity)
    assert sample_opportunity.amount == 80000.0
    assert sample_opportunity.forecast_category == "best_case"


@pytest.mark.asyncio
async def test_create_adjustment_category_only(
    db: AsyncSession, manager_user: User, sample_opportunity: Opportunity,
):
    """Adjustment with only new_category keeps original amount."""
    service = ForecastService(db)
    adjustment = await service.create_adjustment(
        opp_id=sample_opportunity.id,
        user_id=manager_user.id,
        new_category="pipeline",
    )
    await db.commit()

    assert adjustment.adjusted_amount == 100000.0
    assert adjustment.adjusted_category == "pipeline"

    await db.refresh(sample_opportunity)
    assert sample_opportunity.amount == 100000.0
    assert sample_opportunity.forecast_category == "pipeline"


@pytest.mark.asyncio
async def test_create_adjustment_nonexistent_opportunity(
    db: AsyncSession, manager_user: User,
):
    """Adjusting a nonexistent opportunity raises NotFoundException."""
    service = ForecastService(db)

    from app.core.exceptions import NotFoundException
    with pytest.raises(NotFoundException):
        await service.create_adjustment(
            opp_id=99999,
            user_id=manager_user.id,
            new_amount=50000.0,
        )


@pytest.mark.asyncio
async def test_get_adjustments_returns_history(
    db: AsyncSession, manager_user: User, sample_opportunity: Opportunity,
):
    """Multiple adjustments are returned newest first."""
    service = ForecastService(db)

    await service.create_adjustment(
        opp_id=sample_opportunity.id,
        user_id=manager_user.id,
        new_amount=110000.0,
        reason="First adjustment",
    )
    await db.commit()

    await service.create_adjustment(
        opp_id=sample_opportunity.id,
        user_id=manager_user.id,
        new_amount=130000.0,
        reason="Second adjustment",
    )
    await db.commit()

    adjustments = await service.get_adjustments(sample_opportunity.id)

    assert len(adjustments) == 2
    # Newest first
    assert adjustments[0].reason == "Second adjustment"
    assert adjustments[1].reason == "First adjustment"


# -- Snapshot Tests --

@pytest.mark.asyncio
async def test_take_pipeline_snapshot(
    db: AsyncSession, manager_user: User,
):
    """Snapshot groups active opportunities by stage with weighted amounts."""
    # Create opportunities in different stages via tenant-aware factory.
    await make_opportunity(
        db, title="Prospecting Deal", stage="prospecting",
        amount=50000.0, currency="TRY",
        owner_id=manager_user.id, status="active",
    )
    await make_opportunity(
        db, title="Qualified Deal", stage="qualified",
        amount=80000.0, currency="TRY",
        owner_id=manager_user.id, status="active",
    )
    await make_opportunity(
        db, title="Another Qualified", stage="qualified",
        amount=40000.0, currency="TRY",
        owner_id=manager_user.id, status="active",
    )
    await db.commit()

    service = ForecastService(db)
    snapshots = await service.take_pipeline_snapshot()
    await db.commit()

    assert len(snapshots) >= 2

    stage_map = {s.stage: s for s in snapshots}

    # Prospecting: 1 opp, 50000, weighted = 50000 * 0.1 = 5000
    assert "prospecting" in stage_map
    prospecting = stage_map["prospecting"]
    assert prospecting.opportunity_count == 1
    assert prospecting.total_amount == 50000.0
    assert prospecting.weighted_amount == pytest.approx(5000.0)

    # Qualified: 2 opps, 120000, weighted = 120000 * 0.3 = 36000
    assert "qualified" in stage_map
    qualified = stage_map["qualified"]
    assert qualified.opportunity_count == 2
    assert qualified.total_amount == 120000.0
    assert qualified.weighted_amount == pytest.approx(36000.0)


@pytest.mark.asyncio
async def test_snapshot_excludes_inactive_opportunities(
    db: AsyncSession, manager_user: User,
):
    """Closed opportunities are excluded from snapshots."""
    await make_opportunity(
        db, title="Active", stage="proposal",
        amount=100000.0, currency="TRY",
        owner_id=manager_user.id, status="active",
    )
    await make_opportunity(
        db, title="Closed", stage="proposal",
        amount=200000.0, currency="TRY",
        owner_id=manager_user.id, status="closed",
    )
    await db.commit()

    service = ForecastService(db)
    snapshots = await service.take_pipeline_snapshot()
    await db.commit()

    proposal_snaps = [s for s in snapshots if s.stage == "proposal"]
    assert len(proposal_snaps) == 1
    assert proposal_snaps[0].total_amount == 100000.0


# -- Week-over-Week Tests --

@pytest.mark.asyncio
async def test_week_over_week_calculation(db: AsyncSession):
    """WoW returns weekly data with deltas between consecutive weeks."""
    today = date.today()

    # Create snapshots for two consecutive weeks
    this_week = PipelineSnapshot(
        snapshot_date=today,
        stage="proposal",
        opportunity_count=5,
        total_amount=500000.0,
        weighted_amount=250000.0,
    )
    last_week = PipelineSnapshot(
        snapshot_date=today - timedelta(weeks=1),
        stage="proposal",
        opportunity_count=3,
        total_amount=300000.0,
        weighted_amount=150000.0,
    )
    db.add_all([this_week, last_week])
    await db.commit()

    service = ForecastService(db)
    wow_data = await service.get_week_over_week(weeks=2)

    assert len(wow_data) == 2
    # Most recent week first
    current = wow_data[0]
    previous = wow_data[1]

    assert current["total_amount"] == 500000.0
    assert previous["total_amount"] == 300000.0
    assert current["delta_amount"] == pytest.approx(200000.0)
    # Last week has no previous week to compare to
    assert previous["delta_amount"] == 0.0


@pytest.mark.asyncio
async def test_week_over_week_empty_weeks(db: AsyncSession):
    """WoW handles weeks with no snapshot data gracefully."""
    service = ForecastService(db)
    wow_data = await service.get_week_over_week(weeks=3)

    assert len(wow_data) == 3
    assert all(w["total_amount"] == 0.0 for w in wow_data)
    assert all(w["delta_amount"] == 0.0 for w in wow_data)


@pytest.mark.asyncio
async def test_stage_probabilities_complete():
    """Verify all expected stages have probability mappings."""
    expected_stages = [
        "prospecting", "qualified", "proposal",
        "negotiation", "closed_won", "closed_lost",
    ]
    for stage in expected_stages:
        assert stage in STAGE_PROBABILITIES, f"Missing probability for stage: {stage}"

    assert STAGE_PROBABILITIES["closed_won"] == 1.0
    assert STAGE_PROBABILITIES["closed_lost"] == 0.0
