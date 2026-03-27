from __future__ import annotations

import math
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(description="Total number of records")
    page: int = Field(ge=1, description="Current page number")
    page_size: int = Field(ge=1, description="Number of items per page")
    pages: int = Field(description="Total number of pages")

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
