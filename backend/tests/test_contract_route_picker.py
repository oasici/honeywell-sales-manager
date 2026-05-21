"""Round-16 N15-API-3 (C7) — GET /contracts/{id} picker integration.

Fifth per-entity rollout after C3-C6.
"""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient

from app.models.contract import Contract
from app.models.customer import Customer
from app.models.user import User
from app.services.field_permission_service import _FIELD_PERMS_CV


@pytest.fixture
async def sample_contract(db, admin_user: User) -> Contract:
    """A contract with every NOT-NULL field populated."""
    customer = Customer(
        tenant_id=admin_user.tenant_id,
        name="Contract Canary Co",
        email="cc@canary.example",
        preferred_lang="tr",
        kvkk_consent=True,
        created_by=admin_user.id,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    contract = Contract(
        tenant_id=admin_user.tenant_id,
        customer_id=customer.id,
        title="Canary Service Agreement",
        status="active",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        value=120000.0,
        created_by=admin_user.id,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


@pytest.mark.asyncio
@pytest.mark.security
async def test_get_contract_uses_strict_schema_when_no_masking(
    client: AsyncClient,
    auth_headers: dict,
    sample_contract: Contract,
) -> None:
    """No masking → strict schema enforces NOT-NULL fields."""
    _FIELD_PERMS_CV.set({})

    response = await client.get(
        f"/api/v1/contracts/{sample_contract.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # NOT-NULL invariants from ContractStrictResponse
    assert body["id"] == sample_contract.id
    assert body["tenant_id"] == sample_contract.tenant_id
    assert body["customer_id"] == sample_contract.customer_id
    assert body["title"] == "Canary Service Agreement"
    assert body["created_by"] == sample_contract.created_by
    assert body["created_at"] is not None
    assert body["updated_at"] is not None


@pytest.mark.asyncio
@pytest.mark.security
async def test_get_contract_falls_back_to_masked_when_rules_active(
    client: AsyncClient,
    auth_headers: dict,
    sample_contract: Contract,
) -> None:
    """Masking rule active → picker uses loose ``ContractResponse``."""
    _FIELD_PERMS_CV.set({"contract": {"title": "masked"}})
    try:
        response = await client.get(
            f"/api/v1/contracts/{sample_contract.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == sample_contract.id
    finally:
        _FIELD_PERMS_CV.set({})


@pytest.mark.asyncio
@pytest.mark.security
async def test_contract_openapi_lists_both_response_shapes(
    client: AsyncClient,
) -> None:
    """OpenAPI ``oneOf`` lists both shapes."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    route_spec = spec["paths"]["/api/v1/contracts/{contract_id}"]["get"]
    content_schema = route_spec["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    schema_str = str(content_schema)
    assert "ContractStrictResponse" in schema_str, schema_str
    assert "ContractResponse" in schema_str, schema_str
