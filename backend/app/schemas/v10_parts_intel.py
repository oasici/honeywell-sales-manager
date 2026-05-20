"""Response schemas for V10 spare parts intelligence endpoints."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class PartsSummaryResponse(BaseModel):
    """Combined dashboard payload — shape varies; passthrough."""
    model_config = ConfigDict(from_attributes=True, extra="allow")


class VelocityResponse(BaseModel):
    """A/B/C tier list — service dataclasses passed through asdict()."""
    model_config = ConfigDict(from_attributes=True)

    items: list[dict[str, Any]]
    total: int


class HeatmapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[dict[str, Any]]
    total: int


class DeadStockItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spare_part_id: int
    honeywell_code: str | None = None
    name: str | None = None
    supplier_price: float | None = None
    frozen_capital_estimate: float | None = None
    last_quoted_at: str | None = None


class DeadStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[DeadStockItem]
    total: int
    frozen_capital_total: float


class InflationTaxResponse(BaseModel):
    """Drift × open-pipeline exposure — shape varies; passthrough."""
    model_config = ConfigDict(from_attributes=True, extra="allow")


class StalePricingItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    spare_part_id: int
    honeywell_code: str | None = None
    name: str | None = None
    last_price_at: str | None = None
    valid_until: str | None = None
    age_days: int | None = None
    reason: str | None = None


class StalePricingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[StalePricingItem]
    total: int


class MarginHealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[dict[str, Any]]
    total: int


class ObsolescenceWatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[dict[str, Any]]
    total: int


class EolRiskResponse(BaseModel):
    """Per-part risk envelope — shape varies per service version."""
    model_config = ConfigDict(from_attributes=True, extra="allow")


class LastTimeBuyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[Any]
    total: int


class DataHealthResponse(BaseModel):
    """Master-data completeness — shape varies; passthrough."""
    model_config = ConfigDict(from_attributes=True, extra="allow")


class DuplicatesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[dict[str, Any]]
    total: int


class OrphanPricingItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    price_entry_id: int
    spare_part_id: int | None = None
    list_price: float | None = None
    created_at: str | None = None
    reason: str | None = None


class OrphanPricingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[OrphanPricingItem]
    total: int


class SubstitutionsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[dict[str, Any]]
    total: int


class CrossCustomerItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    customer_name: str | None = None
    company: str | None = None
    industry: str | None = None
    quote_count: int | None = None
    last_quoted_at: str | None = None


class CrossCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[CrossCustomerItem]
    total: int


class SegmentAffinityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[dict[str, Any]]
    total: int
