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


class ContractStrictResponse(BaseModel):
    """C7 canary — Round-16 (N15-API-3 RFC Option A).

    Strong-contract variant of ``ContractResponse`` for routes where
    field-permission masking is NOT active.

    NOT-NULL fields (per ORM ``Mapped[int]`` declarations):
      id, tenant_id, customer_id, title, created_by, created_at,
      updated_at.

    ``extra="allow"`` mirrors the masked variant so per-route
    enrichments (``customer`` nested object, ``amendments``,
    revenue_recognition links) round-trip through the strict-shape
    validator unchanged.
    """

    id: int
    tenant_id: int
    customer_id: int
    title: str
    created_by: int
    created_at: datetime
    updated_at: datetime

    # Truly nullable on the ORM
    quote_id: int | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    value: float | None = None
    terms_json: str | None = None
    signed_at: datetime | None = None
    signed_by: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
