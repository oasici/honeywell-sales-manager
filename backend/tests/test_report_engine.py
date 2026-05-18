"""Tests for ReportEngine: query building, filters, column whitelist, CSV export."""
from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.security import hash_password
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.report import ReportTemplate
from app.models.user import User
from app.services.report_engine import ALLOWED_COLUMNS, ReportEngine


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _create_user(db: AsyncSession) -> User:
    user = User(
        tenant_id=_TENANT_ID,
        email="report_test@test.com",
        full_name="Report Tester",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seed_customers(db: AsyncSession, user_id: int) -> list[Customer]:
    customers = [
        Customer(tenant_id=_TENANT_ID, name="Ahmet Yilmaz", email="ahmet@sanayi.com", company="ABC Sanayi", created_by=user_id),
        Customer(tenant_id=_TENANT_ID, name="Mehmet Demir", email="mehmet@teknoloji.com", company="XYZ Teknoloji", created_by=user_id),
        Customer(tenant_id=_TENANT_ID, name="Ayse Kaya", email="ayse@insaat.com", company="Kaya Insaat", created_by=user_id),
    ]
    db.add_all(customers)
    await db.commit()
    for c in customers:
        await db.refresh(c)
    return customers


async def _seed_quotes(db: AsyncSession, user_id: int) -> list[Quote]:
    quotes = [
        Quote(
            tenant_id=_TENANT_ID,
            quote_number="RPT-001",
            created_by=user_id,
            status="draft",
            currency="TRY",
            subtotal=1000.0,
            discount_total=50.0,
            tax_amount=190.0,
            grand_total=1140.0,
            valid_days=30,
        ),
        Quote(
            tenant_id=_TENANT_ID,
            quote_number="RPT-002",
            created_by=user_id,
            status="approved",
            currency="USD",
            subtotal=5000.0,
            discount_total=200.0,
            tax_amount=960.0,
            grand_total=5760.0,
            valid_days=15,
        ),
    ]
    db.add_all(quotes)
    await db.commit()
    for q in quotes:
        await db.refresh(q)
    return quotes


async def _seed_opportunities(
    db: AsyncSession, user_id: int, customer_id: int
) -> list[Opportunity]:
    opps = [
        Opportunity(tenant_id=_TENANT_ID, title="Firsat A", stage="prospecting", owner_id=user_id, customer_id=customer_id, amount=10000.0),
        Opportunity(tenant_id=_TENANT_ID, title="Firsat B", stage="proposal", owner_id=user_id, customer_id=customer_id, amount=25000.0),
    ]
    db.add_all(opps)
    await db.commit()
    for o in opps:
        await db.refresh(o)
    return opps


async def _create_template(
    db: AsyncSession,
    user_id: int,
    entity_type: str = "customer",
    columns: list[str] | None = None,
    filters: list[dict] | None = None,
    group_by: str | None = None,
    sort_by: str | None = None,
) -> ReportTemplate:
    if columns is None:
        columns = ["id", "name", "company"]

    template = ReportTemplate(
        name="Test Rapor",
        entity_type=entity_type,
        columns_json=json.dumps(columns),
        filters_json=json.dumps(filters) if filters else None,
        group_by=group_by,
        sort_by=sort_by,
        created_by=user_id,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


# ── Query Building per Entity Type ──


@pytest.mark.asyncio
async def test_execute_inline_customer(db: AsyncSession):
    user = await _create_user(db)
    await _seed_customers(db, user.id)

    engine = ReportEngine(db)
    result = await engine.execute_inline(
        current_user=user,
        entity_type="customer",
        columns=["id", "name", "company"],
    )

    assert result["total"] == 3
    assert result["columns"] == ["id", "name", "company"]
    assert len(result["rows"]) == 3
    names = {row["name"] for row in result["rows"]}
    assert "Ahmet Yilmaz" in names


@pytest.mark.asyncio
async def test_execute_inline_quote(db: AsyncSession):
    user = await _create_user(db)
    await _seed_quotes(db, user.id)

    engine = ReportEngine(db)
    result = await engine.execute_inline(
        current_user=user,
        entity_type="quote",
        columns=["id", "quote_number", "status", "grand_total"],
    )

    assert result["total"] == 2
    numbers = {row["quote_number"] for row in result["rows"]}
    assert "RPT-001" in numbers
    assert "RPT-002" in numbers


@pytest.mark.asyncio
async def test_execute_inline_opportunity(db: AsyncSession):
    user = await _create_user(db)
    customers = await _seed_customers(db, user.id)
    await _seed_opportunities(db, user.id, customers[0].id)

    engine = ReportEngine(db)
    result = await engine.execute_inline(
        current_user=user,
        entity_type="opportunity",
        columns=["id", "title", "stage", "amount"],
    )

    assert result["total"] == 2


@pytest.mark.asyncio
async def test_execute_inline_email(db: AsyncSession):
    user = await _create_user(db)
    email = EmailRequest(
        # Round-15 Sprint 15k cohort 1 — tenant_id threaded so the
        # ReportEngine's scoped query (filters by user.tenant_id)
        # picks up the seed row.
        tenant_id=_TENANT_ID,
        message_id="rpt-test-001",
        from_address="test@example.com",
        subject="Test Konu",
        status="new",
        category="quote_request",
        sentiment="positive",
    )
    db.add(email)
    await db.commit()

    engine = ReportEngine(db)
    result = await engine.execute_inline(
        current_user=user,
        entity_type="email",
        columns=["id", "from_address", "subject", "status"],
    )

    assert result["total"] == 1
    assert result["rows"][0]["from_address"] == "test@example.com"


# ── Filter Operators ──


@pytest.mark.asyncio
async def test_filter_eq(db: AsyncSession):
    user = await _create_user(db)
    await _seed_quotes(db, user.id)

    engine = ReportEngine(db)
    result = await engine.execute_inline(
        current_user=user,
        entity_type="quote",
        columns=["id", "status"],
        filters=[{"field": "status", "operator": "eq", "value": "draft"}],
    )

    assert result["total"] == 1
    assert result["rows"][0]["status"] == "draft"


@pytest.mark.asyncio
async def test_filter_neq(db: AsyncSession):
    user = await _create_user(db)
    await _seed_quotes(db, user.id)

    engine = ReportEngine(db)
    result = await engine.execute_inline(
        current_user=user,
        entity_type="quote",
        columns=["id", "status"],
        filters=[{"field": "status", "operator": "neq", "value": "draft"}],
    )

    assert result["total"] == 1
    assert result["rows"][0]["status"] == "approved"


@pytest.mark.asyncio
async def test_filter_gt(db: AsyncSession):
    user = await _create_user(db)
    await _seed_quotes(db, user.id)

    engine = ReportEngine(db)
    result = await engine.execute_inline(
        current_user=user,
        entity_type="quote",
        columns=["id", "grand_total"],
        filters=[{"field": "grand_total", "operator": "gt", "value": 3000}],
    )

    assert result["total"] == 1
    assert result["rows"][0]["grand_total"] > 3000


@pytest.mark.asyncio
async def test_filter_contains(db: AsyncSession):
    user = await _create_user(db)
    await _seed_customers(db, user.id)

    engine = ReportEngine(db)
    result = await engine.execute_inline(
        current_user=user,
        entity_type="customer",
        columns=["id", "company"],
        filters=[{"field": "company", "operator": "contains", "value": "Sanayi"}],
    )

    assert result["total"] == 1
    assert "Sanayi" in result["rows"][0]["company"]


@pytest.mark.asyncio
async def test_filter_lte(db: AsyncSession):
    user = await _create_user(db)
    await _seed_quotes(db, user.id)

    engine = ReportEngine(db)
    result = await engine.execute_inline(
        current_user=user,
        entity_type="quote",
        columns=["id", "valid_days"],
        filters=[{"field": "valid_days", "operator": "lte", "value": 20}],
    )

    assert result["total"] == 1
    assert result["rows"][0]["valid_days"] <= 20


# ── Column Whitelist Security ──


@pytest.mark.asyncio
async def test_invalid_column_rejected(db: AsyncSession):
    user = await _create_user(db)
    engine = ReportEngine(db)

    with pytest.raises(BadRequestException):
        await engine.execute_inline(
            current_user=user,
            entity_type="customer",
            columns=["id", "hashed_password"],
        )


@pytest.mark.asyncio
async def test_invalid_column_in_filter_rejected(db: AsyncSession):
    user = await _create_user(db)
    engine = ReportEngine(db)

    with pytest.raises(BadRequestException):
        await engine.execute_inline(
            current_user=user,
            entity_type="customer",
            columns=["id", "name"],
            filters=[{"field": "hashed_password", "operator": "eq", "value": "secret"}],
        )


@pytest.mark.asyncio
async def test_invalid_entity_type_rejected(db: AsyncSession):
    user = await _create_user(db)
    engine = ReportEngine(db)

    with pytest.raises(BadRequestException):
        await engine.execute_inline(
            current_user=user,
            entity_type="user",
            columns=["id", "email"],
        )


@pytest.mark.asyncio
async def test_allowed_columns_do_not_contain_sensitive_fields():
    """Verify that no sensitive columns leak through the whitelist."""
    sensitive_fields = {"hashed_password", "password", "jwt_secret", "token", "secret"}

    for entity_type, columns in ALLOWED_COLUMNS.items():
        for col in columns:
            assert col not in sensitive_fields, (
                f"Sensitive field '{col}' found in ALLOWED_COLUMNS['{entity_type}']"
            )


# ── Group By ──


@pytest.mark.asyncio
async def test_group_by_returns_chart_data(db: AsyncSession):
    user = await _create_user(db)
    await _seed_quotes(db, user.id)

    engine = ReportEngine(db)
    result = await engine.execute_inline(
        current_user=user,
        entity_type="quote",
        columns=["id"],
        group_by="status",
    )

    assert result["chart_data"] is not None
    assert "labels" in result["chart_data"]
    assert "values" in result["chart_data"]
    assert result["total"] >= 1


# ── Sorting ──


@pytest.mark.asyncio
async def test_sort_by_column(db: AsyncSession):
    user = await _create_user(db)
    await _seed_quotes(db, user.id)

    engine = ReportEngine(db)
    result = await engine.execute_inline(
        current_user=user,
        entity_type="quote",
        columns=["id", "grand_total"],
        sort_by="grand_total",
        sort_order="asc",
    )

    totals = [row["grand_total"] for row in result["rows"]]
    assert totals == sorted(totals)


# ── Saved Template Execution ──


@pytest.mark.asyncio
async def test_execute_saved_template(db: AsyncSession):
    user = await _create_user(db)
    await _seed_customers(db, user.id)
    template = await _create_template(db, user.id)

    engine = ReportEngine(db)
    result = await engine.execute_report(template.id, current_user=user)

    assert result["total"] == 3
    assert result["columns"] == ["id", "name", "company"]


@pytest.mark.asyncio
async def test_execute_nonexistent_template(db: AsyncSession):
    user = await _create_user(db)
    engine = ReportEngine(db)

    with pytest.raises(NotFoundException):
        await engine.execute_report(99999, current_user=user)


# ── CSV Export ──


@pytest.mark.asyncio
async def test_csv_export(db: AsyncSession):
    user = await _create_user(db)
    await _seed_customers(db, user.id)
    template = await _create_template(db, user.id)

    engine = ReportEngine(db)
    csv_content = await engine.export_csv(template.id, current_user=user)

    lines = csv_content.strip().split("\n")
    assert len(lines) == 4  # header + 3 data rows

    header = lines[0]
    assert "id" in header
    assert "name" in header
    assert "company" in header


@pytest.mark.asyncio
async def test_csv_export_with_filters(db: AsyncSession):
    user = await _create_user(db)
    await _seed_customers(db, user.id)
    template = await _create_template(
        db,
        user.id,
        filters=[{"field": "company", "operator": "contains", "value": "Sanayi"}],
    )

    engine = ReportEngine(db)
    csv_content = await engine.export_csv(template.id, current_user=user)

    lines = csv_content.strip().split("\n")
    assert len(lines) == 2  # header + 1 matching row
    assert "Sanayi" in lines[1]


# ── Invalid Filter Operator ──


@pytest.mark.asyncio
async def test_invalid_filter_operator_rejected(db: AsyncSession):
    user = await _create_user(db)
    engine = ReportEngine(db)

    with pytest.raises(BadRequestException):
        await engine.execute_inline(
            current_user=user,
            entity_type="customer",
            columns=["id", "name"],
            filters=[{"field": "name", "operator": "regex", "value": ".*"}],
        )


# ── Missing Filter Fields ──


@pytest.mark.asyncio
async def test_filter_missing_field_rejected(db: AsyncSession):
    user = await _create_user(db)
    engine = ReportEngine(db)

    with pytest.raises(BadRequestException):
        await engine.execute_inline(
            current_user=user,
            entity_type="customer",
            columns=["id", "name"],
            filters=[{"operator": "eq", "value": "test"}],
        )
