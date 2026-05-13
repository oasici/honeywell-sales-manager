"""Round-10 R10-API-5 — OpenAPI contract gate.

Asserts that the nine list endpoints we type-locked in Sprint 7 keep
their PaginatedResponse[dict] response model in the generated
OpenAPI schema. A future refactor that drops `response_model=` or
returns a non-canonical envelope will fail this test before merge.
"""

from __future__ import annotations

import pytest


# (method, path) pairs that MUST declare PaginatedResponse[dict].
ENVELOPED_LIST_ENDPOINTS = [
    ("get", "/api/v1/customers/"),
    ("get", "/api/v1/quotes/"),
    ("get", "/api/v1/opportunities/"),
    ("get", "/api/v1/leads/"),
    ("get", "/api/v1/invoices/"),
    ("get", "/api/v1/contracts/"),
    ("get", "/api/v1/campaigns/"),
    ("get", "/api/v1/subscriptions/"),
    ("get", "/api/v1/activities/feed"),
]


@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app).get("/openapi.json").json()


@pytest.mark.parametrize("method,path", ENVELOPED_LIST_ENDPOINTS)
def test_list_endpoint_declares_paginated_envelope(
    method: str, path: str, openapi_schema: dict
) -> None:
    path_item = openapi_schema["paths"].get(path)
    assert path_item is not None, f"OpenAPI path {path} not found"
    op = path_item.get(method)
    assert op is not None, f"{method.upper()} {path} not declared"
    schema_ref = (
        op.get("responses", {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
        .get("$ref", "")
    )
    # Pydantic 2 names the generic instance ``PaginatedResponse_<arg>_``.
    # Round-10 Sprint 11 turned the dict generic into typed per-item
    # generics on the Customer / Quote / Opportunity surfaces
    # (PaginatedResponse_CustomerResponse_, _QuoteResponse_,
    # _OpportunityResponse_). Accept any PaginatedResponse_X_ form
    # so future typing upgrades don't break the gate.
    assert "PaginatedResponse_" in schema_ref, (
        f"{method.upper()} {path} no longer declares any PaginatedResponse[…] "
        f"generic; actual schema ref: {schema_ref!r}"
    )


def test_paginated_response_model_declares_canonical_keys(openapi_schema: dict) -> None:
    """The component schema must declare the canonical {items,total,page,page_size,pages}."""
    components = openapi_schema.get("components", {}).get("schemas", {})
    paginated = components.get("PaginatedResponse_dict_") or components.get(
        "PaginatedResponse[dict]"
    )
    assert paginated is not None, "PaginatedResponse_dict_ schema missing from components"
    properties = paginated.get("properties", {})
    for key in ("items", "total", "page", "page_size", "pages"):
        assert key in properties, f"PaginatedResponse missing canonical key '{key}'"


# Round-10 R10-API-5 (Sprint 10) — expansion gate. Started at 9
# endpoints in Sprint 7, expanded to 68 in Sprint 10 via the bulk-add
# script, then dropped to 59 after reverting 8 false-positives (the
# script's body-window regex over-matched into adjacent functions).
# Threshold set to 55 so an accidental router-level revert still
# trips this assertion; an intentional removal lowers the floor in
# the same PR.
MIN_TYPED_ENVELOPE_ENDPOINTS = 63  # Round-13 Sprint 6b bumped 60 → 63 after typing 3 more list envelopes (invoices/email_templates/playbooks/sequences carried over to Sprint 6b promotion).

# Round-13 Sprint 6b — second gate for typed item-response endpoints
# (detail / create / update). These don't use PaginatedResponse but do
# declare a per-entity ``response_model``. Catches regressions where a
# refactor strips response_model from item endpoints.
MIN_TYPED_ITEM_RESPONSE_ENDPOINTS = 30


def test_paginated_envelope_coverage_meets_minimum(openapi_schema: dict) -> None:
    """At least MIN_TYPED_ENVELOPE_ENDPOINTS endpoints must declare
    any PaginatedResponse[…] generic. Catches regressions where a
    router-level refactor strips response_model from many endpoints
    at once. Accepts both ``PaginatedResponse_dict_`` (lazy generic)
    and per-item typed forms like ``PaginatedResponse_CustomerResponse_``.
    """
    count = 0
    for ops in openapi_schema["paths"].values():
        for op in ops.values():
            if not isinstance(op, dict):
                continue
            ref = (
                op.get("responses", {})
                .get("200", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
                .get("$ref", "")
            )
            if "PaginatedResponse_" in ref:
                count += 1
    assert count >= MIN_TYPED_ENVELOPE_ENDPOINTS, (
        f"Only {count} endpoints declare PaginatedResponse[…]; "
        f"expected at least {MIN_TYPED_ENVELOPE_ENDPOINTS}."
    )


def test_typed_item_response_coverage_meets_minimum(openapi_schema: dict) -> None:
    """Round-13 Sprint 6b — at least MIN_TYPED_ITEM_RESPONSE_ENDPOINTS
    detail/create/update endpoints must declare a per-entity
    ``response_model`` (matches a component schema ending in
    ``Response`` that is *not* a PaginatedResponse generic).

    Catches regressions where a router-level refactor strips
    response_model from item endpoints — distinct from the list
    envelope gate above.
    """
    count = 0
    for ops in openapi_schema["paths"].values():
        for op in ops.values():
            if not isinstance(op, dict):
                continue
            for status in ("200", "201"):
                ref = (
                    op.get("responses", {})
                    .get(status, {})
                    .get("content", {})
                    .get("application/json", {})
                    .get("schema", {})
                    .get("$ref", "")
                )
                if not ref:
                    continue
                model = ref.rsplit("/", 1)[-1]
                if model.endswith("Response") and "Paginated" not in model:
                    count += 1
                    break  # Don't double-count if 200 + 201 both declared.
    assert count >= MIN_TYPED_ITEM_RESPONSE_ENDPOINTS, (
        f"Only {count} item endpoints declare a typed Response model; "
        f"expected at least {MIN_TYPED_ITEM_RESPONSE_ENDPOINTS}."
    )
