"""Tests for Sequence Engine v2 — A/B variants + branching."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.engagement import Sequence, SequenceEnrollment
from app.models.sequence_v2 import SequenceStepRun
from app.models.user import User
from app.models.opportunity import Opportunity
from app.core.security import hash_password
from app.services.sequence_engine import select_variant, evaluate_branch_rules


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(
        tenant_id=_TENANT_ID,
        email="branchtest@test.com",
        full_name="Branch Tester",
        hashed_password=hash_password("test123"),
        role="sales_rep",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def opportunity(db: AsyncSession, user: User) -> Opportunity:
    opp = Opportunity(
        tenant_id=_TENANT_ID,
        title="Branch Deal",
        stage="prospecting",
        owner_id=user.id,
        status="active",
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


class TestVariantBucketing:
    def test_no_variants_returns_none(self):
        assert select_variant([], 100, 1) is None
        assert select_variant(None, 100, 1) is None

    def test_single_variant_always_selected(self):
        variants = [{"key": "A", "template": "Only A", "split_pct": 100}]
        for target_id in range(100):
            result = select_variant(variants, target_id, 1)
            assert result["key"] == "A"

    def test_deterministic_assignment(self):
        """Same (target_id, step_number) always gets the same variant."""
        variants = [
            {"key": "A", "template": "A", "split_pct": 50},
            {"key": "B", "template": "B", "split_pct": 50},
        ]
        first = select_variant(variants, 42, 3)
        for _ in range(10):
            assert select_variant(variants, 42, 3)["key"] == first["key"]

    def test_distribution_roughly_even(self):
        """Over many targets, A/B should be roughly 50/50."""
        variants = [
            {"key": "A", "template": "A", "split_pct": 50},
            {"key": "B", "template": "B", "split_pct": 50},
        ]
        counts = {"A": 0, "B": 0}
        for i in range(1000):
            v = select_variant(variants, i, 1)
            counts[v["key"]] += 1

        # Should be roughly 500/500 — allow 15% tolerance
        assert 350 < counts["A"] < 650
        assert 350 < counts["B"] < 650

    def test_three_way_split(self):
        variants = [
            {"key": "A", "split_pct": 33},
            {"key": "B", "split_pct": 34},
            {"key": "C", "split_pct": 33},
        ]
        counts = {"A": 0, "B": 0, "C": 0}
        for i in range(1000):
            v = select_variant(variants, i, 1)
            counts[v["key"]] += 1

        for k in counts:
            assert 200 < counts[k] < 500  # Each should be ~333


class TestBranchRules:
    def test_no_rules_returns_none(self):
        assert evaluate_branch_rules([], "replied", []) is None
        assert evaluate_branch_rules(None, "replied", []) is None

    def test_no_outcome_returns_none(self):
        rules = [{"condition": "replied", "goto_step": 4}]
        assert evaluate_branch_rules(rules, None, [1, 2, 3, 4]) is None

    def test_matching_rule_returns_goto(self):
        steps = [{"step": i} for i in range(1, 6)]
        rules = [
            {"condition": "replied", "goto_step": 4},
            {"condition": "no_engagement", "goto_step": 3},
        ]
        assert evaluate_branch_rules(rules, "replied", steps) == 4
        assert evaluate_branch_rules(rules, "no_engagement", steps) == 3

    def test_no_match_returns_none(self):
        steps = [{"step": i} for i in range(1, 4)]
        rules = [{"condition": "replied", "goto_step": 3}]
        assert evaluate_branch_rules(rules, "opened", steps) is None

    def test_invalid_goto_step_ignored(self):
        steps = [{"step": 1}, {"step": 2}]
        rules = [{"condition": "replied", "goto_step": 99}]  # Out of range
        assert evaluate_branch_rules(rules, "replied", steps) is None


class TestStepSchemaV2Integration:
    @pytest.mark.asyncio
    async def test_old_format_still_works(
        self, db: AsyncSession, user: User, opportunity: Opportunity,
    ):
        """Old step format (no variants, no branch_rules) should work unchanged."""
        from app.services.sequence_engine import execute_step_v2

        old_steps = [
            {"step": 1, "action": "task", "delay_days": 0, "template": "Old format step"},
        ]
        seq = Sequence(
            name="Old Format",
            steps_json=json.dumps(old_steps),
            is_active=True,
            created_by=user.id,
        )
        db.add(seq)
        await db.commit()
        await db.refresh(seq)

        enrollment = SequenceEnrollment(
            sequence_id=seq.id,
            opportunity_id=opportunity.id,
            enrolled_by=user.id,
            current_step=1,
            status="active",
            next_action_at=datetime.now(timezone.utc),
        )
        db.add(enrollment)
        await db.commit()
        await db.refresh(enrollment)

        result = await execute_step_v2(db, enrollment)
        await db.commit()

        assert "Step 1 executed" in result
        await db.refresh(enrollment)
        assert enrollment.status == "completed"

    @pytest.mark.asyncio
    async def test_variant_recorded_in_step_run(
        self, db: AsyncSession, user: User, opportunity: Opportunity,
    ):
        """When step has variants, the selected variant_key should be recorded."""
        from app.services.sequence_engine import execute_step_v2

        v2_steps = [
            {
                "step": 1,
                "action": "email",
                "delay_days": 0,
                "template": "Default",
                "variants": [
                    {"key": "A", "template": "Variant A", "split_pct": 50},
                    {"key": "B", "template": "Variant B", "split_pct": 50},
                ],
            },
        ]
        seq = Sequence(
            name="AB Test Sequence",
            steps_json=json.dumps(v2_steps),
            is_active=True,
            created_by=user.id,
        )
        db.add(seq)
        await db.commit()
        await db.refresh(seq)

        enrollment = SequenceEnrollment(
            sequence_id=seq.id,
            opportunity_id=opportunity.id,
            enrolled_by=user.id,
            current_step=1,
            status="active",
            next_action_at=datetime.now(timezone.utc),
        )
        db.add(enrollment)
        await db.commit()
        await db.refresh(enrollment)

        await execute_step_v2(db, enrollment)
        await db.commit()

        run = (await db.execute(
            select(SequenceStepRun).where(
                SequenceStepRun.enrollment_id == enrollment.id,
                SequenceStepRun.step_number == 1,
            )
        )).scalar_one()

        assert run.variant_key in ("A", "B")
        assert run.step_action == "email"

    @pytest.mark.asyncio
    async def test_mixed_v1_v2_steps(
        self, db: AsyncSession, user: User, opportunity: Opportunity,
    ):
        """Sequence with mix of old and new format steps should work."""
        from app.services.sequence_engine import execute_step_v2

        mixed_steps = [
            {"step": 1, "action": "task", "delay_days": 0, "template": "Plain task"},
            {
                "step": 2,
                "action": "email",
                "delay_days": 0,
                "template": "Default email",
                "variants": [
                    {"key": "A", "template": "A version", "split_pct": 100},
                ],
            },
        ]
        seq = Sequence(
            name="Mixed Sequence",
            steps_json=json.dumps(mixed_steps),
            is_active=True,
            created_by=user.id,
        )
        db.add(seq)
        await db.commit()
        await db.refresh(seq)

        enrollment = SequenceEnrollment(
            sequence_id=seq.id,
            opportunity_id=opportunity.id,
            enrolled_by=user.id,
            current_step=1,
            status="active",
            next_action_at=datetime.now(timezone.utc),
        )
        db.add(enrollment)
        await db.commit()
        await db.refresh(enrollment)

        # Step 1: old format (no variant)
        await execute_step_v2(db, enrollment)
        await db.commit()
        await db.refresh(enrollment)

        run1 = (await db.execute(
            select(SequenceStepRun).where(
                SequenceStepRun.enrollment_id == enrollment.id,
                SequenceStepRun.step_number == 1,
            )
        )).scalar_one()
        assert run1.variant_key is None

        # Step 2: v2 format (with variant A at 100%)
        await execute_step_v2(db, enrollment)
        await db.commit()

        run2 = (await db.execute(
            select(SequenceStepRun).where(
                SequenceStepRun.enrollment_id == enrollment.id,
                SequenceStepRun.step_number == 2,
            )
        )).scalar_one()
        assert run2.variant_key == "A"
