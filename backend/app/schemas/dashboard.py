from __future__ import annotations

from pydantic import BaseModel


class DashboardConfigResponse(BaseModel):
    """User-customizable dashboard layout (dashboard_builder).

    Round-13 Sprint 6b — separate from ``DashboardStats`` (which serves
    the analytics surface) and from the existing dashboard_builder
    handlers' dict shape. ``extra='allow'`` keeps caller-specific
    extras (e.g. widget count, last-executed timestamps) round-tripping.
    """

    id: int
    name: str | None = None
    owner_id: int | None = None
    widgets_json: str | None = None
    is_default: bool | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class DashboardStats(BaseModel):
    total_emails: int = 0
    parsed_emails: int = 0
    total_quotes: int = 0
    sent_quotes: int = 0
    total_parts: int = 0
    total_customers: int = 0
    conversion_rate: float = 0.0
    avg_response_hours: float = 0.0
    pending_review_count: int = 0
    pending_value: float = 0.0


class TopPart(BaseModel):
    honeywell_code: str
    name: str
    total_quantity: int
    request_count: int


class TrendData(BaseModel):
    period: str
    quote_count: int
    total_value: float
