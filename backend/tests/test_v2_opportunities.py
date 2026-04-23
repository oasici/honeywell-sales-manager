"""v2 Opportunity CRUD + Board + RBAC tests."""

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import patch
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.opportunity import Opportunity, Task
from app.models.quote import Quote
from app.models.user import User
from app.services.summary_service import SummaryService


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
async def test_list_and_detail_rotting_uses_activity_log(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "opp_rot_list@test.com", "sales_manager")
    h = _auth(mgr)
    cr = await client.post(
        "/api/v1/opportunities/",
        json={"title": "Rot List Deal", "stage": "qualified"},
        headers=h,
    )
    opp_id = cr.json()["id"]
    old = datetime.now(timezone.utc) - timedelta(days=15)
    # create path logs activity at "now"; force last activity backdated for rotting assertion
    await db.execute(
        update(ActivityLog)
        .where(ActivityLog.opportunity_id == opp_id)
        .values(created_at=old)
    )
    opp = (await db.execute(select(Opportunity).where(Opportunity.id == opp_id))).scalar_one()
    opp.updated_at = datetime.now(timezone.utc)
    await db.commit()

    dr = await client.get(f"/api/v1/opportunities/{opp_id}", headers=h)
    assert dr.status_code == 200
    assert dr.json()["rotting_days"] >= 14

    lr = await client.get("/api/v1/opportunities/", headers=h)
    assert lr.status_code == 200
    item = next(i for i in lr.json()["items"] if i["id"] == opp_id)
    assert item["rotting_days"] >= 14


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
async def test_kanban_filters_customer_tasks_rotting(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "opp_kanban_filters@test.com", "sales_manager")
    h = _auth(mgr)

    c_keep = Customer(name="KeepCo", email="keepco_kanban@test.com", company="KeepCo")
    c_drop = Customer(name="DropCo", email="dropco_kanban@test.com", company="DropCo")
    db.add_all([c_keep, c_drop])
    await db.commit()
    await db.refresh(c_keep)
    await db.refresh(c_drop)

    opp_match = Opportunity(
        title="Match",
        stage="qualified",
        status="active",
        owner_id=mgr.id,
        customer_id=c_keep.id,
        amount=1000,
        currency="TRY",
    )
    opp_noise_same_stage = Opportunity(
        title="Noise",
        stage="qualified",
        status="active",
        owner_id=mgr.id,
        customer_id=c_drop.id,
        amount=2000,
        currency="TRY",
    )
    db.add_all([opp_match, opp_noise_same_stage])
    await db.commit()
    await db.refresh(opp_match)
    await db.refresh(opp_noise_same_stage)

    db.add_all(
        [
            Task(title="t1", opportunity_id=opp_match.id, owner_id=mgr.id, status="open", priority="normal"),
            Task(title="t2", opportunity_id=opp_match.id, owner_id=mgr.id, status="open", priority="normal"),
        ]
    )
    old = datetime.now(timezone.utc) - timedelta(days=20)
    db.add(
        ActivityLog(
            activity_type="note_added",
            entity_type="opportunity",
            entity_id=opp_match.id,
            opportunity_id=opp_match.id,
            user_id=mgr.id,
            summary="stale",
            created_at=old,
        )
    )
    await db.commit()

    r = await client.get(
        "/api/v1/board/kanban",
        params={
            "customer_id": c_keep.id,
            "min_open_tasks": 2,
            "min_rotting_days": 10,
        },
        headers=h,
    )
    assert r.status_code == 200
    qualified = next(c for c in r.json()["columns"] if c["stage"] == "qualified")
    assert qualified["count"] == 1
    assert len(qualified["items"]) == 1
    assert qualified["items"][0]["id"] == opp_match.id


@pytest.mark.asyncio
async def test_board_summary(client: AsyncClient, db: AsyncSession):
    mgr = await _create_user(db, "opp_summary@test.com", "sales_manager")
    h = _auth(mgr)

    fresh_opp = Opportunity(title="Fresh pipe", stage="prospecting", status="active", owner_id=mgr.id)
    stale_opp = Opportunity(title="Stale pipe", stage="prospecting", status="active", owner_id=mgr.id)
    stale_no_log = Opportunity(
        title="No log stale", stage="qualified", status="active", owner_id=mgr.id
    )
    db.add_all([fresh_opp, stale_opp, stale_no_log])
    await db.commit()
    await db.refresh(fresh_opp)
    await db.refresh(stale_opp)
    await db.refresh(stale_no_log)

    old = datetime.now(timezone.utc) - timedelta(days=10)
    recent = datetime.now(timezone.utc) - timedelta(days=1)
    db.add_all(
        [
            ActivityLog(
                activity_type="note_added",
                entity_type="opportunity",
                entity_id=stale_opp.id,
                opportunity_id=stale_opp.id,
                user_id=mgr.id,
                summary="old",
                created_at=old,
            ),
            ActivityLog(
                activity_type="note_added",
                entity_type="opportunity",
                entity_id=fresh_opp.id,
                opportunity_id=fresh_opp.id,
                user_id=mgr.id,
                summary="new",
                created_at=recent,
            ),
        ]
    )
    stale_no_log.updated_at = old
    await db.commit()

    r = await client.get("/api/v1/board/summary?window=30", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "open_pipeline_total" in d
    assert "win_rate" in d
    assert "rotting_count" in d
    assert d["rotting_count"] == 2


@pytest.mark.asyncio
async def test_email_link_opportunity_timeline(client: AsyncClient, db: AsyncSession):
    """S2: PATCH /emails/{id}/opportunity + timeline shows linked inbound mail."""
    mgr = await _create_user(db, "email_opp_tl@test.com", "sales_manager")
    h = _auth(mgr)

    cust = Customer(
        name="EuroCust",
        company="EuroCo",
        email="eurocust_tl@test.com",
        created_by=mgr.id,
    )
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    cr = await client.post(
        "/api/v1/opportunities/",
        json={"title": "With email TL", "customer_id": cust.id, "stage": "prospecting"},
        headers=h,
    )
    assert cr.status_code == 201
    opp_id = cr.json()["id"]

    email = EmailRequest(
        message_id="unique-msg-timeline-1",
        from_address="buyer@example.com",
        subject="RFQ spare parts",
        customer_id=cust.id,
        assigned_to=mgr.id,
        status="new",
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)

    with patch("app.api.v1.emails.settings") as ms:
        ms.FEATURE_V2_BOARD = True
        lr = await client.patch(
            f"/api/v1/emails/{email.id}/opportunity",
            json={"opportunity_id": opp_id},
            headers=h,
        )
    assert lr.status_code == 200
    assert lr.json().get("opportunity_id") == opp_id

    tr = await client.get(f"/api/v1/opportunities/{opp_id}/timeline", headers=h)
    assert tr.status_code == 200
    evs = tr.json().get("events") or []
    assert any(
        e.get("entity_type") == "email_request"
        and e.get("entity_id") == email.id
        and e.get("synthetic") is True
        for e in evs
    )


@pytest.mark.asyncio
async def test_timeline_includes_email_only_via_quote(client: AsyncClient, db: AsyncSession):
    """Inbound mail linked only through Quote.email_request_id appears on opportunity timeline."""
    mgr = await _create_user(db, "opp_tl_quote@test.com", "sales_manager")
    h = _auth(mgr)

    cust = Customer(
        name="QuoteChainCo",
        company="QCC",
        email="qcc_tl@test.com",
        created_by=mgr.id,
    )
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    cr = await client.post(
        "/api/v1/opportunities/",
        json={"title": "Quote chain TL", "customer_id": cust.id, "stage": "prospecting"},
        headers=h,
    )
    assert cr.status_code == 201
    opp_id = cr.json()["id"]

    email = EmailRequest(
        message_id="unique-msg-quote-chain-1",
        from_address="vendor@example.com",
        subject="Teklif talebi",
        customer_id=cust.id,
        opportunity_id=None,
        assigned_to=mgr.id,
        status="new",
        body_text="RFQ detaylari burada",
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)

    quote = Quote(
        quote_number="Q-TL-QUOTE-001",
        opportunity_id=opp_id,
        email_request_id=email.id,
        customer_id=cust.id,
        grand_total=1000.0,
        status="draft",
    )
    db.add(quote)
    await db.commit()

    tr = await client.get(f"/api/v1/opportunities/{opp_id}/timeline", headers=h)
    assert tr.status_code == 200
    evs = tr.json().get("events") or []
    mail_events = [
        e
        for e in evs
        if e.get("entity_type") == "email_request" and e.get("entity_id") == email.id
    ]
    assert len(mail_events) >= 1
    e0 = mail_events[0]
    assert e0.get("synthetic") is True
    assert e0.get("via_quote") is True
    assert "teklif uzerinden" in (e0.get("description") or "").lower()


@pytest.mark.asyncio
async def test_opportunity_summary_context_includes_quote_linked_email(
    client: AsyncClient, db: AsyncSession,
):
    mgr = await _create_user(db, "opp_sum_quote@test.com", "sales_manager")

    cust = Customer(
        name="SumQuoteCo",
        company="SQC",
        email="sqc_sum@test.com",
        created_by=mgr.id,
    )
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    opp = Opportunity(
        title="Summary quote chain",
        stage="negotiation",
        status="active",
        owner_id=mgr.id,
        customer_id=cust.id,
        amount=5000,
        currency="TRY",
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)

    email = EmailRequest(
        message_id="unique-msg-sum-quote-1",
        from_address="buyer_sum@example.com",
        subject="Ozete dahil olsun",
        customer_id=cust.id,
        opportunity_id=None,
        assigned_to=mgr.id,
        status="new",
        body_text="UNIQUE_SNIPPET_XYZ_123",
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)

    quote = Quote(
        quote_number="Q-SUM-QUOTE-001",
        opportunity_id=opp.id,
        email_request_id=email.id,
        customer_id=cust.id,
        grand_total=2500.0,
        status="sent",
    )
    db.add(quote)
    await db.commit()

    sources: list[dict] = []
    svc = SummaryService(db)
    ctx = await svc._build_context("opportunity", opp.id, sources)

    assert "UNIQUE_SNIPPET_XYZ_123" in ctx
    assert "Bagli e-postalar" in ctx
    assert any(s.get("type") == "email" and s.get("id") == email.id for s in sources)
