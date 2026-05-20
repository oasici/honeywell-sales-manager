from __future__ import annotations

import math
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0, description="Total number of records")
    page: int = Field(ge=1, description="Current page number")
    # Round-11 R11-API-2 — relaxed from ``ge=1`` to ``ge=0``. The
    # ``page_size`` field is the count of items per page; on an empty
    # result set (``total=0``) it is legitimately 0. The original
    # ``ge=1`` constraint caused ResponseValidationError on every
    # endpoint that uses the ``{items: [], total: 0, page: 1,
    # page_size: 0, pages: 0}`` shape — most visibly the leaderboard
    # endpoints (R7-API-4 pattern: ``page_size=len(items)``) and the
    # Round-11 cockpit risky/momentum/stalling endpoints that adopt
    # the same canonical envelope. The ``create()`` classmethod below
    # already handles ``page_size=0`` (no ZeroDivisionError on pages
    # computation), so this is the matching contract relaxation.
    page_size: int = Field(ge=0, description="Number of items per page")
    pages: int = Field(ge=0, description="Total number of pages")

    @classmethod
    def create(
        cls, items: list[T], total: int, page: int, page_size: int
    ) -> PaginatedResponse[T]:
        pages = math.ceil(total / page_size) if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )


class ErrorResponse(BaseModel):
    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error message")


class SuccessResponse(BaseModel):
    message: str
    data: Any | None = None


class MessageResponse(BaseModel):
    """Generic ``{message: str, ...}`` response used by many write endpoints.

    Extras-tolerant so callers can attach IDs, counts, or whatever
    auxiliary data the handler decides to return.
    """

    message: str | None = None

    model_config = {"extra": "allow"}


class GenericDataResponse(BaseModel):
    """Generic ``{data: ...}`` envelope used by ad-hoc endpoints."""

    data: Any | None = None

    model_config = {"extra": "allow"}


class ItemsResponse(BaseModel):
    """Generic ``{items: [...], total: N, ...}`` envelope for
    list endpoints that don't fit ``PaginatedResponse`` (no page/page_size).
    """

    items: list[Any] = []
    total: int | None = None

    model_config = {"extra": "allow"}
