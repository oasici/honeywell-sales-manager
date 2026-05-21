"""Subscription response schema.

Round-13 Sprint 6b — see ``invoice.py`` for the design pattern.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class SubscriptionResponse(BaseModel):
    id: int
    tenant_id: int | None = None
    customer_id: int | None = None
    quote_id: int | None = None
    name: str | None = None
    status: str | None = None
    billing_cycle: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    mrr: float | None = None
    next_renewal_date: date | None = None
    auto_renew: bool | None = None
    items_json: str | None = None
    currency: str | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class SubscriptionStrictResponse(BaseModel):
    """C8 canary — Round-16 (N15-API-3 RFC Option A).

    Strong-contract variant of ``SubscriptionResponse`` — the sixth
    and final entity in the C3-C8 canary sequence laid out in the
    polymorphic response schemas RFC.

    NOT-NULL fields (per ORM ``Mapped[int]`` / ``Mapped[date]``):
      id, tenant_id, customer_id, name, start_date, created_by,
      created_at, updated_at.

    ``extra="allow"`` mirrors the masked variant so per-route
    enrichments (``customer`` nested object) round-trip through the
    strict-shape validator unchanged.
    """

    id: int
    tenant_id: int
    customer_id: int
    name: str
    start_date: date
    created_by: int
    created_at: datetime
    updated_at: datetime

    # Truly nullable on the ORM
    quote_id: int | None = None
    status: str | None = None
    billing_cycle: str | None = None
    end_date: date | None = None
    mrr: float | None = None
    next_renewal_date: date | None = None
    auto_renew: bool | None = None
    items_json: str | None = None
    currency: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
