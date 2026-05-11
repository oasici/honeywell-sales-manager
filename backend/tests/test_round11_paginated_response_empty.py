"""Round-11 R11-API-2 — PaginatedResponse accepts empty result sets.

Production crash signature::

    ResponseValidationError: 1 validation error:
      {'type': 'greater_than_equal',
       'loc': ('response', 'page_size'),
       'msg': 'Input should be greater than or equal to 1',
       'input': 0,
       'ctx': {'ge': 1}}
      GET /api/v1/leaderboard/

The ``PaginatedResponse[T]`` schema in ``app/schemas/common.py`` had
``page_size: int = Field(ge=1)``. ~18 endpoints (leaderboard, approvals,
forecast, customer_health, cockpit, teams, network_intelligence,
duplicates, …) emit the canonical envelope with ``page_size=total``
(non-paginated "bag of all items" endpoints). When the result set is
empty, ``total=0`` and the response fails validation before reaching
the client.

The constraint is relaxed to ``ge=0``: a page with zero items is a
valid empty page. The ``create()`` classmethod was already
``page_size=0``-safe (``pages = math.ceil(total / page_size) if
page_size > 0 else 0``), so this brings the schema in line with the
helper.
"""

from __future__ import annotations

import pytest

from app.schemas.common import PaginatedResponse


def test_empty_result_set_validates() -> None:
    """``page_size=0`` is accepted when the result set is empty."""
    response = PaginatedResponse[dict](
        items=[],
        total=0,
        page=1,
        page_size=0,
        pages=0,
    )
    assert response.total == 0
    assert response.page_size == 0
    assert response.pages == 0
    assert response.items == []


def test_create_helper_handles_empty_set() -> None:
    """``create(items=[], total=0, page=1, page_size=0)`` survives."""
    response = PaginatedResponse[dict].create(
        items=[], total=0, page=1, page_size=0
    )
    assert response.pages == 0


def test_create_helper_handles_normal_paginated_response() -> None:
    """A standard paginated response with non-zero items still works."""
    response = PaginatedResponse[dict].create(
        items=[{"id": 1}, {"id": 2}], total=42, page=1, page_size=20
    )
    assert response.pages == 3  # ceil(42 / 20)
    assert response.page_size == 20
    assert response.total == 42


def test_page_must_still_be_at_least_one() -> None:
    """``page=0`` is still invalid — pagination is 1-indexed."""
    with pytest.raises(Exception):
        PaginatedResponse[dict](
            items=[], total=0, page=0, page_size=0, pages=0
        )


def test_total_cannot_be_negative() -> None:
    """``total`` is also a count, never negative."""
    with pytest.raises(Exception):
        PaginatedResponse[dict](
            items=[], total=-1, page=1, page_size=10, pages=0
        )
