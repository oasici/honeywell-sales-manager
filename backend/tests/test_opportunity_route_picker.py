"""Round-16 N15-API-3 (C4) — GET /opportunities/{id} picker integration.

Second per-entity rollout after the customer canary (C3). Mirrors the
structure of ``test_customer_route_picker.py`` with three assertions:

1. **No masking → strict schema enforced.** With no field-permission
   rule for ``opportunity``, the response includes every NOT-NULL
   ORM field with concrete values.

2. **Masking active → loose schema falls back.** When the
   ``opportunity`` ContextVar carries a rule, the picker uses
   ``OpportunityResponse`` and the route does not 500.

3. **OpenAPI documents both shapes.** The route's ``responses.200``
   lists both ``OpportunityStrictResponse`` and
   ``OpportunityResponse`` so SDK consumers can discriminate.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.field_permission_service import _FIELD_PERMS_CV


@pytest.fixture(autouse=True)
def _enable_v2_board(monkeypatch: pytest.MonkeyPatch) -> None:
    """``/opportunities/*`` routes are gated by ``FEATURE_V2_BOARD``
    (off by default — see ``tests/conftest.py``). Every test in this
    module needs the flag on so the routes don't 404."""
    monkeypatch.setattr(settings, "FEATURE_V2_BOARD", True)


@pytest.fixture
async def sample_opportunity(db, admin_user: User) -> Opportunity:
    """A live opportunity with every NOT-NULL field populated. The
    ``customer_id`` is set via a fixture customer so the
    ``_opp_to_dict`` join doesn't return None and miss the
    ``customer`` summary block."""
    customer = Customer(
        tenant_id=admin_user.tenant_id,
        name="Opp Picker Canary",
        email="opp-picker@canary.example",
        preferred_lang="tr",
        kvkk_consent=True,
        created_by=admin_user.id,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    opp = Opportunity(
        tenant_id=admin_user.tenant_id,
        title="Picker Canary Opp",
        stage="prospecting",
        owner_id=admin_user.id,
        customer_id=customer.id,
        amount=100_000.0,
        currency="TRY",
        status="active",
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


@pytest.mark.asyncio
@pytest.mark.security
async def test_get_opportunity_uses_strict_schema_when_no_masking(
    client: AsyncClient,
    auth_headers: dict,
    sample_opportunity: Opportunity,
) -> None:
    """No masking → response carries every NOT-NULL ORM field with
    concrete non-None values. ``open_quotes_count`` is computed by
    the handler and round-trips through the strict schema's
    ``extra="allow"`` opt-in."""
    _FIELD_PERMS_CV.set({})

    response = await client.get(
        f"/api/v1/opportunities/{sample_opportunity.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # NOT-NULL invariants
    assert body["id"] == sample_opportunity.id
    assert body["tenant_id"] == sample_opportunity.tenant_id
    assert body["title"] == "Picker Canary Opp"
    assert body["stage"] == "prospecting"
    assert body["owner_id"] == sample_opportunity.owner_id
    assert body["created_at"] is not None
    assert body["updated_at"] is not None

    # Computed extras still round-trip
    assert body["open_quotes_count"] == 0
    assert isinstance(body.get("quotes"), list)


@pytest.mark.asyncio
@pytest.mark.security
async def test_get_opportunity_falls_back_to_masked_when_rules_active(
    client: AsyncClient,
    auth_headers: dict,
    sample_opportunity: Opportunity,
) -> None:
    """When the opportunity CV carries a rule, the picker uses the
    loose schema and the route must not 500."""
    _FIELD_PERMS_CV.set({"opportunity": {"title": "masked"}})
    try:
        response = await client.get(
            f"/api/v1/opportunities/{sample_opportunity.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        # id is never masked
        assert body["id"] == sample_opportunity.id
        # title may be replaced with the mask sentinel, but should
        # still be a string — the loose schema accepts both.
        assert "title" in body
    finally:
        _FIELD_PERMS_CV.set({})


@pytest.mark.asyncio
@pytest.mark.security
async def test_opportunity_openapi_lists_both_response_shapes(
    client: AsyncClient,
) -> None:
    """The picker route uses ``response_model=OpportunityStrictResponse |
    OpportunityResponse``. FastAPI compiles this to anyOf/oneOf so
    SDK consumers can codegen the union."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    route_spec = spec["paths"]["/api/v1/opportunities/{opp_id}"]["get"]
    content_schema = route_spec["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    schema_str = str(content_schema)
    assert "OpportunityStrictResponse" in schema_str, schema_str
    assert "OpportunityResponse" in schema_str, schema_str
