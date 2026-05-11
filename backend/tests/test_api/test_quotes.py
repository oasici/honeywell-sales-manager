import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.quote import Quote


@pytest.mark.asyncio
async def test_list_quotes_empty(client: AsyncClient, auth_headers):
    response = await client.get("/api/v1/quotes/", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_create_quote(client: AsyncClient, auth_headers, db: AsyncSession):
    # Create a customer first
    customer = Customer(name="Test Customer", email="customer@test.com")
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    response = await client.post(
        "/api/v1/quotes/",
        headers=auth_headers,
        json={
            "customer_id": customer.id,
            "language": "tr",
            "currency": "TRY",
            "tax_rate": 20,
            "items": [
                {
                    "honeywell_code": "ABC123",
                    "description": "Test Part",
                    "quantity": 5,
                    "unit_price": 100.0,
                    "discount_pct": 10,
                }
            ],
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["customer_id"] == customer.id
    assert data["status"] == "draft"
    assert data["currency"] == "TRY"
    assert len(data["items"]) == 1
    assert data["items"][0]["quantity"] == 5


@pytest.mark.asyncio
async def test_list_quotes_with_data(client: AsyncClient, auth_headers, db: AsyncSession):
    # Round-10 R10-DB-1..5 — the auth_headers fixture seeds the user
    # with tenant_id=1; scoped_for_user filters list_quotes by that
    # tenant, so the test Quote needs the same tenant_id to be visible.
    quote = Quote(
        tenant_id=1,
        quote_number="HW-TEST-001",
        status="draft",
        language="tr",
        currency="TRY",
    )
    db.add(quote)
    await db.commit()

    response = await client.get("/api/v1/quotes/", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_quotes_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/quotes/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_quotes_pagination(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/v1/quotes/?page=1&page_size=5", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "page" in data
    assert "page_size" in data
    assert "pages" in data
    assert "total" in data
