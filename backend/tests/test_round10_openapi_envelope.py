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
    # Pydantic 2 names the generic instance `PaginatedResponse_dict_`.
    assert "PaginatedResponse_dict_" in schema_ref, (
        f"{method.upper()} {path} no longer declares PaginatedResponse[dict]; "
        f"actual schema ref: {schema_ref!r}"
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
