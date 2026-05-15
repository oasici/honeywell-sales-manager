"""P0-3: Ownership / RBAC tests for quotes and emails."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.email_request import EmailRequest
from app.models.quote import Quote
from app.models.user import User


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _create_user(db: AsyncSession, email: str, role: str) -> User:
    user = User(
        tenant_id=_TENANT_ID,
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


# ── Quote Ownership ──


@pytest.mark.asyncio
async def test_sales_rep_cannot_access_other_reps_quote(client: AsyncClient, db: AsyncSession):
    rep_a = await _create_user(db, "rep_a@test.com", "sales_rep")
    rep_b = await _create_user(db, "rep_b@test.com", "sales_rep")

    quote = Quote(
        tenant_id=_TENANT_ID,
        quote_number="TEST-001",
        created_by=rep_a.id,
        status="draft",
        subtotal=0,
        discount_total=0,
        tax_rate=20,
        tax_amount=0,
        grand_total=0,
    )
    db.add(quote)
    await db.commit()
    await db.refresh(quote)

    # Rep B tries to access Rep A's quote -> 403
    response = await client.get(f"/api/v1/quotes/{quote.id}", headers=_auth(rep_b))
    assert response.status_code == 403

    # Rep A can access own quote -> 200
    response = await client.get(f"/api/v1/quotes/{quote.id}", headers=_auth(rep_a))
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_manager_can_access_any_quote(client: AsyncClient, db: AsyncSession):
    rep = await _create_user(db, "rep_mgr_test@test.com", "sales_rep")
    manager = await _create_user(db, "mgr_q_test@test.com", "sales_manager")

    quote = Quote(
        tenant_id=_TENANT_ID,
        quote_number="TEST-002",
        created_by=rep.id,
        status="draft",
        subtotal=0,
        discount_total=0,
        tax_rate=20,
        tax_amount=0,
        grand_total=0,
    )
    db.add(quote)
    await db.commit()
    await db.refresh(quote)

    # Manager can access any quote -> 200
    response = await client.get(f"/api/v1/quotes/{quote.id}", headers=_auth(manager))
    assert response.status_code == 200


# ── Email Ownership ──


@pytest.mark.asyncio
async def test_sales_rep_cannot_access_other_reps_email(client: AsyncClient, db: AsyncSession):
    rep_a = await _create_user(db, "rep_ea@test.com", "sales_rep")
    rep_b = await _create_user(db, "rep_eb@test.com", "sales_rep")

    email = EmailRequest(
        message_id="test-ownership-001",
        from_address="customer@example.com",
        subject="Test email",
        body_text="Test body",
        status="new",
        assigned_to=rep_a.id,
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)

    # Rep B tries to access Rep A's email -> 403
    response = await client.get(f"/api/v1/emails/{email.id}", headers=_auth(rep_b))
    assert response.status_code == 403

    # Rep A can access own email -> 200
    response = await client.get(f"/api/v1/emails/{email.id}", headers=_auth(rep_a))
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_manager_can_access_any_email(client: AsyncClient, db: AsyncSession):
    rep = await _create_user(db, "rep_em_test@test.com", "sales_rep")
    manager = await _create_user(db, "mgr_e_test@test.com", "sales_manager")

    email = EmailRequest(
        message_id="test-ownership-002",
        from_address="customer2@example.com",
        subject="Test email 2",
        body_text="Test body 2",
        status="new",
        assigned_to=rep.id,
    )
    db.add(email)
    await db.commit()
    await db.refresh(email)

    # Manager can access any email -> 200
    response = await client.get(f"/api/v1/emails/{email.id}", headers=_auth(manager))
    assert response.status_code == 200
