"""Sprint 4 — high-intent list + pin/unpin."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.user import User
from tests.factories import DEFAULT_TENANT_ID, make_customer, make_opportunity


async def _user(db: AsyncSession, email: str, role: str) -> tuple[User, dict]:
    u = User(
        # Round-15 Sprint 15k/l unblocker.
        tenant_id=DEFAULT_TENANT_ID,
        email=email,
        full_name="HI Test",
        hashed_password=hash_password("Test1234"),
        role=role,
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    h = {"Authorization": f"Bearer {create_access_token({'sub': str(u.id)})}"}
    return u, h


@pytest.mark.asyncio
async def test_high_intent_list_and_pin_flow(client: AsyncClient, db: AsyncSession):
    mgr, h = await _user(db, "hi_pin_mgr@test.com", "sales_manager")
    cust = await make_customer(
        db,
        name="SignalCo",
        email="signalco_hi@test.com",
        company="SignalCo",
        created_by=mgr.id,
    )

    from datetime import datetime, timedelta, timezone

    from app.models.email_request import EmailRequest

    em = EmailRequest(
        message_id="hi-msg-1",
        from_address="buyer@x.com",
        subject="RFQ",
        customer_id=cust.id,
        status="new",
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(em)
    await make_opportunity(
        db,
        title="Open O",
        stage="qualified",
        status="active",
        owner_id=mgr.id,
        customer_id=cust.id,
        amount=50000.0,
        currency="EUR",
    )
    await db.commit()

    gr0 = await client.get(f"/api/v1/customers/{cust.id}", headers=h)
    assert gr0.status_code == 200
    assert gr0.json().get("pinned") is False

    lr = await client.get("/api/v1/customers/high-intent", headers=h)
    assert lr.status_code == 200
    items = lr.json().get("items") or []
    assert any(i["customer_id"] == cust.id for i in items)

    pr = await client.post(f"/api/v1/customers/{cust.id}/pin", headers=h)
    assert pr.status_code == 201

    gr1 = await client.get(f"/api/v1/customers/{cust.id}", headers=h)
    assert gr1.json().get("pinned") is True

    lr2 = await client.get("/api/v1/customers/high-intent", headers=h)
    row = next(i for i in lr2.json()["items"] if i["customer_id"] == cust.id)
    assert row["pinned"] is True

    ur = await client.delete(f"/api/v1/customers/{cust.id}/pin", headers=h)
    assert ur.status_code == 200

    lr3 = await client.get("/api/v1/customers/high-intent", headers=h)
    row3 = next(i for i in lr3.json()["items"] if i["customer_id"] == cust.id)
    assert row3["pinned"] is False
