"""Tests for Behavioral Scoring Service — score updates, auto-enroll, event handling."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.engagement import Sequence, SequenceEnrollment
from app.models.lead import Lead
from app.models.sequence_v2 import DomainEvent
from app.models.user import User
from app.core.security import hash_password


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(
        tenant_id=_TENANT_ID,
        email="scoretest@test.com",
        full_name="Score Tester",
        hashed_password=hash_password("test123"),
        role="sales_rep",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def lead(db: AsyncSession, user: User) -> Lead:
    ld = Lead(
        tenant_id=_TENANT_ID,
        first_name="Score",
        last_name="Test",
        email="scoretest_lead@example.com",
        owner_id=user.id,
        status="new",
        lead_score=50,
    )
    db.add(ld)
    await db.commit()
    await db.refresh(ld)
    return ld


@pytest_asyncio.fixture
async def sequence_with_auto_enroll(db: AsyncSession, user: User) -> Sequence:
    steps = [{"step": 1, "action": "task", "delay_days": 0, "template": "Auto step"}]
    rules = [{"field": "lead_score", "op": "gte", "value": 70}]
    seq = Sequence(
        name="Auto Enroll Sequence",
        steps_json=json.dumps(steps),
        auto_enroll_rules_json=json.dumps(rules),
        is_active=True,
        created_by=user.id,
    )
    db.add(seq)
    await db.commit()
    await db.refresh(seq)
    return seq


class TestUpdateLeadScore:
    @pytest.mark.asyncio
    @patch("app.services.scoring_service.settings")
    async def test_positive_signal_increases_score(self, mock_settings, db: AsyncSession, lead: Lead):
        mock_settings.FEATURE_BEHAVIORAL_SCORING = True

        from app.services.scoring_service import update_lead_score

        result = await update_lead_score(db, lead.id, "email_replied")
        await db.commit()

        assert result is not None
        assert result["old_score"] == 50
        assert result["new_score"] == 65  # +15
        assert result["delta"] == 15

        await db.refresh(lead)
        assert lead.lead_score == 65

    @pytest.mark.asyncio
    @patch("app.services.scoring_service.settings")
    async def test_negative_signal_decreases_score(self, mock_settings, db: AsyncSession, lead: Lead):
        mock_settings.FEATURE_BEHAVIORAL_SCORING = True

        from app.services.scoring_service import update_lead_score

        result = await update_lead_score(db, lead.id, "email_bounced")
        await db.commit()

        assert result is not None
        assert result["new_score"] == 30  # 50 - 20
        assert result["delta"] == -20

    @pytest.mark.asyncio
    @patch("app.services.scoring_service.settings")
    async def test_score_clamped_at_zero(self, mock_settings, db: AsyncSession, lead: Lead):
        mock_settings.FEATURE_BEHAVIORAL_SCORING = True

        from app.services.scoring_service import update_lead_score

        lead.lead_score = 5
        await db.commit()

        result = await update_lead_score(db, lead.id, "email_bounced")  # -20
        await db.commit()

        assert result["new_score"] == 0

    @pytest.mark.asyncio
    @patch("app.services.scoring_service.settings")
    async def test_score_clamped_at_100(self, mock_settings, db: AsyncSession, lead: Lead):
        mock_settings.FEATURE_BEHAVIORAL_SCORING = True

        from app.services.scoring_service import update_lead_score

        lead.lead_score = 95
        await db.commit()

        result = await update_lead_score(db, lead.id, "meeting_booked")  # +20
        await db.commit()

        assert result["new_score"] == 100

    @pytest.mark.asyncio
    @patch("app.services.scoring_service.settings")
    async def test_unknown_signal_returns_none(self, mock_settings, db: AsyncSession, lead: Lead):
        mock_settings.FEATURE_BEHAVIORAL_SCORING = True

        from app.services.scoring_service import update_lead_score

        result = await update_lead_score(db, lead.id, "unknown_signal")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.scoring_service.settings")
    async def test_feature_flag_off_returns_none(self, mock_settings, db: AsyncSession, lead: Lead):
        mock_settings.FEATURE_BEHAVIORAL_SCORING = False

        from app.services.scoring_service import update_lead_score

        result = await update_lead_score(db, lead.id, "email_replied")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.scoring_service.settings")
    async def test_emits_domain_event(self, mock_settings, db: AsyncSession, lead: Lead):
        mock_settings.FEATURE_BEHAVIORAL_SCORING = True

        from app.services.scoring_service import update_lead_score

        await update_lead_score(db, lead.id, "email_replied")
        await db.commit()

        events = (await db.execute(
            select(DomainEvent).where(DomainEvent.event_type == "lead.score_changed")
        )).scalars().all()
        assert len(events) >= 1
        payload = json.loads(events[0].payload_json)
        assert payload["lead_id"] == lead.id
        assert payload["old_score"] == 50
        assert payload["new_score"] == 65


class TestAutoEnroll:
    @pytest.mark.asyncio
    @patch("app.services.scoring_service.settings")
    async def test_auto_enroll_on_threshold(
        self, mock_settings, db: AsyncSession, lead: Lead, sequence_with_auto_enroll: Sequence,
    ):
        mock_settings.FEATURE_BEHAVIORAL_SCORING = True

        from app.services.scoring_service import evaluate_auto_enroll

        # Lead score 50, threshold 70 — should NOT enroll
        result = await evaluate_auto_enroll(db, lead.id)
        assert result == []

        # Raise score above threshold
        lead.lead_score = 75
        await db.commit()

        result = await evaluate_auto_enroll(db, lead.id)
        await db.commit()

        assert sequence_with_auto_enroll.id in result

        # Verify enrollment exists
        enrollments = (await db.execute(
            select(SequenceEnrollment).where(
                SequenceEnrollment.lead_id == lead.id,
                SequenceEnrollment.sequence_id == sequence_with_auto_enroll.id,
            )
        )).scalars().all()
        assert len(enrollments) == 1
        assert enrollments[0].status == "active"

    @pytest.mark.asyncio
    @patch("app.services.scoring_service.settings")
    async def test_auto_enroll_idempotent(
        self, mock_settings, db: AsyncSession, lead: Lead, sequence_with_auto_enroll: Sequence,
    ):
        """Double call should not create duplicate enrollments."""
        mock_settings.FEATURE_BEHAVIORAL_SCORING = True

        from app.services.scoring_service import evaluate_auto_enroll

        lead.lead_score = 80
        await db.commit()

        await evaluate_auto_enroll(db, lead.id)
        await db.commit()

        # Second call
        result2 = await evaluate_auto_enroll(db, lead.id)
        await db.commit()

        assert result2 == []  # Already enrolled

    @pytest.mark.asyncio
    @patch("app.services.scoring_service.settings")
    async def test_no_enroll_converted_lead(
        self, mock_settings, db: AsyncSession, lead: Lead, sequence_with_auto_enroll: Sequence,
    ):
        mock_settings.FEATURE_BEHAVIORAL_SCORING = True

        from app.services.scoring_service import evaluate_auto_enroll

        lead.lead_score = 80
        lead.status = "converted"
        await db.commit()

        result = await evaluate_auto_enroll(db, lead.id)
        assert result == []
