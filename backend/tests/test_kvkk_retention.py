"""KVKK retention auto-anonymization tests.

The retention service mutates real PII columns. The contract under test:

- Records older than the threshold are anonymized.
- Records newer than the threshold are untouched.
- Already-anonymized rows are skipped (idempotent).
- Customers with active opportunities are protected.
- ``dry_run=True`` reports counts without mutating anything.
- Each anonymization writes an audit row so the KVKK officer has a paper
  trail.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.kvkk_retention_service import (
    anonymize_dormant_customers,
    anonymize_old_email_requests,
    run_retention_anonymization,
)


def _utc(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def _date_ago(days_ago: int) -> date:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).date()


async def _make_email(db: AsyncSession, *, days_ago: int, message_id: str) -> EmailRequest:
    er = EmailRequest(
        message_id=message_id,
        from_address="customer@example.com",
        subject="Need part X",
        body_text="Original PII body",
        body_html="<p>Original PII body</p>",
        parsed_data=json.dumps({"customer_name": "Test User"}),
        received_at=_utc(days_ago),
    )
    db.add(er)
    await db.flush()
    return er


async def _make_user(db: AsyncSession, *, email: str = "owner@test.com") -> User:
    user = User(
        email=email,
        full_name="Owner",
        role="sales_rep",
        hashed_password="x",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _make_customer(db: AsyncSession, *, name: str = "Acme", email: str | None = None) -> Customer:
    suffix = email or f"{name.lower().replace(' ', '_')}@test.com"
    cust = Customer(name=name, email=suffix, kvkk_consent=True)
    db.add(cust)
    await db.flush()
    return cust


async def _make_opportunity(
    db: AsyncSession,
    *,
    owner_id: int,
    customer_id: int,
    status: str,
    close_date_days_ago: int | None,
) -> Opportunity:
    opp = Opportunity(
        title=f"Opp-{customer_id}-{status}",
        owner_id=owner_id,
        customer_id=customer_id,
        status=status,
        close_date=_date_ago(close_date_days_ago) if close_date_days_ago is not None else None,
    )
    db.add(opp)
    await db.flush()
    return opp


# ─── EmailRequest tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_email_older_than_threshold_is_anonymized(db: AsyncSession):
    er = await _make_email(db, days_ago=800, message_id="msg-old")

    count = await anonymize_old_email_requests(db, older_than_days=730)
    await db.commit()
    await db.refresh(er)

    assert count == 1
    assert er.body_text is None
    assert er.body_html is None
    assert er.subject is None
    assert er.parsed_data is None
    assert er.from_address == "anonymized@deleted.local"


@pytest.mark.asyncio
async def test_email_newer_than_threshold_is_untouched(db: AsyncSession):
    er = await _make_email(db, days_ago=400, message_id="msg-recent")

    count = await anonymize_old_email_requests(db, older_than_days=730)
    await db.commit()
    await db.refresh(er)

    assert count == 0
    assert er.body_text == "Original PII body"
    assert er.from_address == "customer@example.com"


@pytest.mark.asyncio
async def test_already_anonymized_email_is_skipped(db: AsyncSession):
    """Idempotency: a second sweep should be a no-op for already-cleared rows."""
    er = await _make_email(db, days_ago=800, message_id="msg-twice")

    first = await anonymize_old_email_requests(db, older_than_days=730)
    await db.commit()
    second = await anonymize_old_email_requests(db, older_than_days=730)
    await db.commit()

    assert first == 1
    assert second == 0


@pytest.mark.asyncio
async def test_email_dry_run_does_not_mutate(db: AsyncSession):
    er = await _make_email(db, days_ago=800, message_id="msg-dry")

    count = await anonymize_old_email_requests(db, older_than_days=730, dry_run=True)
    await db.commit()
    await db.refresh(er)

    assert count == 1
    assert er.body_text == "Original PII body"
    assert er.from_address == "customer@example.com"


@pytest.mark.asyncio
async def test_email_anonymization_writes_audit_row(db: AsyncSession):
    er = await _make_email(db, days_ago=800, message_id="msg-audit")

    await anonymize_old_email_requests(db, older_than_days=730)
    await db.commit()

    audit_rows = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "email_request",
                AuditLog.entity_id == er.id,
            )
        )
    ).scalars().all()

    assert len(audit_rows) == 1
    assert audit_rows[0].action == "kvkk_email_auto_anonymize"
    payload = json.loads(audit_rows[0].changes)
    assert payload["trigger"] == "retention_cron"
    assert payload["retention_days"] == 730


# ─── Customer tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_customer_with_old_closed_opp_is_anonymized(db: AsyncSession):
    user = await _make_user(db)
    cust = await _make_customer(db, name="Dormant Co")
    await _make_opportunity(
        db, owner_id=user.id, customer_id=cust.id, status="closed", close_date_days_ago=1200
    )

    count = await anonymize_dormant_customers(db, older_than_days=1095)
    await db.commit()
    await db.refresh(cust)

    assert count == 1
    assert cust.name == "ANONIMLESTIRILDI"
    assert cust.email == f"anon_{cust.id}@deleted.local"
    assert cust.phone is None
    assert cust.kvkk_consent is False
    assert cust.deletion_requested_at is not None


@pytest.mark.asyncio
async def test_customer_with_active_opp_is_protected(db: AsyncSession):
    """Even if a customer has an old closed opp, an active opp blocks anonymization."""
    user = await _make_user(db)
    cust = await _make_customer(db, name="Still Active")
    await _make_opportunity(
        db, owner_id=user.id, customer_id=cust.id, status="closed", close_date_days_ago=1200
    )
    await _make_opportunity(
        db, owner_id=user.id, customer_id=cust.id, status="active", close_date_days_ago=None
    )

    count = await anonymize_dormant_customers(db, older_than_days=1095)
    await db.commit()
    await db.refresh(cust)

    assert count == 0
    assert cust.name == "Still Active"


@pytest.mark.asyncio
async def test_customer_with_recent_close_is_protected(db: AsyncSession):
    """A customer whose latest close is within the window stays untouched."""
    user = await _make_user(db)
    cust = await _make_customer(db, name="Recently Closed")
    await _make_opportunity(
        db, owner_id=user.id, customer_id=cust.id, status="closed", close_date_days_ago=400
    )

    count = await anonymize_dormant_customers(db, older_than_days=1095)
    await db.commit()
    await db.refresh(cust)

    assert count == 0
    assert cust.name == "Recently Closed"


@pytest.mark.asyncio
async def test_already_anonymized_customer_is_skipped(db: AsyncSession):
    """deletion_requested_at sentinel keeps the sweep idempotent across runs."""
    user = await _make_user(db)
    cust = await _make_customer(db, name="Pre-anon")
    cust.deletion_requested_at = _utc(0)
    await _make_opportunity(
        db, owner_id=user.id, customer_id=cust.id, status="closed", close_date_days_ago=1500
    )

    count = await anonymize_dormant_customers(db, older_than_days=1095)
    await db.commit()
    await db.refresh(cust)

    assert count == 0
    # Name stays whatever it was; not re-stamped.
    assert cust.name == "Pre-anon"


@pytest.mark.asyncio
async def test_customer_with_no_opportunities_is_skipped(db: AsyncSession):
    """No-opp customers have no signal to make a retention call — leave them alone."""
    cust = await _make_customer(db, name="Lonely")

    count = await anonymize_dormant_customers(db, older_than_days=1095)
    await db.commit()
    await db.refresh(cust)

    assert count == 0
    assert cust.name == "Lonely"


@pytest.mark.asyncio
async def test_customer_dry_run_does_not_mutate(db: AsyncSession):
    user = await _make_user(db)
    cust = await _make_customer(db, name="DryCheck")
    await _make_opportunity(
        db, owner_id=user.id, customer_id=cust.id, status="closed", close_date_days_ago=1200
    )

    count = await anonymize_dormant_customers(db, older_than_days=1095, dry_run=True)
    await db.commit()
    await db.refresh(cust)

    assert count == 1
    assert cust.name == "DryCheck"
    assert cust.deletion_requested_at is None


# ─── Orchestrator ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_returns_combined_summary(db: AsyncSession):
    user = await _make_user(db)
    cust = await _make_customer(db, name="Orch Co")
    await _make_opportunity(
        db, owner_id=user.id, customer_id=cust.id, status="closed", close_date_days_ago=1500
    )
    await _make_email(db, days_ago=800, message_id="msg-orch")

    summary = await run_retention_anonymization(
        db,
        email_retention_days=730,
        opportunity_retention_days=1095,
        dry_run=False,
    )
    await db.commit()

    assert summary == {"email_count": 1, "customer_count": 1}


@pytest.mark.asyncio
async def test_invalid_retention_days_raises(db: AsyncSession):
    with pytest.raises(ValueError):
        await anonymize_old_email_requests(db, older_than_days=0)
    with pytest.raises(ValueError):
        await anonymize_dormant_customers(db, older_than_days=-1)
