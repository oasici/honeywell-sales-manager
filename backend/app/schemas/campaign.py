"""Campaign response schema.

Round-13 Sprint 6b — see ``invoice.py`` for the design pattern.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CampaignResponse(BaseModel):
    id: int
    tenant_id: int | None = None
    name: str | None = None
    type: str | None = None
    status: str | None = None
    description: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    budget: float | None = None
    actual_cost: float | None = None
    expected_revenue: float | None = None
    actual_revenue: float | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
