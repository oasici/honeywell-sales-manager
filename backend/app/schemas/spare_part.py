from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MissingPricePartResponse(BaseModel):
    """Round-15 audit F-027 — typed row for ``/analytics/parts-without-price``.

    Two variants share the same shape:
      * ``status == "no_price"``    — part exists in the catalog but
        both ``supplier_price`` and ``transfer_price`` are NULL.
      * ``status == "unknown_part"`` — quoted SKU that doesn't exist in
        the catalog at all; ``id`` and the name fields are NULL.

    Pre-fix the endpoint returned a bare list of dicts. The SPA had to
    cast via ``as unknown as`` because the dict shape wasn't surfaced
    in OpenAPI.
    """

    id: int | None = None
    honeywell_code: str
    name_en: str | None = None
    name_tr: str | None = None
    category: str | None = None
    status: Literal["no_price", "unknown_part"]

    model_config = {"from_attributes": True}


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
    """Public spare-part shape returned by /parts/*.

    Round-15 N15-API-1 quick-win 1 — pre-Round-15 ``/parts/`` was typed
    as ``PaginatedResponse[dict]``. The hand-built ``_part_to_dict``
    already emits this exact set of fields, so wiring this schema as
    the ``response_model`` is a 1-line swap with no shape change. Pricing
    columns ride explicitly so SDK consumers don't need ``[key: string]:
    unknown`` extras to read them.
    """

    id: int
    honeywell_code: str
    model_number: str | None = None
    info: str | None = None
    name_en: str | None = None
    name_tr: str | None = None
    description_en: str | None = None
    description_tr: str | None = None
    category: str | None = None
    subcategory: str | None = None
    transfer_price: float | None = None
    supplier_price: float | None = None
    price_currency: str | None = None
    min_margin_pct: float | None = None  # R5-API-7
    keywords_json: str | None = None
    aliases_json: str | None = None
    is_active: bool
    # ``_part_to_dict`` emits ``created_at`` as an ISO string; keep the
    # wire type a string to match. ``datetime`` would force consumers
    # to parse an already-stringified value.
    created_at: str | None = None

    has_price: bool | None = None

    model_config = {"from_attributes": True}
