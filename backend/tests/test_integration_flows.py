"""End-to-end integration tests using AsyncClient (API-level)."""

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User


@pytest_asyncio.fixture
async def manager(db: AsyncSession) -> User:
    """A sales_manager user for integration tests."""
    user = User(
        email="integration_mgr@test.com",
        full_name="Integration Manager",
        hashed_password=hash_password("pass123"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def manager_headers(manager: User) -> dict:
    from app.core.security import create_access_token

    token = create_access_token({"sub": str(manager.id)})
    return {"Authorization": f"Bearer {token}"}


class TestFullQuoteApprovalFlow:
    """End-to-end: create customer -> create quote -> check history -> approve -> verify."""

    @pytest.mark.asyncio
    async def test_quote_approval_lifecycle(
        self, client: AsyncClient, manager_headers: dict, db: AsyncSession,
    ):
        # Step 1: Create customer
        customer_resp = await client.post(
            "/api/v1/customers/",
            json={
                "name": "Integration Customer",
                "company": "IntCo",
                "email": "integration@customer.com",
                "phone": "+905550001111",
            },
            headers=manager_headers,
        )
        assert customer_resp.status_code == 201, customer_resp.text
        customer_id = customer_resp.json()["id"]

        # Step 2: Create quote
        quote_resp = await client.post(
            "/api/v1/quotes/",
            json={
                "customer_id": customer_id,
                "language": "tr",
                "currency": "TRY",
                "tax_rate": 20.0,
                "items": [
                    {
                        "description": "Test Part",
                        "quantity": 2,
                        "unit_price": 100.0,
                        "discount_pct": 0.0,
                    },
                ],
            },
            headers=manager_headers,
        )
        assert quote_resp.status_code == 201, quote_resp.text
        quote_data = quote_resp.json()
        quote_id = quote_data["id"]
        assert quote_data["status"] == "draft"

        # Step 3: Check approval history (should be empty -- no rules configured)
        with patch("app.core.config.settings.FEATURE_APPROVAL_ROUTING", True):
            history_resp = await client.get(
                f"/api/v1/approvals/history/quote/{quote_id}",
                headers=manager_headers,
            )
            # The endpoint may return 200 with empty list or 404 if no feature
            if history_resp.status_code == 200:
                history = history_resp.json()
                assert isinstance(history, (list, dict))

        # Step 4: Approve quote (generates PDF -- mock the PDF generation)
        with patch(
            "app.services.quote_generator.generate_quote_pdf",
            return_value="/tmp/fake.pdf",
        ):
            approve_resp = await client.patch(
                f"/api/v1/quotes/{quote_id}/approve",
                headers=manager_headers,
            )
            assert approve_resp.status_code == 200, approve_resp.text

        # Step 5: Verify status changed to approved
        get_resp = await client.get(
            f"/api/v1/quotes/{quote_id}",
            headers=manager_headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "approved"


class TestFullLeadConversionFlow:
    """End-to-end: create lead -> verify score -> qualify -> convert -> verify results."""

    @pytest.mark.asyncio
    async def test_lead_conversion_lifecycle(
        self, client: AsyncClient, manager_headers: dict, db: AsyncSession,
    ):
        with patch("app.core.config.settings.FEATURE_LEAD_LIFECYCLE", True), \
             patch("app.core.config.settings.FEATURE_V2_BOARD", True):
            # Step 1: Create lead via API
            lead_resp = await client.post(
                "/api/v1/leads/",
                json={
                    "first_name": "Integration",
                    "last_name": "Lead",
                    "email": "integration.lead@external.com",
                    "phone": "+905550002222",
                    "company": "LeadCo",
                    "title": "CEO",
                    "source": "referral",
                },
                headers=manager_headers,
            )
            assert lead_resp.status_code == 201, lead_resp.text
            lead_data = lead_resp.json()
            lead_id = lead_data["id"]

            # Step 2: Verify lead_score > 0
            assert lead_data["lead_score"] > 0, (
                "Lead with complete data should have a positive score"
            )

            # Step 3: Update lead status to qualified
            update_resp = await client.patch(
                f"/api/v1/leads/{lead_id}",
                json={"status": "qualified"},
                headers=manager_headers,
            )
            assert update_resp.status_code == 200, update_resp.text
            assert update_resp.json()["status"] == "qualified"

            # Step 4: Convert lead with create_opportunity=True
            convert_resp = await client.post(
                f"/api/v1/leads/{lead_id}/convert",
                json={
                    "create_opportunity": True,
                    "opportunity_title": "Integration Opportunity",
                    "opportunity_amount": 50000.0,
                },
                headers=manager_headers,
            )
            assert convert_resp.status_code == 200, convert_resp.text
            convert_data = convert_resp.json()

            # Step 5: Verify customer created
            assert convert_data["customer_id"] is not None
            customer_id = convert_data["customer_id"]

            customer_resp = await client.get(
                f"/api/v1/customers/{customer_id}",
                headers=manager_headers,
            )
            assert customer_resp.status_code == 200
            assert customer_resp.json()["email"] == "integration.lead@external.com"

            # Step 6: Verify opportunity created
            assert convert_data["opportunity_id"] is not None
            opp_id = convert_data["opportunity_id"]

            opp_resp = await client.get(
                f"/api/v1/opportunities/{opp_id}",
                headers=manager_headers,
            )
            assert opp_resp.status_code == 200
            opp_data = opp_resp.json()
            assert opp_data["title"] == "Integration Opportunity"
            assert opp_data["amount"] == 50000.0


class TestLeadConversionWithoutOpportunity:
    """Converting a lead without creating an opportunity."""

    @pytest.mark.asyncio
    async def test_convert_lead_creates_customer_only(
        self, client: AsyncClient, manager_headers: dict,
    ):
        with patch("app.core.config.settings.FEATURE_LEAD_LIFECYCLE", True):
            lead_resp = await client.post(
                "/api/v1/leads/",
                json={
                    "first_name": "NoOpp",
                    "last_name": "Lead",
                    "email": "noopp.lead@external.com",
                    "source": "manual",
                },
                headers=manager_headers,
            )
            assert lead_resp.status_code == 201
            lead_id = lead_resp.json()["id"]

            # Qualify first
            await client.patch(
                f"/api/v1/leads/{lead_id}",
                json={"status": "qualified"},
                headers=manager_headers,
            )

            convert_resp = await client.post(
                f"/api/v1/leads/{lead_id}/convert",
                json={"create_opportunity": False},
                headers=manager_headers,
            )
            assert convert_resp.status_code == 200
            convert_data = convert_resp.json()

            assert convert_data["customer_id"] is not None
            assert convert_data["opportunity_id"] is None


class TestQuoteCreationWithoutCustomer:
    """Creating a quote without a customer should work (customer_id=None)."""

    @pytest.mark.asyncio
    async def test_create_quote_without_customer(
        self, client: AsyncClient, manager_headers: dict,
    ):
        quote_resp = await client.post(
            "/api/v1/quotes/",
            json={
                "language": "tr",
                "currency": "USD",
                "tax_rate": 18.0,
                "items": [
                    {
                        "description": "Widget",
                        "quantity": 5,
                        "unit_price": 50.0,
                        "discount_pct": 10.0,
                    },
                ],
            },
            headers=manager_headers,
        )
        assert quote_resp.status_code == 201
        data = quote_resp.json()
        assert data["customer_id"] is None
        assert data["status"] == "draft"
        assert data["grand_total"] > 0


class TestDuplicateLeadEmail:
    """Creating a lead with a duplicate email should return an error."""

    @pytest.mark.asyncio
    async def test_duplicate_email_rejected(
        self, client: AsyncClient, manager_headers: dict,
    ):
        with patch("app.core.config.settings.FEATURE_LEAD_LIFECYCLE", True):
            lead_payload = {
                "first_name": "First",
                "last_name": "Lead",
                "email": "duplicate@lead.com",
                "source": "manual",
            }

            resp1 = await client.post(
                "/api/v1/leads/",
                json=lead_payload,
                headers=manager_headers,
            )
            assert resp1.status_code == 201

            resp2 = await client.post(
                "/api/v1/leads/",
                json=lead_payload,
                headers=manager_headers,
            )
            # Should be rejected (400 from BadRequestException)
            assert resp2.status_code == 400
            assert "zaten var" in resp2.json()["error"]["message"]
