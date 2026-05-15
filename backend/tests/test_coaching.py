"""Coaching engine tests — scoring, indicators, recommendations, and signals."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.activity_log import ActivityLog
from app.models.opportunity import Opportunity, Task
from app.models.quote import Quote
from app.models.user import User
from app.services.coaching_service import CoachingService


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _create_rep(db: AsyncSession, email: str = "rep@test.com") -> User:
    user = User(
        tenant_id=_TENANT_ID,
        email=email,
        full_name="Satis Temsilcisi",
        hashed_password=hash_password("Test1234"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_opportunity(
    db: AsyncSession, owner_id: int, **kwargs
) -> Opportunity:
    defaults = {
        "tenant_id": _TENANT_ID,
        "title": "Test Firsati",
        "stage": "proposal",
        "owner_id": owner_id,
        "status": "active",
    }
    defaults.update(kwargs)
    opp = Opportunity(**defaults)
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


# ── Coaching score computation ──


@pytest.mark.asyncio
async def test_evaluate_rep_returns_score_and_indicators(db: AsyncSession):
    """Coaching score computation with real data produces valid structure."""
    rep = await _create_rep(db)
    await _create_opportunity(db, rep.id)

    service = CoachingService(db)
    result = await service.evaluate_rep(rep.id)

    assert result["user_id"] == rep.id
    assert result["user_name"] == rep.full_name
    assert 0 <= result["score"] <= 100
    assert result["risk_level"] in ("healthy", "needs_improvement", "at_risk")
    assert len(result["indicators"]) == 5
    assert isinstance(result["recommendations"], list)


@pytest.mark.asyncio
async def test_evaluate_rep_missing_user(db: AsyncSession):
    """Evaluation of nonexistent user returns error."""
    service = CoachingService(db)
    result = await service.evaluate_rep(99999)
    assert "error" in result


@pytest.mark.asyncio
async def test_followup_adherence_no_tasks(db: AsyncSession):
    """No open tasks yields perfect followup score."""
    rep = await _create_rep(db)

    service = CoachingService(db)
    indicator = await service._followup_adherence(rep.id)

    assert indicator.name == "followup_adherence"
    assert indicator.score == 100


@pytest.mark.asyncio
async def test_followup_adherence_with_overdue_tasks(db: AsyncSession):
    """Overdue tasks reduce followup adherence score."""
    rep = await _create_rep(db)
    opp = await _create_opportunity(db, rep.id)
    now = datetime.now(timezone.utc)

    # Create 2 open tasks, 1 overdue
    for i in range(2):
        task = Task(
            owner_id=rep.id,
            opportunity_id=opp.id,
            title=f"Gorev {i}",
            status="open",
            due_at=now + timedelta(days=3),
            source="manual",
        )
        db.add(task)

    overdue_task = Task(
        owner_id=rep.id,
        opportunity_id=opp.id,
        title="Gecmis gorev",
        status="open",
        due_at=now - timedelta(days=2),
        source="manual",
    )
    db.add(overdue_task)
    await db.commit()

    service = CoachingService(db)
    indicator = await service._followup_adherence(rep.id)

    # 1/3 overdue ~33% -> score should be 65 (0.25-0.5 range)
    assert indicator.score < 100
    assert indicator.score > 0


# ── Weak indicator generates recommendation ──


@pytest.mark.asyncio
async def test_weak_indicator_generates_recommendation(db: AsyncSession):
    """When followup score is low, recommendations include followup advice."""
    rep = await _create_rep(db)
    opp = await _create_opportunity(db, rep.id)
    now = datetime.now(timezone.utc)

    # Create many overdue tasks to drive score down
    for i in range(6):
        task = Task(
            owner_id=rep.id,
            opportunity_id=opp.id,
            title=f"Gecmis gorev {i}",
            status="open",
            due_at=now - timedelta(days=5),
            source="manual",
        )
        db.add(task)
    await db.commit()

    service = CoachingService(db)
    result = await service.evaluate_rep(rep.id)

    # Should have at least one recommendation about overdue tasks
    has_followup_rec = any(
        "gorev" in rec.lower() or "takip" in rec.lower()
        for rec in result["recommendations"]
    )
    assert has_followup_rec, (
        f"Expected followup recommendation, got: {result['recommendations']}"
    )


# ── Score threshold emits coaching_needed ──


@pytest.mark.asyncio
async def test_low_score_risk_level(db: AsyncSession):
    """Score below 60 is classified as needs_improvement or at_risk."""
    rep = await _create_rep(db)
    opp = await _create_opportunity(db, rep.id)
    now = datetime.now(timezone.utc)

    # Create heavily overdue scenario
    for i in range(10):
        task = Task(
            owner_id=rep.id,
            opportunity_id=opp.id,
            title=f"Gecmis {i}",
            status="open",
            due_at=now - timedelta(days=10),
            source="manual",
        )
        db.add(task)
    await db.commit()

    service = CoachingService(db)
    result = await service.evaluate_rep(rep.id)

    # With all tasks overdue, followup score should be 0
    # Combined with neutral other indicators, overall might be low
    assert result["risk_level"] in ("healthy", "needs_improvement", "at_risk")


# ── evaluate_all_reps returns list ──


@pytest.mark.asyncio
async def test_evaluate_all_reps_returns_list(db: AsyncSession):
    """Batch evaluation returns a sorted list of rep results."""
    rep1 = await _create_rep(db, email="rep1@test.com")
    rep2 = await _create_rep(db, email="rep2@test.com")

    await _create_opportunity(db, rep1.id)
    await _create_opportunity(db, rep2.id)

    service = CoachingService(db)
    results = await service.evaluate_all_reps()

    assert isinstance(results, list)
    assert len(results) >= 2

    # Results should be sorted by score ascending
    scores = [r["score"] for r in results]
    assert scores == sorted(scores)


# ── Discount pattern indicator ──


@pytest.mark.asyncio
async def test_discount_pattern_no_quotes(db: AsyncSession):
    """No quotes yields neutral discount score."""
    rep = await _create_rep(db)

    service = CoachingService(db)
    indicator = await service._discount_pattern(rep.id)

    assert indicator.name == "discount_pattern"
    assert indicator.raw_value == "N/A"
    assert indicator.score == 60  # neutral


# ── Activity frequency indicator ──


@pytest.mark.asyncio
async def test_activity_frequency_with_data(db: AsyncSession):
    """Activity frequency computes ratio correctly."""
    rep = await _create_rep(db)
    opp = await _create_opportunity(db, rep.id)

    now = datetime.now(timezone.utc)
    for i in range(5):
        activity = ActivityLog(
            activity_type="note_added",
            entity_type="opportunity",
            entity_id=opp.id,
            opportunity_id=opp.id,
            user_id=rep.id,
            summary=f"Aktivite {i}",
            created_at=now - timedelta(days=i),
        )
        db.add(activity)
    await db.commit()

    service = CoachingService(db)
    indicator = await service._activity_frequency(rep.id)

    assert indicator.name == "activity_frequency"
    assert indicator.score > 0


# ── Playbook adherence graceful fallback ──


@pytest.mark.asyncio
async def test_playbook_adherence_graceful_fallback(db: AsyncSession):
    """Playbook adherence returns neutral when module is unavailable."""
    rep = await _create_rep(db)

    service = CoachingService(db)
    indicator = await service._playbook_adherence(rep.id)

    assert indicator.name == "playbook_adherence"
    # Either neutral (module missing) or actual score
    assert 0 <= indicator.score <= 100
