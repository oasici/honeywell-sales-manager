"""KVKK Compliance endpoint tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.opportunity import Opportunity
from app.models.quote import Quote


@pytest_asyncio.fixture
async def sample_customer(db: AsyncSession) -> Customer:
    customer = Customer(
        name="Ahmet Yilmaz",
        email="ahmet@example.com",
        company="Yilmaz Ltd",
        phone="+905551234567",
        address="Istanbul, Turkiye",
        tax_id="1234567890",
        preferred_lang="tr",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


@pytest_asyncio.fixture
async def customer_with_relations(
    db: AsyncSession,
    sample_customer: Customer,
    admin_user,
) -> Customer:
    """Customer with quotes, emails, and opportunities."""
    quote = Quote(
        quote_number="Q-TEST-001",
        customer_id=sample_customer.id,
        status="draft",
        language="tr",
        currency="TRY",
        created_by=admin_user.id,
    )
    db.add(quote)

    email = EmailRequest(
        customer_id=sample_customer.id,
        message_id="test-msg-001@example.com",
        from_address="ahmet@example.com",
        subject="Teklif talebi",
        status="new",
    )
    db.add(email)

    opportunity = Opportunity(
        title="Test Firsat",
        stage="prospecting",
        customer_id=sample_customer.id,
        owner_id=admin_user.id,
        amount=10000.0,
        currency="TRY",
    )
    db.add(opportunity)

    await db.commit()
    return sample_customer


@pytest.mark.asyncio
async def test_record_consent(
    client: AsyncClient,
    auth_headers: dict,
    sample_customer: Customer,
):
    """Record consent: sets all fields correctly."""
    response = await client.post(
        f"/api/v1/compliance/consent/{sample_customer.id}",
        json={
            "consent": True,
            "method": "form",
            "purpose": "Satis ve pazarlama",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["has_consent"] is True
    assert data["method"] == "form"
    assert data["purpose"] == "Satis ve pazarlama"
    assert data["consent_date"] is not None
    assert data["retention_until"] is not None


@pytest.mark.asyncio
async def test_record_consent_invalid_method(
    client: AsyncClient,
    auth_headers: dict,
    sample_customer: Customer,
):
    """Record consent with invalid method returns 400."""
    response = await client.post(
        f"/api/v1/compliance/consent/{sample_customer.id}",
        json={
            "consent": True,
            "method": "invalid_method",
            "purpose": "Test",
        },
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_consent(
    client: AsyncClient,
    auth_headers: dict,
    sample_customer: Customer,
):
    """Get consent: returns current state."""
    # Initially no consent
    response = await client.get(
        f"/api/v1/compliance/consent/{sample_customer.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["has_consent"] is False
    assert data["consent_date"] is None

    # Record consent
    await client.post(
        f"/api/v1/compliance/consent/{sample_customer.id}",
        json={
            "consent": True,
            "method": "email",
            "purpose": "Veri isleme",
        },
        headers=auth_headers,
    )

    # Now should have consent
    response = await client.get(
        f"/api/v1/compliance/consent/{sample_customer.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["has_consent"] is True
    assert data["method"] == "email"


@pytest.mark.asyncio
async def test_data_export(
    client: AsyncClient,
    auth_headers: dict,
    customer_with_relations: Customer,
):
    """Data export: returns customer + related entities."""
    response = await client.post(
        f"/api/v1/compliance/data-export/{customer_with_relations.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()

    assert data["customer"]["id"] == customer_with_relations.id
    assert data["customer"]["name"] == "Ahmet Yilmaz"
    assert len(data["quotes"]) >= 1
    assert len(data["emails"]) >= 1
    assert len(data["opportunities"]) >= 1
    assert "activities" in data


@pytest.mark.asyncio
async def test_data_export_customer_not_found(
    client: AsyncClient,
    auth_headers: dict,
):
    """Data export for non-existent customer returns 404."""
    response = await client.post(
        "/api/v1/compliance/data-export/99999",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_anonymize_customer(
    client: AsyncClient,
    auth_headers: dict,
    sample_customer: Customer,
):
    """Data anonymize: PII fields cleared, deletion_requested_at set."""
    response = await client.post(
        f"/api/v1/compliance/data-delete/{sample_customer.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Musteri verileri anonimlestirildi"
    assert data["customer_id"] == sample_customer.id

    # Use a fresh session to avoid stale cache from fixture
    from tests.conftest import TestSession

    async with TestSession() as fresh_db:
        result = await fresh_db.execute(
            select(Customer).where(Customer.id == sample_customer.id)
        )
        customer = result.scalar_one_or_none()
        assert customer is not None
        assert customer.name == "ANONIMLESTIRILDI"
        assert customer.email == f"anon_{sample_customer.id}@deleted.local"
        assert customer.phone is None
        assert customer.address is None
        assert customer.tax_id is None
        assert customer.company is None
        assert customer.deletion_requested_at is not None
        assert customer.kvkk_consent is False


@pytest.mark.asyncio
async def test_anonymize_already_anonymized(
    client: AsyncClient,
    auth_headers: dict,
    sample_customer: Customer,
):
    """Anonymizing an already-anonymized customer returns 400."""
    await client.post(
        f"/api/v1/compliance/data-delete/{sample_customer.id}",
        headers=auth_headers,
    )
    response = await client.post(
        f"/api/v1/compliance/data-delete/{sample_customer.id}",
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_anonymized_customer_has_no_pii(
    client: AsyncClient,
    auth_headers: dict,
    sample_customer: Customer,
):
    """Anonymized customer has no real PII in any field."""
    await client.post(
        f"/api/v1/compliance/data-delete/{sample_customer.id}",
        headers=auth_headers,
    )

    from tests.conftest import TestSession

    async with TestSession() as fresh_db:
        result = await fresh_db.execute(
            select(Customer).where(Customer.id == sample_customer.id)
        )
        customer = result.scalar_one()

        pii_values = ["Ahmet", "Yilmaz", "ahmet@example.com", "+905551234567", "Istanbul", "1234567890"]
        for pii in pii_values:
            assert pii not in (customer.name or "")
            assert pii not in (customer.email or "")
            assert pii not in (customer.phone or "")
            assert pii not in (customer.address or "")
            assert pii not in (customer.tax_id or "")
            assert pii not in (customer.company or "")


@pytest.mark.asyncio
async def test_retention_report(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
):
    """Retention report: lists overdue customers."""
    # Use a fresh AsyncSession for the seed writes so the commit
    # doesn't collide with the connection state left by the
    # ``auth_headers`` fixture chain (which has already done its own
    # commit on the shared ``db`` session). Round-4 v1.9.14 — earlier
    # the FEATURE_BREACH_WORKFLOW gate masked this with a 404; once
    # the gate flipped to true the underlying async-session reuse
    # bug surfaced.
    from .conftest import TestSession  # type: ignore

    async with TestSession() as seed_session:
        seed_session.add(
            Customer(
                name="Expired User",
                email="expired@example.com",
                data_retention_until=datetime.now(timezone.utc) - timedelta(days=1),
            )
        )
        seed_session.add(
            Customer(
                name="Active User",
                email="active@example.com",
                data_retention_until=datetime.now(timezone.utc) + timedelta(days=365),
            )
        )
        await seed_session.commit()

    response = await client.get(
        "/api/v1/compliance/retention-report",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["overdue_count"] >= 1

    overdue_emails = [c["email"] for c in data["customers"]]
    assert "expired@example.com" in overdue_emails
    assert "active@example.com" not in overdue_emails


@pytest.mark.asyncio
async def test_audit_trail(
    client: AsyncClient,
    auth_headers: dict,
    sample_customer: Customer,
):
    """Audit trail: returns entries after consent recording."""
    # Record consent to generate audit entry
    await client.post(
        f"/api/v1/compliance/consent/{sample_customer.id}",
        json={
            "consent": True,
            "method": "verbal",
            "purpose": "Satis amacli",
        },
        headers=auth_headers,
    )

    response = await client.get(
        f"/api/v1/compliance/audit-trail/{sample_customer.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] == sample_customer.id
    assert len(data["audit_entries"]) >= 1
    assert data["audit_entries"][0]["action"] == "kvkk_consent"


@pytest.mark.asyncio
async def test_audit_trail_customer_not_found(
    client: AsyncClient,
    auth_headers: dict,
):
    """Audit trail for non-existent customer returns 404."""
    response = await client.get(
        "/api/v1/compliance/audit-trail/99999",
        headers=auth_headers,
    )
    assert response.status_code == 404
