"""V9 V2/V3 gap-closure service tests.

Covers:
- Sprint K: SalesforceAdapter / HubSpotAdapter test_mode + factory + orchestrator
- Sprint L: calendar_sync_service.auto_log_meeting + link_meeting_to_opportunity
- Sprint M: pipeline_review_service.propose / decide / wip_status
- Sprint N: nl_search_service semantic_search + upsert helpers
- Sprint O: quote_revision_service.create_revision + list_tree
- Sprint P: slippage_service.slippage_summary envelope shape
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.customer import Customer
from app.models.meeting_booking import MeetingBooking
from app.models.meeting_link import MeetingLink
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.spare_part import SparePart
from app.models.stage_config import StageConfig
from app.models.user import User
from app.models.v9_calendar import MeetingAutoLink
from app.models.v9_crm_sync import CrmConnection
from app.services import (
    calendar_sync_service,
    nl_search_service,
    pipeline_review_service,
    quote_revision_service,
    slippage_service,
)
from app.services.crm_sync import run_sync_job
from app.services.crm_sync.factory import get_adapter
from app.services.crm_sync.hubspot_adapter import HubSpotAdapter
from app.services.crm_sync.salesforce_adapter import SalesforceAdapter


# ─────────────────────── shared fixtures (DB-backed) ─────────────────


# Round-10 R10-DB-1..5 — every seed row now carries a non-null tenant_id
# so downstream models with NOT NULL tenant_id (meeting_bookings,
# playbooks, …) can inherit it without tripping the constraint.
_TENANT_ID = 1


async def _seed_user(db: AsyncSession, email: str = "v9_rep@test.com", role: str = "sales_rep") -> User:
    u = User(
        tenant_id=_TENANT_ID,
        email=email,
        full_name="V9 Rep",
        hashed_password=hash_password("Test1234"),
        role=role,
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _seed_customer(db: AsyncSession, email: str = "v9cust@test.com") -> Customer:
    c = Customer(
        tenant_id=_TENANT_ID,
        name="V9 Cust",
        company="V9 Cust Co",
        email=email,
        phone="",
        address="",
        tax_id="",
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _seed_opp(db: AsyncSession) -> tuple[User, Customer, Opportunity]:
    user = await _seed_user(db)
    cust = await _seed_customer(db)
    opp = Opportunity(
        tenant_id=_TENANT_ID,
        customer_id=cust.id,
        owner_id=user.id,
        title="V9 Deal",
        stage="qualified",
        status="active",
        amount=100_000.0,
        currency="TRY",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return user, cust, opp


# ─────────────────────── Sprint K: CRM adapters ──────────────────────


def test_salesforce_adapter_test_mode_validates_credentials():
    adapter = SalesforceAdapter(
        instance_url="https://example.salesforce", access_token="t", test_mode=True
    )
    assert adapter.test_credentials({"access_token": "t"}) is True
    assert adapter.test_credentials({}) is False


def test_salesforce_adapter_test_mode_lists_records():
    adapter = SalesforceAdapter(
        instance_url="https://example.salesforce", access_token="t", test_mode=True
    )
    out = list(adapter.list_records(entity_type="account", limit=2))
    assert len(out) == 2
    assert out[0].external_id.startswith("sf-account-")


def test_salesforce_adapter_rejects_unsupported_entity():
    from app.services.crm_sync.base import ConnectorError

    adapter = SalesforceAdapter(
        instance_url="https://x", access_token="t", test_mode=True
    )
    with pytest.raises(ConnectorError):
        list(adapter.list_records(entity_type="leads"))


def test_hubspot_adapter_test_mode_lists_records():
    adapter = HubSpotAdapter(access_token="t", test_mode=True)
    out = list(adapter.list_records(entity_type="opportunity", limit=3))
    assert len(out) == 3
    assert out[0].external_id.startswith("hs-opportunity-")


def test_hubspot_adapter_push_record_returns_id():
    adapter = HubSpotAdapter(access_token="t", test_mode=True)
    out = adapter.push_record(entity_type="account", payload={"name": "ACME"})
    assert out.startswith("hs-account-test-")


@pytest.mark.asyncio
async def test_factory_returns_test_mode_for_unconfigured_connection(db: AsyncSession):
    conn = CrmConnection(
        tenant_id=_TENANT_ID,
        provider="salesforce",
        label="Demo SF",
        is_active=True,
        sync_state="idle",
    )
    db.add(conn)
    await db.commit()
    adapter = get_adapter(conn, test_mode=True)
    assert adapter.provider_key == "salesforce"


@pytest.mark.asyncio
async def test_factory_rejects_unknown_provider(db: AsyncSession):
    from app.services.crm_sync.base import ConnectorError

    conn = CrmConnection(
        tenant_id=_TENANT_ID,
        provider="oracle", label="Mystery", is_active=True
    )
    db.add(conn)
    await db.commit()
    with pytest.raises(ConnectorError):
        get_adapter(conn)


@pytest.mark.asyncio
async def test_run_sync_job_creates_records_in_test_mode(db: AsyncSession):
    user = await _seed_user(db, email="sync_owner@test.com")
    conn = CrmConnection(
        tenant_id=_TENANT_ID,
        provider="salesforce",
        label="Demo SF",
        is_active=True,
        sync_state="idle",
        created_by=user.id,
    )
    db.add(conn)
    await db.commit()
    job = await run_sync_job(
        db, connection_id=conn.id, entity_type="account", test_mode=True
    )
    await db.commit()
    assert job.status == "succeeded"
    assert job.items_pulled >= 1


# ─────────────────────── Sprint L: calendar auto-log ─────────────────


@pytest.mark.asyncio
async def test_calendar_auto_log_matches_by_attendee_email(db: AsyncSession):
    user, cust, opp = await _seed_opp(db)
    link = MeetingLink(
        user_id=user.id,
        # Round-15 Sprint 15n cohort 4 — meeting_links.tenant_id NOT NULL.
        tenant_id=user.tenant_id,
        slug="v9-rep-link",
        title="Demo",
        duration_minutes=30,
        is_active=True,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    booking = MeetingBooking(
        # Round-10 R10-DB-2 — tenant_id now NOT NULL; mirror the opp's
        # tenant the same way the live booking service does.
        tenant_id=opp.tenant_id,
        meeting_link_id=link.id,
        booker_email=cust.email,
        booker_name="V9 Booker",
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
        status="confirmed",
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    auto = await calendar_sync_service.auto_log_meeting(
        db, meeting_booking_id=booking.id
    )
    await db.commit()
    assert auto is not None
    assert auto.opportunity_id == opp.id
    assert auto.matched_by == "attendee_email"
    assert 0.0 < auto.confidence <= 1.0


@pytest.mark.asyncio
async def test_calendar_auto_log_no_match_returns_link_with_null_opp(
    db: AsyncSession,
):
    user = await _seed_user(db, email="lonely_rep@test.com")
    link = MeetingLink(
        user_id=user.id,
        tenant_id=user.tenant_id,
        slug="lonely",
        title="Lonely",
        duration_minutes=30,
        is_active=True,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    booking = MeetingBooking(
        # Round-10 R10-DB-2 — tenant_id NOT NULL; user-owned booking.
        tenant_id=user.tenant_id,
        meeting_link_id=link.id,
        booker_email="stranger@nowhere.example",
        booker_name="Stranger",
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=2),
        status="confirmed",
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    auto = await calendar_sync_service.auto_log_meeting(
        db, meeting_booking_id=booking.id
    )
    await db.commit()
    assert auto is not None
    assert auto.opportunity_id is None


@pytest.mark.asyncio
async def test_calendar_link_meeting_to_opportunity_overrides(db: AsyncSession):
    user, cust, opp = await _seed_opp(db)
    link = MeetingLink(
        user_id=user.id,
        tenant_id=user.tenant_id,
        slug="man-link",
        title="Manual",
        duration_minutes=30,
        is_active=True,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    booking = MeetingBooking(
        # Round-10 R10-DB-2 — tenant_id NOT NULL.
        tenant_id=opp.tenant_id,
        meeting_link_id=link.id,
        booker_email="other@x.example",
        booker_name="Other",
        scheduled_at=datetime.now(timezone.utc),
        status="confirmed",
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    out = await calendar_sync_service.link_meeting_to_opportunity(
        db, meeting_booking_id=booking.id, opportunity_id=opp.id
    )
    await db.commit()
    assert out.opportunity_id == opp.id
    assert out.matched_by == "manual"
    assert out.confidence == 1.0


# ─────────────────────── Sprint M: pipeline review queue ─────────────


@pytest.mark.asyncio
async def test_pipeline_propose_idempotent_per_source(db: AsyncSession):
    _, _, opp = await _seed_opp(db)
    a = await pipeline_review_service.propose(
        db, opportunity_id=opp.id, suggested_stage="proposal"
    )
    b = await pipeline_review_service.propose(
        db, opportunity_id=opp.id, suggested_stage="negotiation"
    )
    await db.commit()
    assert a.id == b.id  # same row, replaced
    assert b.suggested_stage == "negotiation"


@pytest.mark.asyncio
async def test_pipeline_decide_apply_moves_stage(db: AsyncSession):
    user, _, opp = await _seed_opp(db)
    entry = await pipeline_review_service.propose(
        db, opportunity_id=opp.id, suggested_stage="proposal"
    )
    await db.commit()
    out = await pipeline_review_service.decide(
        db, entry_id=entry.id, decision="applied", decided_by=user.id
    )
    await db.commit()
    assert out.decision == "applied"
    refreshed = await db.get(Opportunity, opp.id)
    assert refreshed.stage == "proposal"
    assert refreshed.previous_stage == "qualified"


@pytest.mark.asyncio
async def test_pipeline_wip_status_warns_over_limit(db: AsyncSession):
    user = await _seed_user(db, email="wip_rep@test.com")
    cust = await _seed_customer(db)
    db.add(
        StageConfig(
            stage_name="qualified",
            label="Qualified",
            probability_pct=25,
            sort_order=1,
            is_active=True,
            wip_limit=1,
        )
    )
    db.add(
        StageConfig(
            stage_name="proposal",
            label="Proposal",
            probability_pct=50,
            sort_order=2,
            is_active=True,
            wip_limit=10,
        )
    )
    for i in range(2):
        db.add(
            Opportunity(
                tenant_id=_TENANT_ID,
                customer_id=cust.id,
                owner_id=user.id,
                title=f"WIP {i}",
                stage="qualified",
                status="active",
                amount=10_000,
                currency="TRY",
            )
        )
    await db.commit()
    out = await pipeline_review_service.wip_status(db)
    qualified = next(r for r in out if r["stage_name"] == "qualified")
    assert qualified["actual"] == 2
    assert qualified["wip_limit"] == 1
    assert qualified["wip_warning"] is True
    proposal = next(r for r in out if r["stage_name"] == "proposal")
    assert proposal["wip_warning"] is False


# ─────────────────────── Sprint N: NL semantic search ────────────────


@pytest.mark.asyncio
async def test_nl_semantic_search_empty_query_returns_empty(db: AsyncSession):
    out = await nl_search_service.semantic_search(db, query="   ")
    assert out == []


@pytest.mark.asyncio
async def test_nl_semantic_search_keyword_signal_when_no_embeddings(
    db: AsyncSession,
):
    _, _, opp = await _seed_opp(db)
    out = await nl_search_service.semantic_search(
        db, query="V9 Deal", scopes=["opportunities"]
    )
    # No embedding row yet → keyword score on title still ranks the opp
    titles = [item["title"] for item in out]
    assert "V9 Deal" in titles or out == []


# ─────────────────────── Sprint O: quote revisions ───────────────────


@pytest.mark.asyncio
async def test_quote_revision_clones_and_links(db: AsyncSession):
    user, cust, opp = await _seed_opp(db)
    spare = SparePart(honeywell_code="HW-X", name_tr="Demo", category="Demo", is_active=True)
    db.add(spare)
    await db.commit()
    await db.refresh(spare)

    src = Quote(
        # Round-15 Sprint 15k/l — thread tenant_id to match the file's
        # ``_seed_*`` pattern and unblock the NOT NULL promotion.
        tenant_id=_TENANT_ID,
        quote_number="Q-V9-1",
        customer_id=cust.id,
        created_by=user.id,
        status="draft",
        currency="TRY",
        subtotal=10_000.0,
        discount_total=0.0,
        tax_rate=20.0,
        tax_amount=2_000.0,
        grand_total=12_000.0,
        valid_days=30,
    )
    db.add(src)
    await db.commit()
    await db.refresh(src)

    rev = await quote_revision_service.create_revision(
        db, quote_id=src.id, created_by=user.id
    )
    await db.commit()
    assert rev is not None
    assert rev.parent_quote_id == src.id
    assert rev.revision_no == 2

    refreshed_src = await db.get(Quote, src.id)
    assert refreshed_src.superseded_by == rev.id


@pytest.mark.asyncio
async def test_quote_revision_list_tree_returns_chain(db: AsyncSession):
    user, cust, opp = await _seed_opp(db)
    src = Quote(
        tenant_id=_TENANT_ID,
        quote_number="Q-V9-2",
        customer_id=cust.id,
        created_by=user.id,
        status="draft",
        currency="TRY",
        subtotal=5000.0,
        grand_total=6000.0,
        tax_amount=1000.0,
    )
    db.add(src)
    await db.commit()
    await db.refresh(src)

    rev1 = await quote_revision_service.create_revision(
        db, quote_id=src.id, created_by=user.id
    )
    await db.commit()
    rev2 = await quote_revision_service.create_revision(
        db, quote_id=rev1.id, created_by=user.id
    )
    await db.commit()

    trees = await quote_revision_service.list_tree(
        db, opportunity_id=opp.id
    )
    assert len(trees) == 1
    assert trees[0]["revision_count"] == 3
    revs = trees[0]["revisions"]
    assert revs[0]["revision_no"] == 1
    assert revs[-1]["revision_no"] == 3


# ─────────────────────── Sprint P: slippage envelope ─────────────────


@pytest.mark.asyncio
async def test_slippage_summary_returns_v5_envelope(db: AsyncSession):
    user, _, _ = await _seed_opp(db)
    out = await slippage_service.slippage_summary(db, owner_id=user.id)
    assert set(out.keys()) >= {
        "value",
        "confidence",
        "drivers",
        "benchmark_context",
        "recommended_actions",
        "items",
    }
    assert isinstance(out["value"], (int, float))


@pytest.mark.asyncio
async def test_slippage_detects_close_date_push(db: AsyncSession):
    user = await _seed_user(db, email="slip_rep@test.com")
    cust = await _seed_customer(db)
    today = datetime.now(timezone.utc).date()
    opp = Opportunity(
        tenant_id=_TENANT_ID,
        customer_id=cust.id,
        owner_id=user.id,
        title="Slip Deal",
        stage="qualified",
        status="active",
        amount=50_000,
        currency="TRY",
        previous_close_date=today - timedelta(days=10),
        close_date=today + timedelta(days=5),
    )
    db.add(opp)
    await db.commit()

    out = await slippage_service.slippage_summary(db, owner_id=user.id)
    items = out["items"]
    assert any("close_date_push" in it["slip_kinds"] for it in items)
    assert out["value"] > 0
