"""v2 Opportunity CRUD + Board + RBAC tests."""

import pytest
from unittest.mock import patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.opportunity import Opportunity
from app.models.user import User


async def _create_user(db: AsyncSession, email: str, role: str) -> User:
    user = User(
        email=email, full_name=f"Test {role}",
        hashed_password=hash_password("Test1234"),
        role=role, is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


# All tests patch the feature flag to ON
@pytest.fixture(autouse=True)
def _enable_v2_board():
    with patch("app.api.v1.opportunities.settings") as mock_settings:
        mock_settings.FEATURE_V2_BOARD = True
        yield


# ── Feature flag gating ──

@pytest.mark.asyncio
async def test_opportunities_404_when_flag_off(client: AsyncClient, db: AsyncSession):
    """Endpoints return 404 when FEATURE_V2_BOARD is False."""
    mgr = await _create_user(db, "flag_mgr@test.com", "sales_manager")
    with patch("app.api.v1.opportunities.settings") as ms:
        ms.FEATURE_V2_BOARD = False
        r = await client.get("/api/v1/opportunities/", headers=_auth(mgr))
        assert r.status_code == 404


# ── CRUD ──

@pytest.mark.asyncio
async def test_create_opportunity(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "opp_create@test.com", "sales_manager")
    r = await client.post("/api/v1/opportunities/", json={
        "title": "Test Deal",
        "stage": "prospecting",
        "amount": 50000,
    }, headers=_auth(mgr))
    assert r.status_code == 201
    d = r.json()
    assert d["title"] == "Test Deal"
    assert d["stage"] == "prospecting"
    assert d["owner_id"] == mgr.id


@pytest.mark.asyncio
async def test_list_opportunities(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "opp_list@test.com", "sales_manager")
    h = _auth(mgr)
    await client.post("/api/v1/opportunities/", json={"title": "Deal A"}, headers=h)
    await client.post("/api/v1/opportunities/", json={"title": "Deal B"}, headers=h)

    r = await client.get("/api/v1/opportunities/", headers=h)
    assert r.status_code == 200
    assert r.json()["total"] >= 2


@pytest.mark.asyncio
async def test_get_opportunity_detail(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "opp_detail@test.com", "sales_manager")
    h = _auth(mgr)
    cr = await client.post("/api/v1/opportunities/", json={"title": "Detail Deal"}, headers=h)
    opp_id = cr.json()["id"]

    r = await client.get(f"/api/v1/opportunities/{opp_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["title"] == "Detail Deal"
    assert "open_quotes_count" in r.json()


@pytest.mark.asyncio
async def test_update_opportunity_stage(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "opp_update@test.com", "sales_manager")
    h = _auth(mgr)
    cr = await client.post("/api/v1/opportunities/", json={"title": "Update Deal"}, headers=h)
    opp_id = cr.json()["id"]

    r = await client.patch(f"/api/v1/opportunities/{opp_id}", json={"stage": "qualified"}, headers=h)
    assert r.status_code == 200
    assert r.json()["stage"] == "qualified"


# ── RBAC ──

@pytest.mark.asyncio
async def test_rep_cannot_see_other_reps_opportunity(client: AsyncClient, db: AsyncSession):
    rep_a = await _create_user(db, "opp_repa@test.com", "sales_rep")
    rep_b = await _create_user(db, "opp_repb@test.com", "sales_rep")

    cr = await client.post("/api/v1/opportunities/", json={"title": "Rep A Deal"}, headers=_auth(rep_a))
    opp_id = cr.json()["id"]

    r = await client.get(f"/api/v1/opportunities/{opp_id}", headers=_auth(rep_b))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_manager_can_see_any_opportunity(client: AsyncClient, db: AsyncSession):
    rep = await _create_user(db, "opp_rep_mgr@test.com", "sales_rep")
    mgr = await _create_user(db, "opp_mgr_see@test.com", "sales_manager")

    cr = await client.post("/api/v1/opportunities/", json={"title": "Rep Deal"}, headers=_auth(rep))
    opp_id = cr.json()["id"]

    r = await client.get(f"/api/v1/opportunities/{opp_id}", headers=_auth(mgr))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_rep_list_scoped_to_own(client: AsyncClient, db: AsyncSession):
    rep_a = await _create_user(db, "opp_scope_a@test.com", "sales_rep")
    rep_b = await _create_user(db, "opp_scope_b@test.com", "sales_rep")

    await client.post("/api/v1/opportunities/", json={"title": "A's Deal"}, headers=_auth(rep_a))
    await client.post("/api/v1/opportunities/", json={"title": "B's Deal"}, headers=_auth(rep_b))

    r = await client.get("/api/v1/opportunities/", headers=_auth(rep_a))
    items = r.json()["items"]
    assert all(i["owner_id"] == rep_a.id for i in items)


# ── Timeline ──

@pytest.mark.asyncio
async def test_timeline_has_creation_event(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "opp_timeline@test.com", "sales_manager")
    h = _auth(mgr)
    cr = await client.post("/api/v1/opportunities/", json={"title": "Timeline Deal"}, headers=h)
    opp_id = cr.json()["id"]

    r = await client.get(f"/api/v1/opportunities/{opp_id}/timeline", headers=h)
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) >= 1
    assert events[0]["event_type"] == "stage_change"


# ── Board ──

@pytest.mark.asyncio
async def test_kanban_returns_columns(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "opp_kanban@test.com", "sales_manager")
    h = _auth(mgr)

    r = await client.get("/api/v1/board/kanban", headers=h)
    assert r.status_code == 200
    columns = r.json()["columns"]
    assert len(columns) == 6  # 6 stages
    assert columns[0]["stage"] == "prospecting"


@pytest.mark.asyncio
async def test_board_summary(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "opp_summary@test.com", "sales_manager")
    h = _auth(mgr)

    r = await client.get("/api/v1/board/summary?window=30", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "open_pipeline_total" in d
    assert "win_rate" in d
    assert "rotting_count" in d
