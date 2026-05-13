"""Contract response schema.

Round-13 Sprint 6b — see ``invoice.py`` for the design pattern.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class ContractResponse(BaseModel):
    id: int
    tenant_id: int | None = None
    customer_id: int | None = None
    quote_id: int | None = None
    title: str | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    value: float | None = None
    terms_json: str | None = None
    signed_at: datetime | None = None
    signed_by: str | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
