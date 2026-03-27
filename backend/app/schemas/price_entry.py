from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class PriceEntryCreate(BaseModel):
    spare_part_id: int
    list_price: float = Field(ge=0)
    discount_pct: float = Field(default=0.0, ge=0, le=100)
    net_price: float = Field(ge=0)
    currency: str = Field(default="USD", max_length=10)
    valid_from: date | None = None
    valid_until: date | None = None
    price_list_version: str | None = Field(default=None, max_length=50)


class PriceEntryResponse(BaseModel):
    id: int
    spare_part_id: int
    list_price: float
    discount_pct: float
    net_price: float
    currency: str
    valid_from: date | None = None
    valid_until: date | None = None
    price_list_version: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
