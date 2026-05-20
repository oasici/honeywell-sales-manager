"""Round-16 C2 canary — N15-API-3 RFC Option A proof.

Three assertions prove the two-schema-split pattern works:

1. **CustomerStrictResponse validates a full customer dict** — when
   masking is OFF, the strong schema accepts the live serializer's
   output. NOT-NULL fields are Required and present.

2. **CustomerStrictResponse REJECTS a hidden-field dict** — when a
   field-permission rule has ``hidden`` access, the field is REMOVED
   from the dict by ``apply_perms_sync``. The strong schema must
   refuse this shape; the masked schema (``CustomerResponse``) must
   accept it. This is what justifies the two-schema split.

3. **The picker selects the right schema** — calling
   ``has_masking_rules_for("customer")`` inside a request context
   that carries a masking rule returns True; outside any context
   returns False.

If all three pass, the RFC pattern is engineering-validated and
ready for per-route rollout in Round-17.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.customer import (
    CustomerResponse,
    CustomerStrictResponse,
)
from app.services.field_permission_service import _FIELD_PERMS_CV
from app.services.response_model_picker import has_masking_rules_for


def _customer_full_dict() -> dict:
    """A realistic dict shape ``_customer_to_dict`` emits when no
    permissions are active. All NOT-NULL columns are present."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": 1,
        "tenant_id": 10,
        "name": "Acme Corp",
        "email": "ops@acme.example",
        "preferred_lang": "tr",
        "kvkk_consent": True,
        "created_at": now,
        "updated_at": now,
        "company": "Acme Corp Ltd.",
        "phone": "+90 212 555 0100",
        "address": "Istanbul",
        "tax_id": None,
        "created_by": 42,
        "data_classification": "internal",
        "industry": "Manufacturing",
        "employee_count": 250,
        "annual_revenue": "USD 50M",
        "website": "https://acme.example",
        "linkedin_url": None,
        "enriched_at": now,
        "territory_id": 3,
        "parent_id": None,
        "kvkk_consent_date": now,
        "kvkk_consent_method": "web",
        "data_processing_purpose": "B2B sales",
        "data_retention_until": None,
        "deletion_requested_at": None,
        "quote_count": 12,
        "total_quote_value": 125_000.50,
        "pinned": False,
    }


@pytest.mark.security
def test_strict_schema_accepts_full_dict() -> None:
    """When masking is off, the strict schema validates cleanly and
    exposes every NOT-NULL field as a Required attribute."""
    full = _customer_full_dict()
    parsed = CustomerStrictResponse.model_validate(full)
    # Required fields must round-trip with concrete values (not None)
    assert parsed.id == 1
    assert parsed.tenant_id == 10
    assert parsed.name == "Acme Corp"
    assert parsed.email == "ops@acme.example"
    assert parsed.preferred_lang == "tr"
    assert parsed.kvkk_consent is True
    assert parsed.created_at is not None
    assert parsed.updated_at is not None


@pytest.mark.security
def test_strict_schema_rejects_hidden_field_dict() -> None:
    """When ``hidden`` masking removes a Required field (e.g.
    ``tenant_id``), the strict schema must refuse — that's the
    justification for the two-schema split. The masked schema
    (``CustomerResponse``, Optional-everywhere) must accept the
    same shape."""
    masked = _customer_full_dict()
    del masked["tenant_id"]
    del masked["name"]

    # Strict variant — refuses
    with pytest.raises(ValidationError) as excinfo:
        CustomerStrictResponse.model_validate(masked)
    err = str(excinfo.value)
    assert "tenant_id" in err or "name" in err

    # Masked variant — accepts
    accepted = CustomerResponse.model_validate(masked)
    assert accepted.tenant_id is None  # absent → default-None
    assert accepted.name is None


@pytest.mark.security
def test_picker_returns_false_outside_request_scope() -> None:
    """``has_masking_rules_for`` falls back to False when the
    ContextVar is empty — matches the RFC's "no masking → strong
    schema" intent for tests / jobs."""
    # Reset to default and check
    _FIELD_PERMS_CV.set({})
    assert has_masking_rules_for("customer") is False


@pytest.mark.security
def test_picker_returns_true_when_masking_active() -> None:
    """When the ContextVar carries a masking rule for the entity,
    the picker reports True so the route can fall back to the
    masked schema."""
    _FIELD_PERMS_CV.set({"customer": {"name": "masked"}})
    try:
        assert has_masking_rules_for("customer") is True
        # Sibling entities without rules still return False
        assert has_masking_rules_for("opportunity") is False
    finally:
        _FIELD_PERMS_CV.set({})
