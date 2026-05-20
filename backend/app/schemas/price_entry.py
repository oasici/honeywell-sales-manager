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


class PriceEntrySparePartSummary(BaseModel):
    """Inline spare-part summary the price list embeds for each row.

    Round-15 N15-API-1 quick-win 2 — pre-Round-15 ``/prices/`` was typed
    as ``PaginatedResponse[dict]`` and ``_price_to_dict`` embedded this
    3-field summary inside each price row. Declaring it explicitly keeps
    the contract honest instead of relying on ``extra='allow'``.
    """

    id: int
    honeywell_code: str
    name_en: str | None = None

    model_config = {"from_attributes": True}


class PriceEntryResponse(BaseModel):
    id: int
    spare_part_id: int
    list_price: float
    discount_pct: float
    net_price: float
    currency: str
    # ``_price_to_dict`` emits ISO strings; keep the wire shape a string.
    valid_from: str | None = None
    valid_until: str | None = None
    price_list_version: str | None = None
    created_at: str | None = None
    spare_part: PriceEntrySparePartSummary | None = None

    model_config = {"from_attributes": True}
