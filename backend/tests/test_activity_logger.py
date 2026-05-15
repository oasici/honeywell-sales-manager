"""Tests for activity auto-logging service."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.opportunity import Opportunity, OpportunityEvent
from app.models.customer import Customer
from app.models.user import User
from app.services.activity_logger import log_activity
from app.core.security import hash_password


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    user = User(
        tenant_id=_TENANT_ID,
        email="actlog@test.com",
        full_name="Activity Logger",
        hashed_password=hash_password("Test1234"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_customer(db: AsyncSession, test_user: User) -> Customer:
    customer = Customer(
        tenant_id=_TENANT_ID,
        name="Test Corp",
        email="corp@test.com",
        company="Test Corp Ltd",
        created_by=test_user.id,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


@pytest_asyncio.fixture
async def test_opportunity(db: AsyncSession, test_user: User, test_customer: Customer) -> Opportunity:
    opp = Opportunity(
        tenant_id=_TENANT_ID,
        title="Test Deal",
        stage="prospecting",
        owner_id=test_user.id,
        customer_id=test_customer.id,
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


@pytest.mark.asyncio
async def test_log_activity_basic(db: AsyncSession, test_user: User, test_customer: Customer):
    """Activity log entry is created with correct fields."""
    await log_activity(
        db,
        activity_type="quote_created",
        entity_type="quote",
        entity_id=999,
        customer_id=test_customer.id,
        user_id=test_user.id,
        summary="Teklif olusturuldu: QT-001",
    )
    await db.commit()

    result = await db.execute(select(ActivityLog))
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].activity_type == "quote_created"
    assert logs[0].entity_type == "quote"
    assert logs[0].entity_id == 999
    assert logs[0].customer_id == test_customer.id
    assert logs[0].user_id == test_user.id
    assert "QT-001" in logs[0].summary


@pytest.mark.asyncio
async def test_log_activity_creates_opportunity_event(
    db: AsyncSession, test_user: User, test_opportunity: Opportunity
):
    """When opportunity_id is set, an OpportunityEvent is also created."""
    await log_activity(
        db,
        activity_type="stage_change",
        entity_type="opportunity",
        entity_id=test_opportunity.id,
        opportunity_id=test_opportunity.id,
        user_id=test_user.id,
        summary="Asamadan gecis: prospecting -> qualified",
    )
    await db.commit()

    # Check ActivityLog
    result = await db.execute(select(ActivityLog))
    logs = result.scalars().all()
    assert len(logs) == 1

    # Check OpportunityEvent was also created
    result = await db.execute(
        select(OpportunityEvent).where(
            OpportunityEvent.opportunity_id == test_opportunity.id
        )
    )
    events = result.scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "stage_change"
    assert "prospecting -> qualified" in (events[0].description or "")


@pytest.mark.asyncio
async def test_log_activity_without_opportunity(db: AsyncSession, test_user: User):
    """Without opportunity_id, no OpportunityEvent is created."""
    await log_activity(
        db,
        activity_type="email_received",
        entity_type="email",
        entity_id=42,
        user_id=test_user.id,
        summary="Email alindi",
    )
    await db.commit()

    result = await db.execute(select(ActivityLog))
    assert len(result.scalars().all()) == 1

    result = await db.execute(select(OpportunityEvent))
    assert len(result.scalars().all()) == 0


@pytest.mark.asyncio
async def test_log_activity_with_metadata(db: AsyncSession, test_user: User):
    """Metadata dict is serialized to JSON."""
    await log_activity(
        db,
        activity_type="quote_approved",
        entity_type="quote",
        entity_id=1,
        user_id=test_user.id,
        summary="Teklif onaylandi",
        metadata={"approved_by": "manager", "discount": 15.5},
    )
    await db.commit()

    result = await db.execute(select(ActivityLog))
    log = result.scalars().first()
    assert log is not None
    assert log.metadata_json is not None
    import json
    data = json.loads(log.metadata_json)
    assert data["discount"] == 15.5


@pytest.mark.asyncio
async def test_log_activity_never_raises(db: AsyncSession):
    """log_activity must never raise — even with invalid data."""
    # Pass None for required fields — should not raise
    await log_activity(
        db,
        activity_type="test",
        entity_type="test",
        entity_id=0,
    )
    # If we get here without exception, the test passes


@pytest.mark.asyncio
async def test_log_activity_truncates_long_summary(db: AsyncSession, test_user: User):
    """Summary longer than 500 chars is truncated."""
    long_summary = "x" * 600
    await log_activity(
        db,
        activity_type="note_added",
        entity_type="opportunity",
        entity_id=1,
        user_id=test_user.id,
        summary=long_summary,
    )
    await db.commit()

    result = await db.execute(select(ActivityLog))
    log = result.scalars().first()
    assert log is not None
    assert len(log.summary) <= 500
