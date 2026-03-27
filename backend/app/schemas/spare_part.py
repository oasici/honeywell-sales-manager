from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SparePartCreate(BaseModel):
    honeywell_code: str = Field(min_length=1, max_length=100)
    name_en: str | None = Field(default=None, max_length=500)
    name_tr: str | None = Field(default=None, max_length=500)
    description_en: str | None = None
    description_tr: str | None = None
    category: str | None = Field(default=None, max_length=200)
    subcategory: str | None = Field(default=None, max_length=200)
    keywords_json: str | None = None
    aliases_json: str | None = None


class SparePartUpdate(BaseModel):
    honeywell_code: str | None = Field(default=None, min_length=1, max_length=100)
    name_en: str | None = Field(default=None, max_length=500)
    name_tr: str | None = Field(default=None, max_length=500)
    description_en: str | None = None
    description_tr: str | None = None
    category: str | None = Field(default=None, max_length=200)
    subcategory: str | None = Field(default=None, max_length=200)
    keywords_json: str | None = None
    aliases_json: str | None = None
    is_active: bool | None = None


class SparePartResponse(BaseModel):
    id: int
    honeywell_code: str
    name_en: str | None = None
    name_tr: str | None = None
    description_en: str | None = None
    description_tr: str | None = None
    category: str | None = None
    subcategory: str | None = None
    keywords_json: str | None = None
    aliases_json: str | None = None
    is_active: bool
    created_at: datetime

    has_price: bool | None = None

    model_config = {"from_attributes": True}
