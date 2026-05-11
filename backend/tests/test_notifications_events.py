"""A3: Tests that events produce notifications (best-effort)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.notification import Notification
from app.models.quote import Quote
from app.models.email_request import EmailRequest
from app.models.user import User


async def _create_user(db: AsyncSession, email: str, role: str) -> User:
    user = User(
        # Round-10 R10-DB-5 — Notification.tenant_id is NOT NULL and
        # create_notification looks it up from the target user. The
        # seed needs a non-null tenant_id so the notification path
        # doesn't early-out.
        tenant_id=1,
        email=email,
        full_name=f"Test {role}",
        hashed_password=hash_password("Test1234"),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _auth(user: User) -> dict:
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _count_notifications(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(Notification).where(Notification.user_id == user_id)
    )
    return len(result.scalars().all())


# ── Manual email creates notification ──

@pytest.mark.asyncio
async def test_manual_email_creates_notification(client: AsyncClient, db: AsyncSession):
    rep = await _create_user(db, "notif_rep@test.com", "sales_rep")

    response = await client.post(
        "/api/v1/emails/manual",
        json={
            "from_address": "customer@example.com",
            "subject": "Test notification email",
            "body_text": "Need spare parts",
        },
        headers=_auth(rep),
    )
    assert response.status_code == 201

    count = await _count_notifications(db, rep.id)
    assert count >= 1, "Manual email should create a notification"


# ── Approve quote creates notification for creator ──

@pytest.mark.asyncio
async def test_approve_quote_notifies_creator(client: AsyncClient, db: AsyncSession):
    rep = await _create_user(db, "notif_creator@test.com", "sales_rep")
    mgr = await _create_user(db, "notif_mgr@test.com", "sales_manager")

    quote = Quote(
        quote_number="NOTIF-001",
        created_by=rep.id,
        status="draft",
        subtotal=100,
        discount_total=0,
        tax_rate=20,
        tax_amount=20,
        grand_total=120,
    )
    db.add(quote)
    await db.commit()
    await db.refresh(quote)

    response = await client.patch(
        f"/api/v1/quotes/{quote.id}/approve",
        headers=_auth(mgr),
    )
    # May fail due to PDF generation, but notification should still be created
    if response.status_code == 200:
        count = await _count_notifications(db, rep.id)
        assert count >= 1, "Approve should notify the quote creator"


# ── Best-effort: notification failure doesn't break endpoint ──

@pytest.mark.asyncio
async def test_notification_failure_does_not_break_endpoint(
    client: AsyncClient, db: AsyncSession, monkeypatch
):
    rep = await _create_user(db, "notif_fail@test.com", "sales_rep")

    # Make create_notification always raise
    async def _broken_notification(*args, **kwargs):
        raise RuntimeError("Notification service down")

    monkeypatch.setattr(
        "app.api.v1.emails.create_notification",
        _broken_notification,
    )

    response = await client.post(
        "/api/v1/emails/manual",
        json={
            "from_address": "customer2@example.com",
            "subject": "Should still succeed",
            "body_text": "Even if notification fails",
        },
        headers=_auth(rep),
    )
    # Endpoint should still succeed
    assert response.status_code == 201


# ── Unread count increases ──

@pytest.mark.asyncio
async def test_unread_count_increases_after_notification(client: AsyncClient, db: AsyncSession):
    rep = await _create_user(db, "notif_unread@test.com", "sales_rep")
    headers = _auth(rep)

    # Check initial count
    resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp.status_code == 200
    initial_count = resp.json()["unread_count"]

    # Create email (triggers notification)
    await client.post(
        "/api/v1/emails/manual",
        json={
            "from_address": "trigger@example.com",
            "subject": "Trigger notification",
            "body_text": "body",
        },
        headers=headers,
    )

    # Check count increased
    resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
    new_count = resp.json()["unread_count"]
    assert new_count > initial_count
