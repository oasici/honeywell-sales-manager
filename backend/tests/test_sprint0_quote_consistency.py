import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.enums import EmailStatus
from app.models.user import User


async def _mgr(db: AsyncSession) -> tuple[User, dict]:
    user = User(
        email="s0_mgr@test.com",
        full_name="Sprint0 Manager",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token({'sub': str(user.id)})}"}


@pytest.mark.asyncio
async def test_quote_from_email_creates_and_links_opportunity(
    client: AsyncClient, db: AsyncSession
):
    user, h = await _mgr(db)

    customer = Customer(name="C1", email="c1@test.com", created_by=user.id)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    email = EmailRequest(
        customer_id=customer.id,
        message_id="m-s0-1",
        from_address=customer.email,
        subject="Teklif istiyorum",
        body_text="ABC123 x2",
        status=EmailStatus.PARSED.value,
        parsed_data=json.dumps(
            {"parts": [{"honeywell_code": "ABC123", "quantity": 2, "unit_price": 100.0, "discount_pct": 0}]}
        ),
        assigned_to=user.id,
        thread_id="th-s0-1",
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)

    r = await client.post(f"/api/v1/quotes/from-email/{email.id}", headers=h)
    assert r.status_code == 201
    payload = r.json()
    assert payload["email_request_id"] == email.id
    assert payload["opportunity_id"] is not None

    # Email should now be linked to the same opportunity for consistency
    await db.refresh(email)
    assert email.opportunity_id == payload["opportunity_id"]

