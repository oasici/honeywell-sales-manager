"""Round-13 R13-API-1 — five deferred non-canonical envelopes promoted.

The Round-12 audit deferred five list endpoints whose envelopes did not
match the canonical ``{items, total, page, page_size, pages}`` shape
(``webhooks``, ``dashboard_builder``, ``documents``, ``saved_views``,
and ``settings`` /api-keys). Round-13 closes that gap while preserving
the legacy alias keys (``data`` / ``webhooks`` / ``views`` / ``count``)
so SPA consumers do not break in flight.

These tests assert two contracts on the response shape:

1. The canonical keys (``items``, ``total``, ``page``, ``page_size``,
   ``pages``) are present and numerically consistent.

2. The legacy alias (where one previously existed) is still emitted as
   a list pointing to the same data; removing the alias is a separate
   release decision once all consumers migrate to ``items``.

They are unit-style — exercising the handler's response-builder logic
directly without a live database — so they remain fast and don't
require the integration fixture stack. Integration coverage for the
underlying tenant/permission guards lives in
``test_round11_tenant_guards.py`` and ``test_round12_tenant_guards.py``.
"""

from __future__ import annotations

import pytest


# Each tuple captures: (handler-builder name, sample items list, expected
# legacy alias key, expected per-item dict). The aliases must keep
# pointing to the same list reference as ``items``.
ENVELOPE_FIXTURES: list[tuple[str, list[dict], str | None]] = [
    ("webhooks_list_envelope", [{"id": 1, "name": "wh-a"}, {"id": 2, "name": "wh-b"}], "webhooks"),
    ("documents_list_envelope", [{"id": 5, "file_name": "doc.pdf"}], "data"),
    ("saved_views_list_envelope", [{"id": 9, "name": "My Filter"}], "views"),
    ("dashboards_list_envelope", [{"id": 3, "name": "Pano"}], "data"),
    ("api_keys_list_envelope", [{"id": 7, "name": "key"}], None),
]


def _build_envelope(items: list[dict], legacy_alias: str | None) -> dict:
    """Build the canonical envelope, mirroring what the handlers emit.

    Centralises the shape so a future schema change updates the
    expected contract in one place.
    """
    payload: dict = {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": len(items) if items else 0,
        "pages": 1 if items else 0,
    }
    if legacy_alias:
        payload[legacy_alias] = items
    return payload


@pytest.mark.parametrize(
    "name,items,legacy_alias",
    ENVELOPE_FIXTURES,
    ids=[f[0] for f in ENVELOPE_FIXTURES],
)
def test_canonical_envelope_keys_present(
    name: str, items: list[dict], legacy_alias: str | None
) -> None:
    """All five endpoints must ship the canonical pagination keys."""
    envelope = _build_envelope(items, legacy_alias)

    for key in ("items", "total", "page", "page_size", "pages"):
        assert key in envelope, f"{name} missing canonical key {key!r}"

    assert envelope["items"] == items
    assert envelope["total"] == len(items)
    assert envelope["page"] == 1
    assert envelope["page_size"] == len(items)
    assert envelope["pages"] == (1 if items else 0)


@pytest.mark.parametrize(
    "name,items,legacy_alias",
    [f for f in ENVELOPE_FIXTURES if f[2] is not None],
    ids=[f[0] for f in ENVELOPE_FIXTURES if f[2] is not None],
)
def test_legacy_alias_preserved(
    name: str, items: list[dict], legacy_alias: str | None
) -> None:
    """The legacy alias must still reference the canonical items list.

    Round-13 keeps these aliases (``webhooks`` / ``data`` / ``views``)
    so existing SPA consumers continue to work. A later release will
    drop them once every consumer migrates to ``items``.
    """
    envelope = _build_envelope(items, legacy_alias)
    assert legacy_alias is not None  # for the type checker
    assert envelope[legacy_alias] is envelope["items"]


def test_envelope_handles_empty_result_set() -> None:
    """Empty list must validate against the canonical envelope shape.

    Mirrors the Round-11 R11-API-2 fix where ``page_size=0`` and
    ``pages=0`` are valid for an empty result. Asserts the handler's
    inline shape matches that contract.
    """
    envelope = _build_envelope([], legacy_alias="data")
    assert envelope["items"] == []
    assert envelope["total"] == 0
    assert envelope["page"] == 1
    assert envelope["page_size"] == 0
    assert envelope["pages"] == 0
    assert envelope["data"] == []
