"""Tests for Sequence Engine v2 — idempotency, global exit, event emission."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.engagement import Sequence, SequenceEnrollment
from app.models.lead import Lead
from app.models.opportunity import Opportunity, Task
from app.models.sequence_v2 import DomainEvent, SequenceStepRun
from app.models.user import User
from app.core.security import hash_password


# ── Fixtures ──


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(
        email="seqtest@test.com",
        full_name="Seq Tester",
        hashed_password=hash_password("test123"),
        role="sales_rep",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def sequence(db: AsyncSession, user: User) -> Sequence:
    steps = [
        {"step": 1, "action": "task", "delay_days": 0, "template": "Initial call"},
        {"step": 2, "action": "email", "delay_days": 2, "template": "Follow up email"},
        {"step": 3, "action": "task", "delay_days": 3, "template": "Final check"},
    ]
    seq = Sequence(
        name="Test Sequence",
        steps_json=json.dumps(steps),
        is_active=True,
        created_by=user.id,
    )
    db.add(seq)
    await db.commit()
    await db.refresh(seq)
    return seq


@pytest_asyncio.fixture
async def opportunity(db: AsyncSession, user: User) -> Opportunity:
    opp = Opportunity(
        title="Test Deal",
        stage="prospecting",
        owner_id=user.id,
        status="active",
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


@pytest_asyncio.fixture
async def lead(db: AsyncSession, user: User) -> Lead:
    ld = Lead(
        first_name="Test",
        last_name="Lead",
        email="testlead@example.com",
        owner_id=user.id,
        status="new",
    )
    db.add(ld)
    await db.commit()
    await db.refresh(ld)
    return ld


@pytest_asyncio.fixture
async def enrollment(
    db: AsyncSession, sequence: Sequence, opportunity: Opportunity, user: User,
) -> SequenceEnrollment:
    e = SequenceEnrollment(
        sequence_id=sequence.id,
        opportunity_id=opportunity.id,
        enrolled_by=user.id,
        current_step=1,
        status="active",
        next_action_at=datetime.now(timezone.utc),
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


# ── Domain Events Service Tests ──


class TestDomainEvents:
    @pytest.mark.asyncio
    async def test_emit_domain_event_persists(self, db: AsyncSession):
        """emit_domain_event should write a row to domain_events table."""
        from app.services.domain_events import DomainEvents, emit_domain_event

        await emit_domain_event(
            db,
            DomainEvents.SEQUENCE_STEP_COMPLETED,
            {"enrollment_id": 1, "step_number": 1, "step_action": "task"},
            entity_type="sequence_enrollment",
            entity_id=1,
            actor_id=99,
        )
        await db.commit()

        result = await db.execute(
            select(DomainEvent).where(
                DomainEvent.event_type == DomainEvents.SEQUENCE_STEP_COMPLETED
            )
        )
        event = result.scalar_one_or_none()
        assert event is not None
        assert event.entity_type == "sequence_enrollment"
        assert event.actor_id == 99
        payload = json.loads(event.payload_json)
        assert payload["enrollment_id"] == 1

    @pytest.mark.asyncio
    async def test_emit_domain_event_no_persist(self, db: AsyncSession):
        """When persist=False, no DB row should be created."""
        from app.services.domain_events import DomainEvents, emit_domain_event

        await emit_domain_event(
            db,
            DomainEvents.SEQUENCE_COMPLETED,
            {"enrollment_id": 2},
            persist=False,
        )
        await db.commit()

        result = await db.execute(
            select(DomainEvent).where(DomainEvent.event_type == DomainEvents.SEQUENCE_COMPLETED)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_event_payload_serialization(self, db: AsyncSession):
        """Payload with datetime should serialize correctly."""
        from app.services.domain_events import emit_domain_event

        now = datetime.now(timezone.utc)
        await emit_domain_event(
            db,
            "test.serialization",
            {"timestamp": now, "value": 42.5},
        )
        await db.commit()

        result = await db.execute(
            select(DomainEvent).where(DomainEvent.event_type == "test.serialization")
        )
        event = result.scalar_one()
        payload = json.loads(event.payload_json)
        assert payload["value"] == 42.5
        assert isinstance(payload["timestamp"], str)


# ── Sequence Engine Tests ──


class TestSequenceEngine:
    @pytest.mark.asyncio
    async def test_execute_step_creates_task(
        self, db: AsyncSession, enrollment: SequenceEnrollment,
    ):
        """Step with action=task should create a Task record."""
        from app.services.sequence_engine import execute_step_v2

        result = await execute_step_v2(db, enrollment)
        await db.commit()

        assert "Step 1 executed" in result

        # Task created
        tasks = (await db.execute(
            select(Task).where(Task.opportunity_id == enrollment.opportunity_id)
        )).scalars().all()
        assert len(tasks) >= 1
        assert tasks[0].source == "rule"

    @pytest.mark.asyncio
    async def test_step_run_recorded(
        self, db: AsyncSession, enrollment: SequenceEnrollment,
    ):
        """After executing a step, a SequenceStepRun should exist."""
        from app.services.sequence_engine import execute_step_v2

        await execute_step_v2(db, enrollment)
        await db.commit()

        runs = (await db.execute(
            select(SequenceStepRun).where(
                SequenceStepRun.enrollment_id == enrollment.id
            )
        )).scalars().all()
        assert len(runs) == 1
        assert runs[0].step_number == 1
        assert runs[0].step_action == "task"
        assert runs[0].status == "completed"

    @pytest.mark.asyncio
    async def test_idempotent_double_execution(
        self, db: AsyncSession, enrollment: SequenceEnrollment,
    ):
        """Running execute_step_v2 twice for same enrollment should not create duplicate StepRuns."""
        from app.services.sequence_engine import execute_step_v2

        # First execution
        await execute_step_v2(db, enrollment)
        await db.commit()

        # Reset current_step to 1 to simulate retry
        enrollment.current_step = 1
        await db.commit()

        # Second execution (should be idempotent)
        result2 = await execute_step_v2(db, enrollment)
        await db.commit()

        assert "already ran" in result2

        # Only 1 StepRun should exist for step 1
        runs = (await db.execute(
            select(SequenceStepRun).where(
                SequenceStepRun.enrollment_id == enrollment.id,
                SequenceStepRun.step_number == 1,
            )
        )).scalars().all()
        assert len(runs) == 1

    @pytest.mark.asyncio
    async def test_sequence_completion(
        self, db: AsyncSession, enrollment: SequenceEnrollment,
    ):
        """After executing all steps, enrollment should be completed."""
        from app.services.sequence_engine import execute_step_v2

        # Execute all 3 steps
        for _ in range(3):
            await execute_step_v2(db, enrollment)
            await db.commit()
            await db.refresh(enrollment)

        assert enrollment.status == "completed"
        assert enrollment.exit_reason == "all_steps_completed"
        assert enrollment.completed_at is not None

    @pytest.mark.asyncio
    async def test_domain_event_emitted_on_step(
        self, db: AsyncSession, enrollment: SequenceEnrollment,
    ):
        """Step execution should emit a sequence.step_completed domain event."""
        from app.services.domain_events import DomainEvents
        from app.services.sequence_engine import execute_step_v2

        await execute_step_v2(db, enrollment)
        await db.commit()

        events = (await db.execute(
            select(DomainEvent).where(
                DomainEvent.event_type == DomainEvents.SEQUENCE_STEP_COMPLETED
            )
        )).scalars().all()
        assert len(events) >= 1
        payload = json.loads(events[0].payload_json)
        assert payload["enrollment_id"] == enrollment.id
        assert payload["step_number"] == 1


# ── Global Exit Tests ──


class TestGlobalExit:
    @pytest.mark.asyncio
    async def test_exit_on_lead_converted(
        self,
        db: AsyncSession,
        sequence: Sequence,
        lead: Lead,
        user: User,
    ):
        """Enrollment should exit when linked lead is converted."""
        from app.services.sequence_engine import execute_step_v2

        enrollment = SequenceEnrollment(
            sequence_id=sequence.id,
            lead_id=lead.id,
            enrolled_by=user.id,
            current_step=1,
            status="active",
            next_action_at=datetime.now(timezone.utc),
        )
        db.add(enrollment)
        await db.commit()
        await db.refresh(enrollment)

        # Convert the lead
        lead.status = "converted"
        await db.commit()

        # Execute — should exit instead of running step
        result = await execute_step_v2(db, enrollment)
        await db.commit()
        await db.refresh(enrollment)

        assert enrollment.status == "exited"
        assert enrollment.exit_reason == "lead_converted"
        assert "exited" in result

    @pytest.mark.asyncio
    async def test_exit_on_opp_closed(
        self,
        db: AsyncSession,
        enrollment: SequenceEnrollment,
        opportunity: Opportunity,
    ):
        """Enrollment should exit when linked opportunity is closed."""
        from app.services.sequence_engine import execute_step_v2

        # Close the opportunity
        opportunity.status = "closed"
        await db.commit()

        result = await execute_step_v2(db, enrollment)
        await db.commit()
        await db.refresh(enrollment)

        assert enrollment.status == "exited"
        assert enrollment.exit_reason == "opp_closed"

    @pytest.mark.asyncio
    async def test_no_exit_when_active(
        self,
        db: AsyncSession,
        enrollment: SequenceEnrollment,
    ):
        """Enrollment should continue normally when no exit conditions met."""
        from app.services.sequence_engine import execute_step_v2

        result = await execute_step_v2(db, enrollment)
        await db.commit()
        await db.refresh(enrollment)

        assert enrollment.status == "active"
        assert enrollment.current_step == 2
        assert "Step 1 executed" in result

    @pytest.mark.asyncio
    async def test_exit_emits_domain_event(
        self,
        db: AsyncSession,
        enrollment: SequenceEnrollment,
        opportunity: Opportunity,
    ):
        """Exiting should emit a sequence.exited domain event."""
        from app.services.domain_events import DomainEvents
        from app.services.sequence_engine import execute_step_v2

        opportunity.status = "closed"
        await db.commit()

        await execute_step_v2(db, enrollment)
        await db.commit()

        events = (await db.execute(
            select(DomainEvent).where(
                DomainEvent.event_type == DomainEvents.SEQUENCE_EXITED
            )
        )).scalars().all()
        assert len(events) >= 1
        payload = json.loads(events[0].payload_json)
        assert payload["exit_reason"] == "opp_closed"


# ── StepRun Model Tests ──


class TestStepRunModel:
    @pytest.mark.asyncio
    async def test_unique_constraint(
        self, db: AsyncSession, enrollment: SequenceEnrollment,
    ):
        """Two StepRuns with same enrollment_id+step_number should raise."""
        from sqlalchemy.exc import IntegrityError

        run1 = SequenceStepRun(
            enrollment_id=enrollment.id,
            sequence_id=enrollment.sequence_id,
            step_number=1,
            step_action="task",
            status="completed",
        )
        db.add(run1)
        await db.commit()

        run2 = SequenceStepRun(
            enrollment_id=enrollment.id,
            sequence_id=enrollment.sequence_id,
            step_number=1,
            step_action="task",
            status="completed",
        )
        db.add(run2)

        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()
