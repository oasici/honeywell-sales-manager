"""Round-16 N15-API-3 (C8) — GET /subscriptions/{id} picker integration.

Sixth and final per-entity rollout in the C3-C8 RFC sequence
(Customer → Opportunity → Lead → Quote → Contract → Subscription).
"""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient

from app.models.customer import Customer
from app.models.subscription import Subscription
from app.models.user import User
from app.services.field_permission_service import _FIELD_PERMS_CV


@pytest.fixture
async def sample_subscription(db, admin_user: User) -> Subscription:
    """A subscription with every NOT-NULL field populated."""
    customer = Customer(
        tenant_id=admin_user.tenant_id,
        name="Subscription Canary Co",
        email="sub@canary.example",
        preferred_lang="tr",
        kvkk_consent=True,
        created_by=admin_user.id,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    sub = Subscription(
        tenant_id=admin_user.tenant_id,
        customer_id=customer.id,
        name="Canary SaaS Plan",
        status="active",
        billing_cycle="monthly",
        start_date=date(2026, 1, 1),
        mrr=1000.0,
        currency="TRY",
        created_by=admin_user.id,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


@pytest.mark.asyncio
@pytest.mark.security
async def test_get_subscription_uses_strict_schema_when_no_masking(
    client: AsyncClient,
    auth_headers: dict,
    sample_subscription: Subscription,
) -> None:
    """No masking → strict schema enforces NOT-NULL fields."""
    _FIELD_PERMS_CV.set({})

    response = await client.get(
        f"/api/v1/subscriptions/{sample_subscription.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # NOT-NULL invariants from SubscriptionStrictResponse
    assert body["id"] == sample_subscription.id
    assert body["tenant_id"] == sample_subscription.tenant_id
    assert body["customer_id"] == sample_subscription.customer_id
    assert body["name"] == "Canary SaaS Plan"
    assert body["start_date"] is not None
    assert body["created_by"] == sample_subscription.created_by
    assert body["created_at"] is not None
    assert body["updated_at"] is not None


@pytest.mark.asyncio
@pytest.mark.security
async def test_get_subscription_falls_back_to_masked_when_rules_active(
    client: AsyncClient,
    auth_headers: dict,
    sample_subscription: Subscription,
) -> None:
    """Masking rule active → picker uses loose ``SubscriptionResponse``."""
    _FIELD_PERMS_CV.set({"subscription": {"name": "masked"}})
    try:
        response = await client.get(
            f"/api/v1/subscriptions/{sample_subscription.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == sample_subscription.id
    finally:
        _FIELD_PERMS_CV.set({})


@pytest.mark.asyncio
@pytest.mark.security
async def test_subscription_openapi_lists_both_response_shapes(
    client: AsyncClient,
) -> None:
    """OpenAPI ``oneOf`` lists both shapes."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    route_spec = spec["paths"]["/api/v1/subscriptions/{sub_id}"]["get"]
    content_schema = route_spec["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    schema_str = str(content_schema)
    assert "SubscriptionStrictResponse" in schema_str, schema_str
    assert "SubscriptionResponse" in schema_str, schema_str
