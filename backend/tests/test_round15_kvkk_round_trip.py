"""Round-15 F-006/F-008 — Customer KVKK fields round-trip through the
contract.

The deep cross-layer audit found that 5 KVKK / GDPR consent columns
exist on the ``Customer`` model but were absent from
``CustomerResponse`` and from the FE ``Customer`` interface. The
serializer's ``extra='allow'`` config let them pass through at
runtime, but OpenAPI didn't document them — so SDK codegen produced
no types and the SPA had to ``as unknown as`` cast.

These tests pin the new declared contract so a future refactor that
drops the fields trips CI before merge.
"""

from __future__ import annotations


_KVKK_FIELDS = {
    "kvkk_consent",
    "kvkk_consent_date",
    "kvkk_consent_method",
    "data_processing_purpose",
    "data_retention_until",
}


def test_customer_model_declares_kvkk_columns() -> None:
    """Defense-in-depth — if a future migration drops a KVKK column,
    fail loudly rather than silently losing legal-relevant state.
    """
    from app.models.customer import Customer

    cols = {c.name for c in Customer.__table__.columns}
    missing = _KVKK_FIELDS - cols
    assert not missing, f"Customer model missing KVKK columns: {missing}"


def test_customer_response_declares_kvkk_fields() -> None:
    """KVKK consent state must round-trip via the typed contract.

    Pre-Round-15 these fields were stripped from OpenAPI because the
    schema didn't declare them — SDK consumers had no way to reference
    them without manual casting.
    """
    from app.schemas.customer import CustomerResponse

    declared = set(CustomerResponse.model_fields.keys())
    missing = _KVKK_FIELDS - declared
    assert not missing, f"CustomerResponse missing KVKK fields: {missing}"


def test_customer_response_accepts_kvkk_values() -> None:
    """Sanity — populated values validate (no Pydantic type rejection)."""
    from datetime import datetime, timezone

    from app.schemas.customer import CustomerResponse

    payload = {
        "id": 1,
        "kvkk_consent": True,
        "kvkk_consent_date": datetime.now(timezone.utc),
        "kvkk_consent_method": "web",
        "data_processing_purpose": "Sales follow-up",
        "data_retention_until": datetime.now(timezone.utc),
    }
    obj = CustomerResponse.model_validate(payload)
    assert obj.kvkk_consent is True
    assert obj.kvkk_consent_method == "web"
