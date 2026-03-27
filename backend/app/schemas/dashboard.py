from __future__ import annotations

from pydantic import BaseModel


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
