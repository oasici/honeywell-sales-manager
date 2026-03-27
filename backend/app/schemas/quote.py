from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.customer import CustomerResponse


class QuoteItemCreate(BaseModel):
    spare_part_id: int | None = None
    honeywell_code: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    quantity: int = Field(ge=1)
    unit_price: float = Field(ge=0)
    discount_pct: float = Field(default=0.0, ge=0, le=100)


class QuoteCreate(BaseModel):
    customer_id: int | None = None
    language: str = Field(default="tr", max_length=5)
    currency: str = Field(default="TRY", max_length=10)
    tax_rate: float = Field(default=20.0, ge=0)
    notes: str | None = None
    items: list[QuoteItemCreate] = []


class QuoteItemUpdate(BaseModel):
    spare_part_id: int | None = None
    honeywell_code: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    quantity: int | None = Field(default=None, ge=1)
    unit_price: float | None = Field(default=None, ge=0)
    discount_pct: float | None = Field(default=None, ge=0, le=100)


class QuoteUpdate(BaseModel):
    customer_id: int | None = None
    language: str | None = Field(default=None, max_length=5)
    currency: str | None = Field(default=None, max_length=10)
    tax_rate: float | None = Field(default=None, ge=0)
    notes: str | None = None
    items: list[QuoteItemCreate] | None = None


class QuoteItemResponse(BaseModel):
    id: int
    quote_id: int
    spare_part_id: int | None = None
    original_text: str | None = None
    honeywell_code: str | None = None
    description: str | None = None
    quantity: int
    unit_price: float
    discount_pct: float
    line_total: float
    match_score: float | None = None
    match_strategy: str | None = None
    is_confirmed: bool
    sort_order: int

    # Inline spare part info
    spare_part_name: str | None = None
    spare_part_category: str | None = None

    model_config = {"from_attributes": True}


class QuoteResponse(BaseModel):
    id: int
    quote_number: str
    customer_id: int | None = None
    email_request_id: int | None = None
    created_by: int | None = None
    approved_by: int | None = None
    status: str
    language: str
    currency: str
    subtotal: float
    discount_total: float
    tax_rate: float
    tax_amount: float
    grand_total: float
    valid_days: int
    notes: str | None = None
    pdf_path: str | None = None
    version: int
    parent_quote_id: int | None = None
    created_at: datetime
    updated_at: datetime

    items: list[QuoteItemResponse] = []
    customer: CustomerResponse | None = None

    model_config = {"from_attributes": True}
