"""Pydantic schemas for the customer-health surface.

Round-15 audit F-009 follow-up — the three customer-health endpoints
(``/customers/health/overview``, ``/customers/health/at-risk``,
``/customers/health/{id}``) were emitting bare dicts so the SPA had to
maintain ``CustomerHealthReport`` + ``HealthIndicator`` +
``HealthExplanation`` + ``HealthOverview`` by hand. This module makes
each shape explicit on the OpenAPI surface so the frontend can drop
the hand-written interfaces and pick them up from
``api-types.gen.ts``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthIndicatorResponse(BaseModel):
    """One row of ``CustomerHealthReport.indicators``.

    ``weight`` is a fractional float (e.g. 0.2 = 20% of total) — NOT an
    integer percentage. The original v1 hand-written FE interface
    declared it as ``number`` which works either way.
    """

    name: str
    label: str
    score: float
    weight: float
    raw_value: Any = None
    description: str | None = None

    model_config = {"from_attributes": True}


class HealthExplanationResponse(BaseModel):
    """Optional ``?explain=true`` block for the detail endpoint."""

    indicator: str
    label: str
    value: Any = None
    weight: float
    contribution: float
    recommendation: str | None = None

    model_config = {"from_attributes": True}


class CustomerHealthReportResponse(BaseModel):
    """Per-customer health summary.

    Returned by:
      * ``GET /customers/health/{id}`` (single)
      * ``GET /customers/health/overview`` (``items[*]``)
      * ``GET /customers/health/at-risk`` (``items[*]``)
    """

    customer_id: int
    customer_name: str | None = None
    company: str | None = None
    score: int
    risk_level: str  # 'healthy' | 'at_risk' | 'churning'
    indicators: list[HealthIndicatorResponse] = []
    recommendations: list[str] = []
    explanations: list[HealthExplanationResponse] | None = None

    model_config = {"from_attributes": True}


class CustomerHealthOverviewSummary(BaseModel):
    """Aggregate counts attached to the overview envelope."""

    total_customers: int
    healthy_count: int
    at_risk_count: int
    churning_count: int
    average_score: float

    model_config = {"from_attributes": True}
