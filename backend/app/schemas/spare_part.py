from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SparePartCreate(BaseModel):
    honeywell_code: str = Field(min_length=1, max_length=500)
    name_en: str | None = Field(default=None, max_length=500)
    name_tr: str | None = Field(default=None, max_length=500)
    description_en: str | None = None
    description_tr: str | None = None
    category: str | None = Field(default=None, max_length=200)
    subcategory: str | None = Field(default=None, max_length=200)
    # R5-API-7 — pricing guardrail; pricing engine refuses to quote
    # below this margin. 0..100, percentage.
    min_margin_pct: float | None = Field(default=None, ge=0, le=100)
    keywords_json: str | None = None
    aliases_json: str | None = None


class SparePartUpdate(BaseModel):
    """All fields optional — only provided fields are updated."""
    # R5-API-5 — DB column is String(500); the prior 100 cap rejected
    # valid concatenated SKUs from the import pipeline.
    honeywell_code: str | None = Field(default=None, min_length=1, max_length=500)
    model_number: str | None = Field(default=None, max_length=200)
    info: str | None = None
    name_en: str | None = Field(default=None, max_length=500)
    name_tr: str | None = Field(default=None, max_length=500)
    description_en: str | None = None
    description_tr: str | None = None
    category: str | None = Field(default=None, max_length=200)
    subcategory: str | None = Field(default=None, max_length=200)
    transfer_price: float | None = None
    supplier_price: float | None = None
    # R5-API-7 — see SparePartCreate.min_margin_pct.
    min_margin_pct: float | None = Field(default=None, ge=0, le=100)
    keywords_json: str | None = None
    aliases_json: str | None = None

    model_config = {"extra": "ignore"}


class SparePartResponse(BaseModel):
    id: int
    honeywell_code: str
    name_en: str | None = None
    name_tr: str | None = None
    description_en: str | None = None
    description_tr: str | None = None
    category: str | None = None
    subcategory: str | None = None
    min_margin_pct: float | None = None  # R5-API-7
    keywords_json: str | None = None
    aliases_json: str | None = None
    is_active: bool
    created_at: datetime

    has_price: bool | None = None

    model_config = {"from_attributes": True}
