"""Round-16 N15-API-3 (C6) — GET /quotes/{id} picker integration.

Fourth per-entity rollout after C3-C5. Same three-assertion structure.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.customer import Customer
from app.models.quote import Quote
from app.models.user import User
from app.services.field_permission_service import _FIELD_PERMS_CV


@pytest.fixture
async def sample_quote(db, admin_user: User) -> Quote:
    """A quote with every NOT-NULL field populated."""
    customer = Customer(
        tenant_id=admin_user.tenant_id,
        name="Quote Canary Co",
        email="qc@canary.example",
        preferred_lang="tr",
        kvkk_consent=True,
        created_by=admin_user.id,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    quote = Quote(
        tenant_id=admin_user.tenant_id,
        quote_number="Q-PICKER-001",
        customer_id=customer.id,
        created_by=admin_user.id,
        status="draft",
        language="tr",
        currency="TRY",
        subtotal=1000.0,
        grand_total=1180.0,
    )
    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    return quote


@pytest.mark.asyncio
@pytest.mark.security
async def test_get_quote_uses_strict_schema_when_no_masking(
    client: AsyncClient,
    auth_headers: dict,
    sample_quote: Quote,
) -> None:
    """No masking → strict schema enforces NOT-NULL fields."""
    _FIELD_PERMS_CV.set({})

    response = await client.get(
        f"/api/v1/quotes/{sample_quote.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # NOT-NULL invariants from QuoteStrictResponse. tenant_id is
    # intentionally NOT surfaced by ``_quote_to_dict`` (R10-API-2)
    # so the strict schema declares it Optional.
    assert body["id"] == sample_quote.id
    assert body["quote_number"] == "Q-PICKER-001"
    assert body["created_at"] is not None
    assert body["updated_at"] is not None

    # Computed/joined extras still round-trip
    assert isinstance(body.get("items"), list)


@pytest.mark.asyncio
@pytest.mark.security
async def test_get_quote_falls_back_to_masked_when_rules_active(
    client: AsyncClient,
    auth_headers: dict,
    sample_quote: Quote,
) -> None:
    """Masking rule active → picker uses loose ``QuoteResponse``."""
    _FIELD_PERMS_CV.set({"quote": {"quote_number": "masked"}})
    try:
        response = await client.get(
            f"/api/v1/quotes/{sample_quote.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == sample_quote.id
        assert "quote_number" in body
    finally:
        _FIELD_PERMS_CV.set({})


@pytest.mark.asyncio
@pytest.mark.security
async def test_quote_openapi_lists_both_response_shapes(
    client: AsyncClient,
) -> None:
    """OpenAPI ``oneOf`` lists both shapes."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    route_spec = spec["paths"]["/api/v1/quotes/{quote_id}"]["get"]
    content_schema = route_spec["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    schema_str = str(content_schema)
    assert "QuoteStrictResponse" in schema_str, schema_str
    assert "QuoteResponse" in schema_str, schema_str
