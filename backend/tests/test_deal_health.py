"""Deal health scoring tests — indicators, aggregation, and edge cases."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.activity_log import ActivityLog
from app.models.email_request import EmailRequest
from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal, Task
from app.models.quote import Quote
from app.models.user import User
from app.services.deal_health_service import DealHealthService


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _create_user(db: AsyncSession) -> User:
    user = User(
        tenant_id=_TENANT_ID,
        email="deal_health@test.com",
        full_name="Deal Health Tester",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _create_opportunity(db: AsyncSession, owner_id: int, **kwargs) -> Opportunity:
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


# ── Service-level tests ──


@pytest.mark.asyncio
async def test_compute_deal_health_returns_none_for_missing_opportunity(db: AsyncSession):
    service = DealHealthService(db)
    result = await service.compute_deal_health(999)
    assert result is None


@pytest.mark.asyncio
async def test_compute_deal_health_returns_report(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    service = DealHealthService(db)
    report = await service.compute_deal_health(opp.id)

    assert report is not None
    assert report.opportunity_id == opp.id
    assert 0 <= report.score <= 100
    assert report.risk_level in ("healthy", "at_risk", "high_risk", "critical")
    assert len(report.indicators) == 6


@pytest.mark.asyncio
async def test_activity_recency_no_activity(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    service = DealHealthService(db)
    indicator = await service._activity_recency(opp.id)

    assert indicator.name == "activity_recency"
    assert indicator.score == 0
    assert indicator.raw_value == "yok"


@pytest.mark.asyncio
async def test_activity_recency_recent_activity(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    activity = ActivityLog(
        activity_type="note_added",
        entity_type="opportunity",
        entity_id=opp.id,
        opportunity_id=opp.id,
        summary="Test notu",
        created_at=datetime.now(timezone.utc) - timedelta(hours=12),
    )
    db.add(activity)
    await db.commit()

    service = DealHealthService(db)
    indicator = await service._activity_recency(opp.id)

    assert indicator.score == 100
    assert indicator.raw_value == 0


@pytest.mark.asyncio
async def test_activity_recency_old_activity(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    activity = ActivityLog(
        activity_type="note_added",
        entity_type="opportunity",
        entity_id=opp.id,
        opportunity_id=opp.id,
        summary="Eski notu",
        created_at=datetime.now(timezone.utc) - timedelta(days=20),
    )
    db.add(activity)
    await db.commit()

    service = DealHealthService(db)
    indicator = await service._activity_recency(opp.id)

    assert indicator.score == 25


@pytest.mark.asyncio
async def test_email_engagement_no_emails(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    service = DealHealthService(db)
    indicator = await service._email_engagement(opp.id)

    assert indicator.name == "email_engagement"
    assert indicator.score == 25
    assert indicator.raw_value == 0


@pytest.mark.asyncio
async def test_email_engagement_many_emails(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    for i in range(6):
        email = EmailRequest(
            message_id=f"msg-health-{i}@test.com",
            from_address="customer@example.com",
            opportunity_id=opp.id,
            created_at=datetime.now(timezone.utc) - timedelta(days=i),
        )
        db.add(email)
    await db.commit()

    service = DealHealthService(db)
    indicator = await service._email_engagement(opp.id)

    assert indicator.score == 100
    assert indicator.raw_value == 6


@pytest.mark.asyncio
async def test_quote_progress_no_quotes(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    service = DealHealthService(db)
    indicator = await service._quote_progress(opp.id)

    assert indicator.name == "quote_progress"
    assert indicator.score == 0
    assert indicator.raw_value == "yok"


@pytest.mark.asyncio
async def test_quote_progress_with_sent_quote(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    quote = Quote(
        tenant_id=_TENANT_ID,
        quote_number="HW-TEST-001",
        opportunity_id=opp.id,
        status="sent",
    )
    db.add(quote)
    await db.commit()

    service = DealHealthService(db)
    indicator = await service._quote_progress(opp.id)

    assert indicator.score == 100


@pytest.mark.asyncio
async def test_task_completion_no_tasks(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    service = DealHealthService(db)
    indicator = await service._task_completion(opp.id)

    assert indicator.name == "task_completion"
    assert indicator.score == 50  # neutral when no tasks


@pytest.mark.asyncio
async def test_task_completion_mixed_tasks(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    for i, status in enumerate(["done", "done", "open", "open"]):
        task = Task(
            tenant_id=_TENANT_ID,
            title=f"Gorev {i}",
            owner_id=user.id,
            opportunity_id=opp.id,
            status=status,
        )
        db.add(task)
    await db.commit()

    service = DealHealthService(db)
    indicator = await service._task_completion(opp.id)

    assert indicator.score == 50  # 2/4 = 50%
    assert indicator.raw_value == "2/4"


@pytest.mark.asyncio
async def test_signal_balance_no_signals(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    service = DealHealthService(db)
    indicator = await service._signal_balance(opp.id)

    assert indicator.name == "signal_balance"
    assert indicator.score == 50  # neutral


@pytest.mark.asyncio
async def test_signal_balance_mostly_positive(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    for _ in range(3):
        db.add(OpportunitySignal(
            tenant_id=opp.tenant_id,
            opportunity_id=opp.id,
            signal_type="positive",
            severity="low",
        ))
    db.add(OpportunitySignal(
        tenant_id=opp.tenant_id,
        opportunity_id=opp.id,
        signal_type="pricing_concern",
        severity="med",
    ))
    await db.commit()

    service = DealHealthService(db)
    indicator = await service._signal_balance(opp.id)

    assert indicator.score == 75  # 3/4 positive


@pytest.mark.asyncio
async def test_weighted_aggregation(db: AsyncSession):
    """Total score is a weighted average of all indicators."""
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    service = DealHealthService(db)
    report = await service.compute_deal_health(opp.id)

    assert report is not None
    # Manually verify the weighted calculation
    total_weight = sum(i.weight for i in report.indicators)
    weighted_sum = sum(i.score * i.weight for i in report.indicators)
    expected_score = max(0, min(100, round(weighted_sum / total_weight)))
    assert report.score == expected_score


@pytest.mark.asyncio
async def test_risk_level_thresholds(db: AsyncSession):
    """Verify risk level assignment based on score thresholds."""
    service = DealHealthService(db)

    assert service._determine_risk_level(80) == "healthy"
    assert service._determine_risk_level(70) == "healthy"
    assert service._determine_risk_level(69) == "at_risk"
    assert service._determine_risk_level(40) == "at_risk"
    assert service._determine_risk_level(39) == "high_risk"
    assert service._determine_risk_level(20) == "high_risk"
    assert service._determine_risk_level(19) == "critical"
    assert service._determine_risk_level(0) == "critical"


@pytest.mark.asyncio
async def test_recommendations_generated_for_weak_indicators(db: AsyncSession):
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)

    # No data means some indicators score low -> recommendations
    service = DealHealthService(db)
    report = await service.compute_deal_health(opp.id)

    assert report is not None
    # With no activity and no quotes, recommendations should exist
    assert len(report.recommendations) > 0


@pytest.mark.asyncio
async def test_get_all_deal_health(db: AsyncSession):
    user = await _create_user(db)
    await _create_opportunity(db, user.id, title="Firsat A")
    await _create_opportunity(db, user.id, title="Firsat B")

    service = DealHealthService(db)
    reports = await service.get_all_deal_health()

    assert len(reports) >= 2
    # Should be sorted by score ascending
    scores = [r.score for r in reports]
    assert scores == sorted(scores)


@pytest.mark.asyncio
async def test_get_all_deal_health_filtered_by_owner(db: AsyncSession):
    user = await _create_user(db)
    await _create_opportunity(db, user.id, title="Firsat Owned")

    service = DealHealthService(db)
    reports = await service.get_all_deal_health(owner_id=user.id)

    assert all(r.opportunity_id is not None for r in reports)


@pytest.mark.asyncio
async def test_get_at_risk(db: AsyncSession):
    user = await _create_user(db)
    await _create_opportunity(db, user.id)

    service = DealHealthService(db)
    at_risk = await service.get_at_risk(threshold=100)

    # With threshold=100, most deals should appear
    assert isinstance(at_risk, list)


# ── API endpoint tests ──


@pytest.mark.asyncio
async def test_deal_health_endpoint_feature_flag_disabled(client: AsyncClient, db: AsyncSession):
    """Should return 403 when feature flag is disabled."""
    user = await _create_user(db)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}

    response = await client.get("/api/v1/deal-health/1", headers=headers)
    # Feature flag is False by default in test settings
    assert response.status_code == 403


@pytest.fixture
def _enable_deal_health(monkeypatch: pytest.MonkeyPatch) -> None:
    """``/deal-health/*`` is gated by ``FEATURE_DEAL_HEALTH`` (off in
    test config). Enable for the response_model smoke tests below."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "FEATURE_DEAL_HEALTH", True)


@pytest.mark.asyncio
async def test_deal_health_endpoint_responds_200_with_real_indicators(
    client: AsyncClient,
    db: AsyncSession,
    _enable_deal_health,
):
    """GET /deal-health/{id} round-trips through response_model.

    Round-16 regression guard — the Round-16 N15-API-7 batch 4 typed
    the endpoint as ``DealHealthReportRow``. An over-narrow declaration
    on a nested field (``DealHealthIndicatorRow.raw_value: str`` while
    runtime emits int) caused a 500 with 21 ResponseValidationErrors
    in prod. This test exercises the actual HTTP serialization so the
    same class of regression is caught locally.
    """
    user = await _create_user(db)
    opp = await _create_opportunity(db, user.id)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}

    response = await client.get(f"/api/v1/deal-health/{opp.id}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["opportunity_id"] == opp.id
    # Every indicator must serialize cleanly. raw_value is intentionally
    # untyped on the schema — runtime emits int / float / str / None.
    assert isinstance(body["indicators"], list)
    for ind in body["indicators"]:
        assert "name" in ind
        assert "raw_value" in ind  # may be int, float, str, or None


@pytest.mark.asyncio
async def test_deal_health_at_risk_endpoint_responds_200(
    client: AsyncClient,
    db: AsyncSession,
    _enable_deal_health,
):
    """GET /deal-health/at-risk/list serialises the list response.

    Prod hit a ``response_model`` 500 here when a nested field type
    was narrower than runtime. The list-shape test catches both the
    list envelope and the nested indicator validation in one shot.
    """
    user = await _create_user(db)
    await _create_opportunity(db, user.id)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}

    response = await client.get(
        "/api/v1/deal-health/at-risk/list?threshold=100", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "threshold" in body
    assert "count" in body
    assert isinstance(body["opportunities"], list)


@pytest.mark.asyncio
async def test_deal_health_overview_endpoint_responds_200(
    client: AsyncClient,
    db: AsyncSession,
    _enable_deal_health,
):
    """GET /deal-health/overview/all — same regression class."""
    user = await _create_user(db)
    await _create_opportunity(db, user.id)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}

    response = await client.get("/api/v1/deal-health/overview/all", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "summary" in body
    assert isinstance(body["opportunities"], list)
