"""Tests for Revenue Signal — emit, dedup, stream, resolve, depth guard."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.revenue_signal import RevenueSignal
from app.models.user import User
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.core.security import hash_password
from app.services import revenue_signal_service


@pytest_asyncio.fixture
async def setup_data(db: AsyncSession):
    user = User(
        email="cockpit@test.com", full_name="Cockpit Tester",
        hashed_password=hash_password("Test1234"), role="sales_manager", is_active=True,
    )
    db.add(user)
    await db.flush()

    customer = Customer(name="Signal Corp", email="signal@corp.com", created_by=user.id)
    db.add(customer)
    await db.flush()

    opp = Opportunity(
        title="Signal Deal", stage="proposal", amount=100000,
        owner_id=user.id, customer_id=customer.id,
    )
    db.add(opp)
    await db.flush()

    return {"user": user, "customer": customer, "opp": opp}


@pytest.mark.asyncio
async def test_emit_signal_basic(db: AsyncSession, setup_data):
    """Basic signal emission creates a row."""
    data = setup_data
    signal = await revenue_signal_service.emit_signal(
        db,
        signal_type="deal_risk",
        source_entity_type="opportunity",
        source_entity_id=data["opp"].id,
        opportunity_id=data["opp"].id,
        owner_id=data["user"].id,
        severity="high",
        confidence=0.85,
        recommended_action="Acil takip gerekli",
    )
    await db.commit()

    assert signal is not None
    assert signal.id is not None
    assert signal.signal_type == "deal_risk"
    assert signal.severity == "high"
    assert signal.confidence == 0.85


@pytest.mark.asyncio
async def test_emit_signal_idempotent(db: AsyncSession, setup_data):
    """Duplicate event_key is silently deduplicated."""
    data = setup_data
    s1 = await revenue_signal_service.emit_signal(
        db,
        signal_type="stage_change",
        source_entity_type="opportunity",
        source_entity_id=data["opp"].id,
        event_key="stage:1:proposal:negotiation",
    )
    s2 = await revenue_signal_service.emit_signal(
        db,
        signal_type="stage_change",
        source_entity_type="opportunity",
        source_entity_id=data["opp"].id,
        event_key="stage:1:proposal:negotiation",
    )
    await db.commit()

    assert s1 is not None
    assert s2 is None  # deduplicated

    count = (await db.execute(
        select(RevenueSignal).where(RevenueSignal.event_key == "stage:1:proposal:negotiation")
    )).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_emit_signal_depth_guard(db: AsyncSession):
    """Signals with depth > 3 are dropped."""
    signal = await revenue_signal_service.emit_signal(
        db,
        signal_type="cascade_test",
        source_entity_type="test",
        depth=4,
    )
    assert signal is None


@pytest.mark.asyncio
async def test_get_signal_stream(db: AsyncSession, setup_data):
    """Signal stream returns paginated results with filters."""
    data = setup_data
    for i in range(5):
        await revenue_signal_service.emit_signal(
            db,
            signal_type="deal_risk" if i < 3 else "positive",
            source_entity_type="test",
            source_entity_id=i,
            opportunity_id=data["opp"].id,
            severity="high" if i < 3 else "low",
        )
    await db.commit()

    # All signals
    result = await revenue_signal_service.get_signal_stream(db, limit=10)
    assert result["total"] == 5
    assert len(result["items"]) == 5

    # Filter by severity
    result = await revenue_signal_service.get_signal_stream(db, severity="high", limit=10)
    assert result["total"] == 3

    # Filter by type
    result = await revenue_signal_service.get_signal_stream(db, signal_type="positive", limit=10)
    assert result["total"] == 2


@pytest.mark.asyncio
async def test_resolve_signal(db: AsyncSession, setup_data):
    """Resolving a signal sets is_resolved=True."""
    signal = await revenue_signal_service.emit_signal(
        db,
        signal_type="no_touch",
        source_entity_type="test",
    )
    await db.commit()

    found = await revenue_signal_service.resolve_signal(db, signal.id)
    assert found is True

    # Resolved signals excluded from default stream
    result = await revenue_signal_service.get_signal_stream(db, limit=10)
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_get_signal_stats(db: AsyncSession, setup_data):
    """Stats returns counts by severity and type."""
    for sev in ["high", "high", "critical", "low"]:
        await revenue_signal_service.emit_signal(
            db,
            signal_type="deal_risk",
            source_entity_type="test",
            severity=sev,
        )
    await db.commit()

    stats = await revenue_signal_service.get_signal_stats(db)
    assert stats["total"] == 4
    assert stats["high_count"] == 2
    assert stats["critical_count"] == 1


@pytest.mark.asyncio
async def test_resolve_nonexistent_signal(db: AsyncSession):
    """Resolving non-existent signal returns False."""
    found = await revenue_signal_service.resolve_signal(db, 99999)
    assert found is False
