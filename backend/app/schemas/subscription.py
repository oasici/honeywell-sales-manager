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
