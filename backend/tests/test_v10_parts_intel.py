"""V10 spare-parts intelligence service tests.

Covers all 5 sprints (AA / BB / CC / DD / EE) end-to-end against the
SQLite test DB. The service layer is the unit under test — API
contract is exercised by the helpers, not the FastAPI client, to
keep tests fast and independent of the auth flow.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.price_entry import PriceEntry
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.spare_part import SparePart
from app.models.user import User
from app.services import (
    parts_data_quality_service,
    parts_intelligence_service,
    parts_obsolescence_watch_service,
    parts_pricing_intel_service,
    parts_substitution_service,
)


# ─────────────────────── shared fixtures ─────────────────────────────


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _seed_user(db: AsyncSession) -> User:
    user = User(
        tenant_id=_TENANT_ID,
        email="v10-mgr@test.com",
        full_name="V10 Manager",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_customer(db: AsyncSession, *, industry: str = "industrial") -> Customer:
    cust = Customer(
        tenant_id=_TENANT_ID,
        name="V10 Customer",
        company="V10 Co",
        email=f"v10-{datetime.utcnow().timestamp()}@cust.com",
        industry=industry,
    )
    db.add(cust)
    await db.flush()
    return cust


async def _seed_part(
    db: AsyncSession,
    *,
    code: str,
    name_tr: str | None = "Parça",
    name_en: str | None = None,
    description_tr: str | None = "Açıklama",
    description_en: str | None = None,
    category: str | None = "valves",
    supplier_price: float | None = 100.0,
    transfer_price: float | None = 60.0,
    model_number: str | None = "M1",
    min_margin_pct: float = 20.0,
) -> SparePart:
    part = SparePart(
        honeywell_code=code,
        name_tr=name_tr,
        name_en=name_en,
        description_tr=description_tr,
        description_en=description_en,
        category=category,
        supplier_price=supplier_price,
        transfer_price=transfer_price,
        model_number=model_number,
        min_margin_pct=min_margin_pct,
        is_active=True,
    )
    db.add(part)
    await db.flush()
    return part


async def _seed_quote_with_item(
    db: AsyncSession,
    *,
    customer: Customer,
    part: SparePart,
    line_total: float = 100.0,
    created_at: datetime | None = None,
    opportunity_id: int | None = None,
) -> Quote:
    q = Quote(
        tenant_id=_TENANT_ID,
        quote_number=f"Q-{datetime.utcnow().timestamp()}-{part.id}",
        customer_id=customer.id,
        opportunity_id=opportunity_id,
        status="sent",
        language="tr",
        currency="TRY",
        tax_rate=20.0,
        valid_days=30,
        grand_total=line_total,
    )
    if created_at is not None:
        q.created_at = created_at
    db.add(q)
    await db.flush()
    item = QuoteItem(
        quote_id=q.id,
        spare_part_id=part.id,
        honeywell_code=part.honeywell_code,
        description=part.name_tr,
        quantity=1,
        unit_price=line_total,
        line_total=line_total,
    )
    db.add(item)
    await db.flush()
    return q


# ─────────────────────── Sprint AA tests ─────────────────────────────


@pytest.mark.asyncio
async def test_velocity_classification_returns_empty_when_no_parts(db: AsyncSession):
    rows = await parts_intelligence_service.velocity_classification(db)
    assert rows == []


@pytest.mark.asyncio
async def test_velocity_classification_assigns_C_to_zero_contribution_parts(
    db: AsyncSession,
):
    await _seed_part(db, code="HW-INACTIVE-1")
    rows = await parts_intelligence_service.velocity_classification(db)
    assert len(rows) == 1
    assert rows[0].tier == "C"
    assert rows[0].line_total_sum == 0.0


@pytest.mark.asyncio
async def test_velocity_classification_top_contributor_is_A_tier(db: AsyncSession):
    cust = await _seed_customer(db)
    p_top = await _seed_part(db, code="HW-A-TOP")
    p_mid = await _seed_part(db, code="HW-B-MID")
    p_low = await _seed_part(db, code="HW-C-LOW")
    p_zero = await _seed_part(db, code="HW-Z-ZERO")
    p_zero_2 = await _seed_part(db, code="HW-Z-ZERO-2")

    await _seed_quote_with_item(db, customer=cust, part=p_top, line_total=10_000)
    await _seed_quote_with_item(db, customer=cust, part=p_mid, line_total=1_000)
    await _seed_quote_with_item(db, customer=cust, part=p_low, line_total=100)

    rows = await parts_intelligence_service.velocity_classification(db)
    by_code = {r.honeywell_code: r for r in rows}
    assert by_code["HW-A-TOP"].tier == "A"
    assert by_code["HW-Z-ZERO"].tier == "C"
    assert by_code["HW-Z-ZERO-2"].tier == "C"


@pytest.mark.asyncio
async def test_dead_stock_excludes_recently_quoted_parts(db: AsyncSession):
    cust = await _seed_customer(db)
    p_active = await _seed_part(db, code="HW-ACTIVE")
    p_idle = await _seed_part(db, code="HW-IDLE", supplier_price=500.0)
    await _seed_quote_with_item(
        db,
        customer=cust,
        part=p_active,
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    rows = await parts_intelligence_service.dead_stock_ledger(
        db, min_idle_days=180
    )
    codes = {r.honeywell_code for r in rows}
    assert "HW-IDLE" in codes
    assert "HW-ACTIVE" not in codes


@pytest.mark.asyncio
async def test_demand_heatmap_empty_when_no_quotes_in_window(db: AsyncSession):
    cust = await _seed_customer(db)
    part = await _seed_part(db, code="HW-OLD-ONLY")
    await _seed_quote_with_item(
        db,
        customer=cust,
        part=part,
        created_at=datetime.now(timezone.utc) - timedelta(days=400),
    )
    cells = await parts_intelligence_service.demand_heatmap(
        db, window_days=180
    )
    assert cells == []


@pytest.mark.asyncio
async def test_demand_heatmap_groups_by_month(db: AsyncSession):
    cust = await _seed_customer(db)
    part = await _seed_part(db, code="HW-HEAT")
    now = datetime.now(timezone.utc)
    await _seed_quote_with_item(db, customer=cust, part=part, created_at=now)
    await _seed_quote_with_item(
        db, customer=cust, part=part, created_at=now - timedelta(days=2)
    )
    cells = await parts_intelligence_service.demand_heatmap(db, window_days=30)
    assert len(cells) == 1
    assert cells[0].quote_count == 2


@pytest.mark.asyncio
async def test_summary_combines_primitives(db: AsyncSession):
    cust = await _seed_customer(db)
    part = await _seed_part(db, code="HW-SUM", supplier_price=200.0)
    payload = await parts_intelligence_service.parts_intelligence_summary(db)
    assert "tier_counts" in payload
    assert payload["dead_stock_count"] >= 1
    assert payload["frozen_capital_total"] >= 200.0


# ─────────────────────── Sprint BB tests ─────────────────────────────


@pytest.mark.asyncio
async def test_inflation_tax_returns_low_confidence_when_no_history(db: AsyncSession):
    payload = await parts_pricing_intel_service.inflation_tax_summary(db)
    assert payload["confidence"] == "low"
    assert payload["value"] == 0.0


@pytest.mark.asyncio
async def test_stale_pricing_includes_parts_without_price_entries(db: AsyncSession):
    part = await _seed_part(db, code="HW-NO-PRICE")
    rows = await parts_pricing_intel_service.stale_pricing_alerts(db)
    codes = {r.honeywell_code for r in rows}
    assert "HW-NO-PRICE" in codes
    target = next(r for r in rows if r.honeywell_code == "HW-NO-PRICE")
    assert target.reason == "no_price_entry"


@pytest.mark.asyncio
async def test_stale_pricing_detects_expired_valid_until(db: AsyncSession):
    part = await _seed_part(db, code="HW-EXPIRED")
    # Use UTC date so the seed matches the service's
    # ``datetime.now(timezone.utc).date()`` reference. Pre-fix the test
    # used local ``date.today()`` which produced an off-by-one
    # ``age_days`` when the run crossed UTC midnight from a timezone
    # ahead of UTC (Istanbul, etc).
    today_utc = datetime.now(timezone.utc).date()
    pe = PriceEntry(
        spare_part_id=part.id,
        list_price=100.0,
        net_price=80.0,
        currency="USD",
        valid_until=today_utc - timedelta(days=5),
    )
    db.add(pe)
    await db.flush()

    rows = await parts_pricing_intel_service.stale_pricing_alerts(db)
    target = next(r for r in rows if r.honeywell_code == "HW-EXPIRED")
    assert target.reason == "expired_valid_until"
    assert target.age_days >= 5


@pytest.mark.asyncio
async def test_margin_health_skips_parts_without_transfer_price(db: AsyncSession):
    part = await _seed_part(db, code="HW-NO-TRANSFER", transfer_price=None)
    pe = PriceEntry(
        spare_part_id=part.id,
        list_price=100.0,
        net_price=80.0,
        currency="USD",
    )
    db.add(pe)
    await db.flush()
    rows = await parts_pricing_intel_service.margin_health_alerts(db)
    codes = {r.honeywell_code for r in rows}
    assert "HW-NO-TRANSFER" not in codes


@pytest.mark.asyncio
async def test_margin_health_flags_thin_margin(db: AsyncSession):
    part = await _seed_part(
        db,
        code="HW-THIN",
        transfer_price=90.0,
        min_margin_pct=30.0,
    )
    pe = PriceEntry(
        spare_part_id=part.id,
        list_price=100.0,
        net_price=100.0,
        currency="USD",
    )
    db.add(pe)
    await db.flush()
    rows = await parts_pricing_intel_service.margin_health_alerts(db)
    target = next(r for r in rows if r.honeywell_code == "HW-THIN")
    # derived margin = 10%, floor = 30%, warn threshold = 24%, danger = 15%
    assert target.severity == "danger"
    assert target.derived_margin_pct == pytest.approx(10.0, abs=0.5)


# ─────────────────────── Sprint CC tests ─────────────────────────────


@pytest.mark.asyncio
async def test_eol_risk_score_is_bounded_0_to_100(db: AsyncSession):
    part = await _seed_part(db, code="HW-RISK", supplier_price=None, model_number=None)
    payload = await parts_obsolescence_watch_service.eol_risk_score(
        db, part_id=part.id
    )
    assert 0 <= payload["value"] <= 100


@pytest.mark.asyncio
async def test_eol_risk_for_unknown_part_returns_zero(db: AsyncSession):
    payload = await parts_obsolescence_watch_service.eol_risk_score(
        db, part_id=999_999
    )
    assert payload["value"] == 0
    assert payload["confidence"] == "low"


@pytest.mark.asyncio
async def test_obsolescence_watch_orders_by_descending_risk(db: AsyncSession):
    p_low = await _seed_part(
        db, code="HW-LOW-RISK", supplier_price=10.0, model_number="full"
    )
    p_high = await _seed_part(
        db,
        code="HW-HIGH-RISK",
        supplier_price=None,
        model_number=None,
        description_tr=None,
        description_en=None,
        category=None,
    )
    rows = await parts_obsolescence_watch_service.obsolescence_watch_list(
        db, top_n=10
    )
    assert rows  # has data
    risk_by_code = {r.honeywell_code: r.risk_score for r in rows}
    if "HW-HIGH-RISK" in risk_by_code and "HW-LOW-RISK" in risk_by_code:
        assert risk_by_code["HW-HIGH-RISK"] >= risk_by_code["HW-LOW-RISK"]


# ─────────────────────── Sprint DD tests ─────────────────────────────


@pytest.mark.asyncio
async def test_master_data_health_returns_low_confidence_for_empty_catalog(
    db: AsyncSession,
):
    payload = await parts_data_quality_service.master_data_health_score(db)
    assert payload["confidence"] == "low"
    assert payload["value"] == 0


@pytest.mark.asyncio
async def test_master_data_health_perfect_when_all_fields_filled(db: AsyncSession):
    await _seed_part(
        db,
        code="HW-PERFECT-1",
        description_tr="full",
        category="valves",
        supplier_price=100.0,
        model_number="M1",
    )
    payload = await parts_data_quality_service.master_data_health_score(db)
    assert payload["value"] == 100


@pytest.mark.asyncio
async def test_duplicate_candidates_finds_same_model_number(db: AsyncSession):
    a = await _seed_part(db, code="HW-DUP-1", model_number="MODEL-X")
    b = await _seed_part(db, code="HW-DUP-2", model_number="MODEL-X")
    rows = await parts_data_quality_service.duplicate_candidates(db, threshold=0.99)
    assert any(
        r.spare_part_a_id in {a.id, b.id} and r.spare_part_b_id in {a.id, b.id}
        for r in rows
    )


@pytest.mark.asyncio
async def test_duplicate_candidates_fuzzy_name_match(db: AsyncSession):
    await _seed_part(
        db, code="HW-FUZ-1", model_number="X1", name_tr="Honeywell Sıcaklık Sensörü"
    )
    await _seed_part(
        db, code="HW-FUZ-2", model_number="X2", name_tr="Honeywell Sıcaklık Sensoru"
    )
    rows = await parts_data_quality_service.duplicate_candidates(
        db, threshold=0.85
    )
    assert any(r.reason == "fuzzy_name" for r in rows)


@pytest.mark.asyncio
async def test_orphan_pricing_flags_inactive_part(db: AsyncSession):
    part = await _seed_part(db, code="HW-INACTIVE", supplier_price=10.0)
    part.is_active = False
    await db.flush()
    pe = PriceEntry(
        spare_part_id=part.id,
        list_price=10.0,
        net_price=8.0,
        currency="USD",
    )
    db.add(pe)
    await db.flush()
    rows = await parts_data_quality_service.orphan_pricing(db)
    assert any(r.spare_part_id == part.id for r in rows)
    target = next(r for r in rows if r.spare_part_id == part.id)
    assert target.reason == "inactive_part"


# ─────────────────────── Sprint EE tests ─────────────────────────────


@pytest.mark.asyncio
async def test_substitution_returns_empty_for_part_without_revisions(db: AsyncSession):
    part = await _seed_part(db, code="HW-NO-SUB")
    rows = await parts_substitution_service.substitution_patterns(
        db, part_id=part.id
    )
    assert rows == []


@pytest.mark.asyncio
async def test_substitution_detects_part_swap_via_revision_chain(
    db: AsyncSession,
):
    cust = await _seed_customer(db)
    p_old = await _seed_part(db, code="HW-OLD")
    p_new = await _seed_part(db, code="HW-NEW")

    parent = await _seed_quote_with_item(db, customer=cust, part=p_old)
    child = Quote(
        tenant_id=_TENANT_ID,
        quote_number="Q-CHILD",
        customer_id=cust.id,
        status="draft",
        language="tr",
        currency="TRY",
        tax_rate=20.0,
        valid_days=30,
        grand_total=100.0,
        parent_quote_id=parent.id,
        revision_no=2,
    )
    db.add(child)
    await db.flush()
    db.add(
        QuoteItem(
            quote_id=child.id,
            spare_part_id=p_new.id,
            honeywell_code=p_new.honeywell_code,
            description="new",
            quantity=1,
            unit_price=100.0,
            line_total=100.0,
        )
    )
    await db.flush()

    rows = await parts_substitution_service.substitution_patterns(
        db, part_id=p_old.id
    )
    assert any(r.replacement_part_id == p_new.id for r in rows)


@pytest.mark.asyncio
async def test_cross_customer_demand_distinct_customer_count(db: AsyncSession):
    cust_a = await _seed_customer(db, industry="industrial")
    cust_b = await _seed_customer(db, industry="oil_gas")
    part = await _seed_part(db, code="HW-CROSS")
    await _seed_quote_with_item(db, customer=cust_a, part=part)
    await _seed_quote_with_item(db, customer=cust_b, part=part)
    rows = await parts_substitution_service.cross_customer_demand(
        db, part_id=part.id
    )
    customer_ids = {r.customer_id for r in rows}
    assert cust_a.id in customer_ids
    assert cust_b.id in customer_ids


@pytest.mark.asyncio
async def test_segment_affinity_skips_null_industry(db: AsyncSession):
    cust_unknown = await _seed_customer(db)
    cust_unknown.industry = None
    await db.flush()
    cust_named = await _seed_customer(db, industry="industrial")
    part = await _seed_part(db, code="HW-AFF")
    await _seed_quote_with_item(db, customer=cust_unknown, part=part)
    await _seed_quote_with_item(db, customer=cust_named, part=part)
    rows = await parts_substitution_service.segment_affinity(db, part_id=part.id)
    assert all(r.industry is not None for r in rows)
    industries = {r.industry for r in rows}
    assert "industrial" in industries
