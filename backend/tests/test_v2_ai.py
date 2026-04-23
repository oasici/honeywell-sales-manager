"""v2 AI + Signals + Tasks endpoint tests."""

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import patch
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.opportunity import Opportunity, Task
from app.models.user import User


async def _mgr(db: AsyncSession) -> tuple[User, dict]:
    user = User(email="ai_mgr@test.com", full_name="AI Manager",
                hashed_password=hash_password("Test1234"), role="sales_manager", is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


@pytest.fixture(autouse=True)
def _enable_flags():
    with patch("app.api.v1.ai.settings") as m:
        m.FEATURE_AI_SUMMARIES = True
        m.FEATURE_AI_PIPELINE_SUGGESTIONS = True
        m.FEATURE_TASKS = True
        m.ANTHROPIC_API_KEY = ""
        m.AI_MODEL_NAME = "test"
        m.AI_MAX_TOKENS = 100
        yield


@pytest.mark.asyncio
async def test_summarize_changes_opportunity(client: AsyncClient, db: AsyncSession):
    user, h = await _mgr(db)
    opp = Opportunity(title="Chg", stage="prospecting", owner_id=user.id)
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    r = await client.post(
        "/api/v1/ai/summarize/changes",
        json={"entity_type": "opportunity", "entity_id": opp.id, "days": 7},
        headers=h,
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("days") == 7
    assert "summary" in data
    assert isinstance(data.get("sources"), list)


@pytest.mark.asyncio
async def test_summarize_changes_customer(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    cust = Customer(name="C1", email="c1_ai_ch@test.com", company="Co")
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    r = await client.post(
        "/api/v1/ai/summarize/changes",
        json={"entity_type": "customer", "entity_id": cust.id, "days": 3},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json().get("days") == 3


@pytest.mark.asyncio
async def test_summarize_changes_invalid_entity(client: AsyncClient, db: AsyncSession):
    user, h = await _mgr(db)
    opp = Opportunity(title="X", stage="prospecting", owner_id=user.id)
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    r = await client.post(
        "/api/v1/ai/summarize/changes",
        json={"entity_type": "quote", "entity_id": opp.id, "days": 7},
        headers=h,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_summarize_fallback(client: AsyncClient, db: AsyncSession):
    user, h = await _mgr(db)
    opp = Opportunity(title="Test Deal", stage="prospecting", owner_id=user.id)
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    r = await client.post("/api/v1/ai/summarize", json={
        "entity_type": "opportunity", "entity_id": opp.id,
    }, headers=h)
    assert r.status_code == 200
    assert "summary" in r.json()


@pytest.mark.asyncio
async def test_suggest_pipeline_update(client: AsyncClient, db: AsyncSession):
    user, h = await _mgr(db)
    opp = Opportunity(title="Stale Deal", stage="prospecting", owner_id=user.id)
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    r = await client.post("/api/v1/ai/suggest-pipeline-update", json={
        "opportunity_id": opp.id,
    }, headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "suggested_next_steps" in d
    assert "factors" in d


@pytest.mark.asyncio
async def test_suggest_pipeline_staleness_uses_activity_log(client: AsyncClient, db: AsyncSession):
    """no_touch staleness aligns with board: max(ActivityLog) else updated_at."""
    user, h = await _mgr(db)
    opp = Opportunity(title="Touchy Deal", stage="prospecting", owner_id=user.id)
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    log = ActivityLog(
        activity_type="note_added",
        entity_type="opportunity",
        entity_id=opp.id,
        opportunity_id=opp.id,
        user_id=user.id,
        summary="seed",
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    old = datetime.now(timezone.utc) - timedelta(days=20)
    await db.execute(update(ActivityLog).where(ActivityLog.id == log.id).values(created_at=old))
    opp.updated_at = datetime.now(timezone.utc)
    await db.commit()

    r = await client.post(
        "/api/v1/ai/suggest-pipeline-update",
        json={"opportunity_id": opp.id},
        headers=h,
    )
    assert r.status_code == 200
    factors = r.json().get("factors") or []
    assert any("dokunulmamis" in str(f).lower() for f in factors)
    assert any("20" in str(f) for f in factors)


@pytest.mark.asyncio
async def test_extract_signals_empty(client: AsyncClient, db: AsyncSession):
    user, h = await _mgr(db)
    opp = Opportunity(title="Signal Deal", stage="qualified", owner_id=user.id)
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    r = await client.post("/api/v1/ai/extract-signals", json={
        "opportunity_id": opp.id,
    }, headers=h)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_tasks_crud(client: AsyncClient, db: AsyncSession):
    user, h = await _mgr(db)

    # Create
    r = await client.post("/api/v1/ai/tasks", json={
        "title": "Musteriyi ara", "priority": "high",
    }, headers=h)
    assert r.status_code == 201
    task_id = r.json()["id"]

    # List
    r = await client.get("/api/v1/ai/tasks?status=open", headers=h)
    assert r.status_code == 200
    assert len(r.json()["tasks"]) >= 1

    # Complete
    r = await client.patch(f"/api/v1/ai/tasks/{task_id}", json={"status": "done"}, headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "done"


@pytest.mark.asyncio
async def test_signals_404_when_flag_off(client: AsyncClient, db: AsyncSession):
    user, h = await _mgr(db)
    with patch("app.api.v1.ai.settings") as m:
        m.FEATURE_AI_SUMMARIES = False
        m.FEATURE_AI_PIPELINE_SUGGESTIONS = False
        r = await client.post("/api/v1/ai/summarize", json={
            "entity_type": "opportunity", "entity_id": 999,
        }, headers=h)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_weekly_diff(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/analytics/pipeline-weekly-diff", headers=h)
    assert r.status_code == 200
    assert "new_opportunities" in r.json()


@pytest.mark.asyncio
async def test_discount_guardrails(client: AsyncClient, db: AsyncSession):
    _, h = await _mgr(db)
    r = await client.get("/api/v1/analytics/discount-guardrails", headers=h)
    assert r.status_code == 200
    assert "flagged_count" in r.json()
