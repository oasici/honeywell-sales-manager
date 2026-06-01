"""Round-19 Phase 12 — non-AWS roadmap continuation.

Covers:
  D-007  JWT rotate on login (session-fixation defense)
  D-028  Email pipeline retry on AI fail
  D-031  Opportunity bulk import (leads shipped in Phase 9)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


# ────────────────────────────────────────────────────────────────────
# D-007 — JWT rotate on login (session-fixation defense)
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_revokes_incoming_bearer_token(
    client: AsyncClient, admin_user, admin_token
) -> None:
    """A token presented in Authorization: Bearer at login time must be
    revoked before the new token is issued. Prevents session fixation:
    an attacker who planted a token via XSS cannot keep using it after
    the victim logs in normally.
    """
    from app.core.security import decode_token_async

    # Sanity: the planted token is valid before login.
    pre = await decode_token_async(admin_token)
    assert pre is not None
    assert pre.get("sub") == str(admin_user.id)

    # Log in WITH the planted token in the Authorization header.
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "admin@test.com", "password": "admin123"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    new_token = resp.json()["access_token"]
    assert new_token != admin_token

    # The planted (incoming) token is now revoked.
    post = await decode_token_async(admin_token)
    assert post is None, "Planted token should be revoked after login"

    # The newly issued token works.
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_login_revokes_incoming_cookie_token(
    client: AsyncClient, admin_user, admin_token
) -> None:
    """Same defense, but the planted token is in the access_token cookie
    rather than the Authorization header."""
    from app.core.security import decode_token_async

    pre = await decode_token_async(admin_token)
    assert pre is not None

    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "admin@test.com", "password": "admin123"},
        cookies={"access_token": admin_token},
    )
    assert resp.status_code == 200

    post = await decode_token_async(admin_token)
    assert post is None


@pytest.mark.asyncio
async def test_login_with_no_incoming_token_still_works(
    client: AsyncClient, admin_user
) -> None:
    """Baseline: a fresh login (no planted token) must not break."""
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "admin@test.com", "password": "admin123"},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_login_with_invalid_planted_token_still_succeeds(
    client: AsyncClient, admin_user
) -> None:
    """A junk token in the cookie / header must not block a valid login.
    Revocation is best-effort; bad incoming tokens are ignored.
    """
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "admin@test.com", "password": "admin123"},
        headers={"Authorization": "Bearer not-a-jwt"},
        cookies={"access_token": "also-not-a-jwt"},
    )
    assert resp.status_code == 200


# ────────────────────────────────────────────────────────────────────
# D-028 — Email pipeline retry on AI fail → DLQ
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_email_pipeline_writes_dlq_entry_on_processing_failure(
    db, admin_user, monkeypatch
) -> None:
    """When email processing raises an unrecoverable exception, the
    failure must land in background_job_dlq with job_name set, so
    Operations can triage from /admin/dlq instead of grepping
    `email.status=error` rows.
    """
    from datetime import datetime, timezone

    from app.models.email_request import EmailRequest
    from app.services.dlq_service import count_unresolved, list_unresolved
    from app.services.email_processing_service import EmailProcessingService

    email = EmailRequest(
        message_id="d028-test-001",
        from_address="customer@example.com",
        subject="Test pipeline failure",
        body_text="Need 5x ABC123",
        status="new",
        received_at=datetime.now(timezone.utc),
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)

    before = await count_unresolved(db)

    # Force the parser to raise. The service should swallow the
    # exception, mark the row in error state, AND write a DLQ entry.
    async def _boom(self, *_a, **_kw):
        raise RuntimeError("simulated unrecoverable parse failure")

    monkeypatch.setattr(
        EmailProcessingService,
        "_parse_email_with_fallback",
        _boom,
        raising=True,
    )

    service = EmailProcessingService(db)
    processed = await service.process_email(email.id)
    assert processed.status == "error"
    assert "simulated unrecoverable parse failure" in (processed.error_message or "")

    # DLQ has a new entry tagged with the right job_name and email id.
    after = await count_unresolved(db)
    assert after == before + 1
    entries = await list_unresolved(db, limit=50)
    matches = [
        e for e in entries
        if e.job_name == "email_parser_pipeline"
        and (e.payload or {}).get("email_id") == email.id
    ]
    assert matches, "Expected DLQ entry for email_parser_pipeline"
    assert "simulated unrecoverable parse failure" in matches[0].error


@pytest.mark.asyncio
async def test_email_pipeline_dlq_write_is_best_effort(
    db, admin_user, monkeypatch
) -> None:
    """A DLQ write failure must not mask the original error; the email
    row must still end in error state so the UI shows the right banner.
    """
    from datetime import datetime, timezone

    from app.models.email_request import EmailRequest
    from app.services.email_processing_service import EmailProcessingService

    email = EmailRequest(
        message_id="d028-test-002",
        from_address="customer@example.com",
        subject="DLQ write blip",
        body_text="something",
        status="new",
        received_at=datetime.now(timezone.utc),
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)

    async def _boom(self, *_a, **_kw):
        raise RuntimeError("original parse failure")

    monkeypatch.setattr(
        EmailProcessingService,
        "_parse_email_with_fallback",
        _boom,
        raising=True,
    )

    # Make the underlying DLQ writer raise too — the helper's own
    # try/except must keep the email failure path alive.
    async def _dlq_boom(*_a, **_kw):
        raise RuntimeError("dlq write also failed")

    import app.services.dlq_service as dlq_module
    monkeypatch.setattr(dlq_module, "write_to_dlq", _dlq_boom, raising=True)

    service = EmailProcessingService(db)
    try:
        processed = await service.process_email(email.id)
    except RuntimeError:
        pytest.fail("DLQ write failure must not propagate out of process_email")

    assert processed.status == "error"
    assert "original parse failure" in (processed.error_message or "")


# ────────────────────────────────────────────────────────────────────
# D-031 (opps half) — Opportunity bulk import
# ────────────────────────────────────────────────────────────────────


async def _seed_customer(db, *, tenant_id: int, name: str, tax_id: str) -> int:
    """Create a customer via the ORM so all NOT NULL defaults
    (preferred_lang, row_version, etc.) are populated regardless of
    schema churn. Returns the new customer id.
    """
    from app.models.customer import Customer

    cust = Customer(
        tenant_id=tenant_id,
        name=name,
        email=f"{name.lower().replace(' ', '')}@example.com",
        tax_id=tax_id,
    )
    db.add(cust)
    await db.flush()
    await db.refresh(cust)
    return cust.id


@pytest.mark.asyncio
async def test_opportunity_bulk_import_inserts_valid_rows(db, admin_user) -> None:
    """Valid CSV rows insert with stage/probability defaulting and
    customer lookup via vergi_no.
    """
    from sqlalchemy import text as _text

    from app.services.bulk_import import import_opportunities

    await _seed_customer(db, tenant_id=admin_user.tenant_id, name="Acme", tax_id="1234567890")
    await _seed_customer(db, tenant_id=admin_user.tenant_id, name="Beta", tax_id="2234567890")

    # Note: the TR-locale amount must be CSV-quoted so the comma
    # inside the number isn't treated as a field separator.
    csv_text = (
        "title,customer_vergi_no,amount,currency,stage,close_date,probability,source\n"
        "Big deal,1234567890,250000.50,TRY,qualified,2026-08-15,,inbound\n"
        'Smaller,2234567890,"12.500,50",TRY,proposal,15/08/2026,55,referral\n'
    )
    report = await import_opportunities(
        db, csv_text, tenant_id=admin_user.tenant_id, actor_id=admin_user.id
    )
    assert report.inserted == 2
    assert report.updated == 0
    assert report.skipped == 0
    assert report.errors == []

    # Row 1: blank probability → falls back to qualified=25.
    row1 = (await db.execute(_text(
        "SELECT stage, probability, amount FROM opportunities WHERE title = 'Big deal'"
    ))).first()
    assert row1.stage == "qualified"
    assert row1.probability == 25.0
    assert float(row1.amount) == 250000.50

    # Row 2: TR-locale "12.500,50" parsed as 12500.5.
    row2 = (await db.execute(_text(
        "SELECT amount, probability FROM opportunities WHERE title = 'Smaller'"
    ))).first()
    assert float(row2.amount) == 12500.50
    assert row2.probability == 55.0


@pytest.mark.asyncio
async def test_opportunity_bulk_import_savepoint_isolates_bad_rows(
    db, admin_user
) -> None:
    """A bad row (unknown customer, invalid stage) must report-and-skip
    without aborting the surrounding transaction. The valid sibling
    rows still land in the DB.
    """
    from sqlalchemy import text as _text

    from app.services.bulk_import import import_opportunities

    await _seed_customer(db, tenant_id=admin_user.tenant_id, name="Gamma", tax_id="3334567890")

    csv_text = (
        "title,customer_vergi_no,amount,stage\n"
        "Valid,3334567890,1000,qualified\n"
        "Unknown customer,9999999999,1000,qualified\n"
        "Invalid stage,3334567890,1000,not-a-stage\n"
        "Out-of-range prob,3334567890,1000,qualified\n"  # probability handled below
    )
    # Rewrite last row so it actually carries the bad probability.
    csv_text = csv_text.replace(
        "Out-of-range prob,3334567890,1000,qualified",
        "Out-of-range prob,3334567890,1000,qualified,150",
    )
    csv_text = csv_text.replace(
        "title,customer_vergi_no,amount,stage",
        "title,customer_vergi_no,amount,stage,probability",
    )

    report = await import_opportunities(
        db, csv_text, tenant_id=admin_user.tenant_id, actor_id=admin_user.id
    )

    assert report.inserted == 1
    assert report.skipped == 3
    # One unknown customer, one invalid stage, one out-of-range probability.
    assert len(report.errors) == 3
    messages = " | ".join(e.message for e in report.errors)
    assert "customer_not_found" in messages
    assert "invalid_stage" in messages
    assert "out_of_range" in messages

    # The Valid row landed.
    count = (await db.execute(_text(
        "SELECT COUNT(*) FROM opportunities WHERE title = 'Valid'"
    ))).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_opportunity_bulk_import_dedupes_on_reupload(db, admin_user) -> None:
    """Re-uploading the same CSV updates the existing row instead of
    creating a duplicate. Natural key: (tenant, title, customer_id).
    """
    from sqlalchemy import text as _text

    from app.services.bulk_import import import_opportunities

    await _seed_customer(db, tenant_id=admin_user.tenant_id, name="Delta", tax_id="4444567890")

    csv_v1 = (
        "title,customer_vergi_no,amount,stage\n"
        "Recurring deal,4444567890,1000,qualified\n"
    )
    r1 = await import_opportunities(
        db, csv_v1, tenant_id=admin_user.tenant_id, actor_id=admin_user.id
    )
    assert r1.inserted == 1 and r1.updated == 0

    # Reupload with a new amount + stage; same (title, customer).
    csv_v2 = (
        "title,customer_vergi_no,amount,stage\n"
        "Recurring deal,4444567890,5000,negotiation\n"
    )
    r2 = await import_opportunities(
        db, csv_v2, tenant_id=admin_user.tenant_id, actor_id=admin_user.id
    )
    assert r2.inserted == 0
    assert r2.updated == 1

    # Only one row exists.
    count = (await db.execute(_text(
        "SELECT COUNT(*) FROM opportunities WHERE title = 'Recurring deal'"
    ))).scalar()
    assert count == 1
    final = (await db.execute(_text(
        "SELECT amount, stage FROM opportunities WHERE title = 'Recurring deal'"
    ))).first()
    assert float(final.amount) == 5000.0
    assert final.stage == "negotiation"


@pytest.mark.asyncio
async def test_opportunity_bulk_import_missing_columns_returns_400ish(
    db, admin_user
) -> None:
    """Header without required columns reports an error and bails."""
    from app.services.bulk_import import import_opportunities

    csv_text = "title,amount\nNo customer column,1000\n"
    report = await import_opportunities(
        db, csv_text, tenant_id=admin_user.tenant_id, actor_id=admin_user.id
    )
    assert report.inserted == 0
    assert any(
        "csv_missing_required_columns" in e.message for e in report.errors
    )
