"""Audit endpoint tests — list filters, CSV export, KVKK data export.

The list endpoint backs the admin audit UI. The CSV export feeds compliance
reports. The KVKK data-export endpoint is the right-of-access path under
KVKK Article 15: hand the data subject everything we hold about them.

Each path is sales_manager-gated; we lock that in alongside the data
contract so a future role-permission refactor can't quietly open it up.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.user import User


def _utc(days_ago: float = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


@pytest_asyncio.fixture
async def manager_headers(db: AsyncSession) -> dict:
    user = User(
        email="manager-audit@test.com",
        full_name="Audit Manager",
        hashed_password=hash_password("x"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def rep_headers(db: AsyncSession) -> dict:
    """A non-manager user — audit endpoints must reject this token."""
    user = User(
        email="rep-audit@test.com",
        full_name="Audit Rep",
        hashed_password=hash_password("x"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def seeded_audit_logs(db: AsyncSession) -> dict:
    """Three logs across two entity types, two actions, two users, two days.

    Seeds the referenced ``users`` rows first because audit_logs has a
    real FK on user_id — SQLite ignores it but PostgreSQL enforces it.

    Returns ``{"logs": [...], "user_a_id": int, "user_b_id": int}`` so
    callers can build URL params from the seeded IDs rather than
    hardcoding 1 and 2 (those collide with other autoincrement state
    when the test suite reorders).
    """
    user_a = User(
        email="audit-user-a@test.com",
        full_name="Audit User A",
        hashed_password=hash_password("x"),
        role="sales_rep",
        is_active=True,
    )
    user_b = User(
        email="audit-user-b@test.com",
        full_name="Audit User B",
        hashed_password=hash_password("x"),
        role="sales_rep",
        is_active=True,
    )
    db.add_all([user_a, user_b])
    await db.flush()

    logs = [
        AuditLog(
            user_id=user_a.id,
            action="customer_created",
            entity_type="customer",
            entity_id=10,
            changes='{"name": "A"}',
            created_at=_utc(days_ago=2),
        ),
        AuditLog(
            user_id=user_b.id,
            action="kvkk_data_delete",
            entity_type="customer",
            entity_id=11,
            changes='{"by": 2}',
            created_at=_utc(days_ago=1),
        ),
        AuditLog(
            user_id=user_b.id,
            action="kvkk_email_auto_anonymize",
            entity_type="email_request",
            entity_id=99,
            changes='{"trigger": "cron"}',
            created_at=_utc(days_ago=0),
        ),
    ]
    for log in logs:
        db.add(log)
    await db.commit()
    return {"logs": logs, "user_a_id": user_a.id, "user_b_id": user_b.id}


# ─── list endpoint ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_requires_manager_role(client: AsyncClient, rep_headers: dict):
    r = await client.get("/api/v1/audit/", headers=rep_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_returns_paginated_logs(
    client: AsyncClient, manager_headers: dict, seeded_audit_logs
):
    r = await client.get("/api/v1/audit/", headers=manager_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 3
    assert len(body["items"]) >= 3
    # Default ordering is newest first
    assert body["items"][0]["action"] == "kvkk_email_auto_anonymize"


@pytest.mark.asyncio
async def test_list_filter_by_user_id(
    client: AsyncClient, manager_headers: dict, seeded_audit_logs
):
    user_b_id = seeded_audit_logs["user_b_id"]
    r = await client.get(
        f"/api/v1/audit/?user_id={user_b_id}", headers=manager_headers
    )
    body = r.json()
    assert all(item["user_id"] == user_b_id for item in body["items"])
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_list_filter_by_entity_type(
    client: AsyncClient, manager_headers: dict, seeded_audit_logs
):
    r = await client.get(
        "/api/v1/audit/?entity_type=email_request", headers=manager_headers
    )
    body = r.json()
    assert all(item["entity_type"] == "email_request" for item in body["items"])
    assert body["total"] == 1


@pytest.mark.asyncio
async def test_list_filter_by_entity_id(
    client: AsyncClient, manager_headers: dict, seeded_audit_logs
):
    r = await client.get("/api/v1/audit/?entity_id=11", headers=manager_headers)
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["entity_id"] == 11


@pytest.mark.asyncio
async def test_list_filter_by_action_prefix(
    client: AsyncClient, manager_headers: dict, seeded_audit_logs
):
    """KVKK officer typically wants ALL kvkk_* actions, not just one."""
    r = await client.get(
        "/api/v1/audit/?action_prefix=kvkk_", headers=manager_headers
    )
    body = r.json()
    assert body["total"] == 2
    assert all(item["action"].startswith("kvkk_") for item in body["items"])


@pytest.mark.asyncio
async def test_list_action_and_action_prefix_are_mutually_exclusive(
    client: AsyncClient, manager_headers: dict
):
    r = await client.get(
        "/api/v1/audit/?action=foo&action_prefix=bar", headers=manager_headers
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_list_filter_by_since_window(
    client: AsyncClient, manager_headers: dict, seeded_audit_logs
):
    """since=12h ago → only the most-recent event passes the cutoff."""
    twelve_hours_ago = _utc(days_ago=0.5).isoformat()
    # Pass via params= so httpx URL-encodes the '+' in the ISO offset.
    r = await client.get(
        "/api/v1/audit/",
        params={"since": twelve_hours_ago},
        headers=manager_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["action"] == "kvkk_email_auto_anonymize"


# ─── CSV export ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_csv_export_requires_manager_role(
    client: AsyncClient, rep_headers: dict
):
    r = await client.get("/api/v1/audit/export/csv", headers=rep_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_csv_export_returns_filtered_rows(
    client: AsyncClient, manager_headers: dict, seeded_audit_logs
):
    r = await client.get(
        "/api/v1/audit/export/csv?action_prefix=kvkk_", headers=manager_headers
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]

    reader = csv.DictReader(io.StringIO(r.text))
    rows = list(reader)
    assert len(rows) == 2
    assert {row["action"] for row in rows} == {
        "kvkk_data_delete",
        "kvkk_email_auto_anonymize",
    }


# ─── KVKK data export ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_data_export_requires_manager_role(
    client: AsyncClient, rep_headers: dict
):
    r = await client.get("/api/v1/audit/data-export/1", headers=rep_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_data_export_returns_404_for_missing_user(
    client: AsyncClient, manager_headers: dict
):
    r = await client.get(
        "/api/v1/audit/data-export/999999", headers=manager_headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_data_export_bundles_user_owned_records(
    client: AsyncClient, manager_headers: dict, db: AsyncSession
):
    """The export must surface the user's audit events, owned opps, and
    customers they created. KVKK Article 15 demands completeness.

    Round-4 v1.9.14 — uses a fresh AsyncSession for the seed writes so
    the commits don't collide with the connection state left by the
    ``manager_headers`` fixture chain (asyncpg doesn't allow two
    in-flight ops on the same connection).
    """
    from .conftest import TestSession  # type: ignore

    async with TestSession() as seed:
        target = User(
            email="subject@test.com",
            full_name="Data Subject",
            hashed_password=hash_password("x"),
            role="sales_rep",
            is_active=True,
        )
        seed.add(target)
        await seed.commit()
        await seed.refresh(target)

        seed.add(
            AuditLog(
                user_id=target.id,
                action="login",
                entity_type="user",
                entity_id=target.id,
            )
        )
        seed.add(Customer(name="Made By Subject", email="madeby@test.com", created_by=target.id))
        seed.add(Opportunity(title="Subject's Opp", owner_id=target.id, status="active"))
        await seed.commit()

    r = await client.get(
        f"/api/v1/audit/data-export/{target.id}", headers=manager_headers
    )
    assert r.status_code == 200
    body = r.json()

    assert body["user"]["email"] == "subject@test.com"
    # Password hash MUST NOT leak
    assert "hashed_password" not in body["user"]

    assert body["counts"]["audit_events"] == 1
    assert body["counts"]["created_customers"] == 1
    assert body["counts"]["owned_opportunities"] == 1

    customer_emails = {c["email"] for c in body["created_customers"]}
    assert "madeby@test.com" in customer_emails


@pytest.mark.asyncio
async def test_data_export_writes_audit_row(
    client: AsyncClient, manager_headers: dict, db: AsyncSession
):
    """The disclosure itself is auditable — KVKK officer must be able to
    see who pulled what and when."""
    from .conftest import TestSession  # type: ignore

    async with TestSession() as seed:
        target = User(
            email="audited-export@test.com",
            full_name="Subject 2",
            hashed_password=hash_password("x"),
            role="sales_rep",
            is_active=True,
        )
        seed.add(target)
        await seed.commit()
        await seed.refresh(target)

    r = await client.get(
        f"/api/v1/audit/data-export/{target.id}", headers=manager_headers
    )
    assert r.status_code == 200

    # Check audit log was written. Use a fresh session so the read
    # doesn't reuse the loop-bound seed session above.
    from sqlalchemy import select

    async with TestSession() as readback:
        audit_rows = (
            await readback.execute(
                select(AuditLog).where(
                    AuditLog.action == "kvkk_data_export",
                    AuditLog.entity_id == target.id,
                )
            )
        ).scalars().all()
        assert len(audit_rows) == 1
        payload = json.loads(audit_rows[0].changes)
        assert "exported_at" in payload
        assert "counts" in payload
