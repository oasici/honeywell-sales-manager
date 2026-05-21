"""Round-16 N15-API-3 (C5) — GET /leads/{id} picker integration.

Third per-entity rollout after the customer (C3) and opportunity (C4)
canaries. Same three-assertion structure: no-mask uses strict shape,
masked falls back, OpenAPI documents both.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.models.lead import Lead
from app.models.user import User
from app.services.field_permission_service import _FIELD_PERMS_CV


@pytest.fixture(autouse=True)
def _enable_lead_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """``/leads/*`` routes are gated by ``FEATURE_LEAD_LIFECYCLE``."""
    monkeypatch.setattr(settings, "FEATURE_LEAD_LIFECYCLE", True)


@pytest.fixture
async def sample_lead(db, admin_user: User) -> Lead:
    """A lead with every NOT-NULL field populated."""
    lead = Lead(
        tenant_id=admin_user.tenant_id,
        first_name="Picker",
        last_name="Canary",
        email="picker.canary@example.com",
        owner_id=admin_user.id,
        status="new",
        source="manual",
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return lead


@pytest.mark.asyncio
@pytest.mark.security
async def test_get_lead_uses_strict_schema_when_no_masking(
    client: AsyncClient,
    auth_headers: dict,
    sample_lead: Lead,
) -> None:
    """No masking → strict schema enforces NOT-NULL fields."""
    _FIELD_PERMS_CV.set({})

    response = await client.get(
        f"/api/v1/leads/{sample_lead.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # NOT-NULL invariants from LeadStrictResponse
    assert body["id"] == sample_lead.id
    assert body["tenant_id"] == sample_lead.tenant_id
    assert body["first_name"] == "Picker"
    assert body["last_name"] == "Canary"
    assert body["email"] == "picker.canary@example.com"
    assert body["owner_id"] == sample_lead.owner_id
    assert body["created_at"] is not None
    assert body["updated_at"] is not None

    # Computed extras round-trip
    assert body.get("full_name") == "Picker Canary"


@pytest.mark.asyncio
@pytest.mark.security
async def test_get_lead_falls_back_to_masked_when_rules_active(
    client: AsyncClient,
    auth_headers: dict,
    sample_lead: Lead,
) -> None:
    """Masking rule active → picker uses loose ``LeadResponse``."""
    _FIELD_PERMS_CV.set({"lead": {"email": "masked"}})
    try:
        response = await client.get(
            f"/api/v1/leads/{sample_lead.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == sample_lead.id
        # email may be replaced with the mask sentinel
        assert "email" in body
    finally:
        _FIELD_PERMS_CV.set({})


@pytest.mark.asyncio
@pytest.mark.security
async def test_lead_openapi_lists_both_response_shapes(
    client: AsyncClient,
) -> None:
    """OpenAPI ``oneOf`` lists both shapes."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    route_spec = spec["paths"]["/api/v1/leads/{lead_id}"]["get"]
    content_schema = route_spec["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    schema_str = str(content_schema)
    assert "LeadStrictResponse" in schema_str, schema_str
    assert "LeadResponse" in schema_str, schema_str
