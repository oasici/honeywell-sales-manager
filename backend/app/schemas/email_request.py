from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ManualEmailCreate(BaseModel):
    from_address: EmailStr
    subject: str = Field(min_length=1, max_length=500)
    body_text: str = Field(min_length=1, max_length=50000)


class ParsedPart(BaseModel):
    part_code: str | None = None
    part_description: str | None = None
    quantity: int | None = None
    urgency: str | None = None


class EmailParsedData(BaseModel):
    language: str | None = None
    customer_name: str | None = None
    customer_company: str | None = None
    parts: list[ParsedPart] = []


class EmailMatchResult(BaseModel):
    part_id: int
    honeywell_code: str
    name: str
    score: float
    strategy: str


class EmailResponse(BaseModel):
    id: int
    customer_id: int | None = None
    message_id: str
    from_address: str
    subject: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    language: str | None = None
    received_at: datetime | None = None
    status: str
    parsed_data: str | None = None
    error_message: str | None = None
    category: str | None = None
    category_confidence: float | None = None
    price_sensitivity: bool | None = None
    review_status: str | None = None
    assigned_to: int | None = None
    reviewed_by: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# Alias for service-layer consumers
ManualEmailRequest = ManualEmailCreate
