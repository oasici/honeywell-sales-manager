"""Sprint 16e C2 (Round-16) — per-request response_model picker.

Implements the picker pattern from the N15-API-3 RFC
(``docs/decisions/2026-05-21-polymorphic-response-schemas.md``,
Option A "Two-schema split"). Routes use ``has_masking_rules_for()``
to decide whether to serialize via the strong shape
(e.g. ``CustomerStrictResponse``) or the masked shape
(``CustomerResponse``, Optional-everywhere).

The picker reads the request-scoped ``_FIELD_PERMS_CV`` ContextVar
that ``prefetch_field_perms_dependency`` populates at the dependency
layer, so the check is O(1) and doesn't touch the database. When the
CV is empty (tests, jobs, dev without role config) the function
returns ``False`` → strong shape applies.

Usage (Round-17 will wire the first route):

    from app.services.response_model_picker import has_masking_rules_for
    from app.schemas.customer import CustomerResponse, CustomerStrictResponse

    @router.get("/{customer_id}")
    async def get_customer(...):
        data = _customer_to_dict(customer)
        if has_masking_rules_for("customer"):
            return CustomerResponse.model_validate(data).model_dump()
        return CustomerStrictResponse.model_validate(data).model_dump()

The RFC's longer-term plan replaces this inline ``if`` with a
``Depends(_pick_customer_response_model)`` resolver once FastAPI's
per-request ``response_model`` story matures. Until then the inline
form is honest about what's happening and keeps the response
validation in Pydantic's hands.
"""

from __future__ import annotations

from app.services.field_permission_service import get_request_field_perms


def has_masking_rules_for(entity_type: str) -> bool:
    """Return True iff the current request has any active masking rule
    for ``entity_type``.

    A rule is "active" when ``get_request_field_perms(entity_type)``
    returns a non-empty mapping. ``hidden`` and ``masked`` both count
    — both can affect whether a Required field is present in the
    response dict.

    Falls back to ``False`` outside a request scope (tests / jobs),
    which gives the strong-schema branch — matches the "no masking →
    Required contract honored" intent of the RFC.
    """
    return bool(get_request_field_perms(entity_type))
