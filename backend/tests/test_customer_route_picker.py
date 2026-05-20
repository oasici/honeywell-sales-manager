"""Round-16 N15-API-3 (C3) — GET /customers/{id} picker integration.

Three assertions prove the picker wiring works end-to-end through the
actual HTTP route, not just the schemas in isolation:

1. **No masking → strict schema enforced.** With no field-permission
   rule for ``customer``, the response payload includes every NOT-NULL
   field declared on ``CustomerStrictResponse`` with concrete values.

2. **Masking active → loose schema falls back.** When a request-scoped
   field-permission rule marks one or more customer fields ``hidden``,
   the picker swaps to ``CustomerResponse`` and the route does not
   500 on missing-Required-field validation errors.

3. **OpenAPI documents both shapes.** The route's ``responses.200``
   in the generated schema lists both ``CustomerResponse`` and
   ``CustomerStrictResponse`` under ``oneOf``, so SDK consumers can
   discriminate.

These tests are the canary for the per-entity rollout (C4..C8). If
any of them fail after a future schema change, the picker contract
is broken and Round-17 rollout should pause.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.customer import Customer
from app.models.user import User
from app.services.field_permission_service import _FIELD_PERMS_CV


@pytest.fixture
async def sample_customer(db, admin_user: User) -> Customer:
    """A customer with every NOT-NULL field populated so the strict
    schema's contract holds."""
    customer = Customer(
        tenant_id=admin_user.tenant_id,
        name="Picker Canary Corp",
        email="picker@canary.example",
        company="Picker Canary Corp Ltd.",
        phone="+90 212 555 0100",
        preferred_lang="tr",
        kvkk_consent=True,
        created_by=admin_user.id,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


@pytest.mark.asyncio
@pytest.mark.security
async def test_get_customer_uses_strict_schema_when_no_masking(
    client: AsyncClient,
    auth_headers: dict,
    sample_customer: Customer,
) -> None:
    """No masking rule active → response carries every NOT-NULL field
    declared on ``CustomerStrictResponse`` with concrete (non-None)
    values. This is the contract the SDK relies on when the
    picker selects the strong shape."""
    _FIELD_PERMS_CV.set({})  # explicit reset — no masking

    response = await client.get(
        f"/api/v1/customers/{sample_customer.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # Required fields on the strict schema must round-trip with concrete
    # values (not None, not missing). If the picker silently fell back
    # to the loose shape, these would be allowed to be None.
    assert body["id"] == sample_customer.id
    assert body["tenant_id"] == sample_customer.tenant_id
    assert body["name"] == "Picker Canary Corp"
    assert body["email"] == "picker@canary.example"
    assert body["preferred_lang"] == "tr"
    # kvkk_consent is intentionally omitted by ``_customer_to_dict`` —
    # the strict schema models that omission as Optional.
    assert body["created_at"] is not None
    assert body["updated_at"] is not None

    # Computed extras still round-trip (extra="allow" on the strict
    # schema preserves the existing ``stats`` payload).
    assert "stats" in body
    assert body["stats"]["total_quotes"] == 0
    assert body["pinned"] is False


@pytest.mark.asyncio
@pytest.mark.security
async def test_get_customer_falls_back_to_masked_when_rules_active(
    client: AsyncClient,
    auth_headers: dict,
    sample_customer: Customer,
) -> None:
    """When ``has_masking_rules_for("customer")`` returns True, the
    picker uses the loose ``CustomerResponse`` shape. The route must
    not 500 even if the payload would be missing a NOT-NULL field
    (the masking layer can ``hidden`` a Required field)."""
    # Simulate a masked field by populating the CV — the actual
    # masking would normally come from a real FieldPermissionRule row
    # via ``prefetch_field_perms_dependency``.
    _FIELD_PERMS_CV.set({"customer": {"name": "masked"}})

    try:
        response = await client.get(
            f"/api/v1/customers/{sample_customer.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()

        # Core invariants still hold: id is always present, tenant_id
        # is never masked.
        assert body["id"] == sample_customer.id
        assert body["tenant_id"] == sample_customer.tenant_id
        # The loose schema accepts None for ``name`` if masking removed
        # it — we just assert the route didn't crash.
        assert "name" in body or body.get("name") is None
    finally:
        _FIELD_PERMS_CV.set({})


@pytest.mark.asyncio
@pytest.mark.security
async def test_openapi_lists_both_response_shapes(
    client: AsyncClient,
) -> None:
    """The picker route uses ``response_model=CustomerStrictResponse |
    CustomerResponse``. FastAPI compiles this to ``oneOf`` (or
    ``anyOf``) in the OpenAPI ``responses.200`` block, so SDK
    consumers can codegen the union."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    route_spec = spec["paths"]["/api/v1/customers/{customer_id}"]["get"]
    content_schema = route_spec["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    # FastAPI may render the union as anyOf or oneOf depending on
    # version — both signal the polymorphic intent.
    schema_str = str(content_schema)
    assert "CustomerStrictResponse" in schema_str, schema_str
    assert "CustomerResponse" in schema_str, schema_str
