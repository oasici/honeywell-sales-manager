"""Playbook engine tests — signal evaluation, step execution, cancellation, dedup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity, Task
from app.models.playbook import Playbook, PlaybookExecution
from app.models.revenue_signal import RevenueSignal
from app.models.user import User
from app.core.security import hash_password
from app.services.playbook_service import PlaybookService


# ── Fixtures ──


@pytest_asyncio.fixture
async def sales_user(db: AsyncSession) -> User:
    # Round-10 R10-DB-1..5 — explicit tenant_id so derived rows
    # (Opportunity, Task, Playbook, PlaybookExecution …) can inherit it.
    user = User(
        tenant_id=1,
        email="rep@test.com",
        full_name="Test Rep",
        hashed_password=hash_password("pass123"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def opportunity(db: AsyncSession, sales_user: User) -> Opportunity:
    opp = Opportunity(
        tenant_id=sales_user.tenant_id,
        title="Test Firsat",
        stage="proposal",
        amount=50000.0,
        owner_id=sales_user.id,
    )
    db.add(opp)
    await db.flush()
    return opp


@pytest_asyncio.fixture
async def playbook_no_touch(db: AsyncSession, admin_user: User) -> Playbook:
    pb = Playbook(
        # Round-10 R10-DB-3 — tenant_id now NOT NULL; mirror admin_user's.
        tenant_id=admin_user.tenant_id,
        name="Temas Edilmeyen Firsat",
        description="no_touch sinyali icin otomatik gorev",
        trigger_conditions_json='[{"field": "signal_type", "op": "eq", "value": "no_touch"}, {"field": "severity", "op": "gte", "value": "high"}]',
        steps_json='[{"step": 1, "action_type": "task", "template": "Musteriyi ara", "delay_days": 0, "priority": "high"}, {"step": 2, "action_type": "task", "template": "Takip emaili gonder", "delay_days": 2, "priority": "normal"}]',
        category="retention",
        is_active=True,
        created_by=admin_user.id,
    )
    db.add(pb)
    await db.flush()
    return pb


@pytest_asyncio.fixture
async def signal_no_touch(
    db: AsyncSession, opportunity: Opportunity, sales_user: User
) -> RevenueSignal:
    signal = RevenueSignal(
        signal_type="no_touch",
        source_entity_type="opportunity",
        source_entity_id=opportunity.id,
        opportunity_id=opportunity.id,
        owner_id=sales_user.id,
        severity="high",
        confidence=0.9,
    )
    db.add(signal)
    await db.flush()
    return signal


@pytest_asyncio.fixture
async def signal_low_severity(
    db: AsyncSession, opportunity: Opportunity, sales_user: User
) -> RevenueSignal:
    signal = RevenueSignal(
        signal_type="no_touch",
        source_entity_type="opportunity",
        source_entity_id=opportunity.id,
        opportunity_id=opportunity.id,
        owner_id=sales_user.id,
        severity="low",
        confidence=0.5,
    )
    db.add(signal)
    await db.flush()
    return signal


# ── Tests ──


@pytest.mark.asyncio
async def test_matching_trigger_creates_execution(
    db: AsyncSession,
    playbook_no_touch: Playbook,
    signal_no_touch: RevenueSignal,
    opportunity: Opportunity,
):
    """Signal evaluation: matching trigger creates execution."""
    service = PlaybookService(db)
    execution = await service.evaluate_signal(signal_no_touch)

    assert execution is not None
    assert execution.playbook_id == playbook_no_touch.id
    assert execution.opportunity_id == opportunity.id
    assert execution.status == "active"
    assert execution.triggered_by_signal_id == signal_no_touch.id


@pytest.mark.asyncio
async def test_non_matching_trigger_creates_nothing(
    db: AsyncSession,
    playbook_no_touch: Playbook,
    signal_low_severity: RevenueSignal,
):
    """Signal evaluation: non-matching trigger creates nothing (severity too low)."""
    service = PlaybookService(db)
    execution = await service.evaluate_signal(signal_low_severity)

    assert execution is None


@pytest.mark.asyncio
async def test_step_execution_creates_task(
    db: AsyncSession,
    playbook_no_touch: Playbook,
    signal_no_touch: RevenueSignal,
    opportunity: Opportunity,
    sales_user: User,
):
    """Step execution: creates Task with correct fields."""
    service = PlaybookService(db)
    execution = await service.evaluate_signal(signal_no_touch)
    assert execution is not None

    # First step already executed during evaluate_signal
    from sqlalchemy import select

    result = await db.execute(
        select(Task).where(
            Task.opportunity_id == opportunity.id,
            Task.source == "rule",
        )
    )
    tasks = result.scalars().all()

    assert len(tasks) >= 1
    task = tasks[0]
    assert task.title == "Musteriyi ara"
    assert task.owner_id == sales_user.id
    assert task.priority == "high"
    assert task.status == "open"


@pytest.mark.asyncio
async def test_advance_past_due_execution(
    db: AsyncSession,
    playbook_no_touch: Playbook,
    signal_no_touch: RevenueSignal,
    opportunity: Opportunity,
):
    """Advance: past-due execution advances to next step."""
    service = PlaybookService(db)
    execution = await service.evaluate_signal(signal_no_touch)
    assert execution is not None

    # After first step, next_action_at should be set (2 days delay for step 2)
    assert execution.next_action_at is not None
    assert execution.current_step == 2

    # Simulate past-due by setting next_action_at to the past
    execution.next_action_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db.flush()

    count = await service.advance_due_executions()
    assert count == 1

    # After advancing step 2 (last step), execution should be completed
    await db.refresh(execution)
    assert execution.status == "completed"
    assert execution.completed_at is not None


@pytest.mark.asyncio
async def test_cancel_sets_status_cancelled(
    db: AsyncSession,
    playbook_no_touch: Playbook,
    signal_no_touch: RevenueSignal,
):
    """Cancel: sets status=cancelled."""
    service = PlaybookService(db)
    execution = await service.evaluate_signal(signal_no_touch)
    assert execution is not None

    is_ok = await service.cancel_execution(execution.id)
    assert is_ok is True

    await db.refresh(execution)
    assert execution.status == "cancelled"
    assert execution.completed_at is not None
    assert execution.next_action_at is None


@pytest.mark.asyncio
async def test_no_duplicate_active_execution(
    db: AsyncSession,
    playbook_no_touch: Playbook,
    signal_no_touch: RevenueSignal,
    opportunity: Opportunity,
    sales_user: User,
):
    """No duplicate: same opp+playbook doesn't create second active execution."""
    service = PlaybookService(db)
    first = await service.evaluate_signal(signal_no_touch)
    assert first is not None

    # Create another matching signal for the same opportunity
    signal_2 = RevenueSignal(
        signal_type="no_touch",
        source_entity_type="opportunity",
        source_entity_id=opportunity.id,
        opportunity_id=opportunity.id,
        owner_id=sales_user.id,
        severity="high",
        confidence=0.9,
    )
    db.add(signal_2)
    await db.flush()

    second = await service.evaluate_signal(signal_2)
    assert second is None


@pytest.mark.asyncio
async def test_completion_sets_status_completed(
    db: AsyncSession,
    opportunity: Opportunity,
    sales_user: User,
    admin_user: User,
):
    """Completion: last step sets status=completed."""
    # Create a single-step playbook
    single_step_pb = Playbook(
        tenant_id=admin_user.tenant_id,  # Round-10 R10-DB-3 — NOT NULL.
        name="Tek Adim Playbook",
        trigger_conditions_json='[{"field": "signal_type", "op": "eq", "value": "churn_risk"}]',
        steps_json='[{"step": 1, "action_type": "task", "template": "Acil gorusme planla", "delay_days": 0, "priority": "urgent"}]',
        is_active=True,
        created_by=admin_user.id,
    )
    db.add(single_step_pb)
    await db.flush()

    signal = RevenueSignal(
        signal_type="churn_risk",
        source_entity_type="opportunity",
        source_entity_id=opportunity.id,
        opportunity_id=opportunity.id,
        owner_id=sales_user.id,
        severity="high",
        confidence=0.8,
    )
    db.add(signal)
    await db.flush()

    service = PlaybookService(db)
    execution = await service.evaluate_signal(signal)
    assert execution is not None

    # Single step playbook should complete immediately after first step
    assert execution.status == "completed"
    assert execution.completed_at is not None
