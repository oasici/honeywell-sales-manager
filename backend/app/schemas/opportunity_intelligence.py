"""Pydantic schema for the ``GET /opportunities/{id}/intelligence`` payload.

Round-15 audit F-019 — this endpoint was returning an untyped dict, so the
OpenAPI document advertised it as ``application/json``-anything and the SPA
had to maintain ``OpportunityIntelligence`` in ``frontend/src/lib/types.ts``
by hand. Typing the response makes the contract explicit and unlocks the
openapi-typescript generator (15m-2 once enabled).

The ``opportunity`` field is intentionally typed as ``dict[str, Any]`` —
``_opp_to_dict`` in ``opportunities.py`` returns a flexible payload whose
shape depends on call-site flags (``include_quotes``, ``last_activity_at``).
Promoting that to a strict schema is a separate refactor (tracked under the
broader F-009 dict-typed-endpoint sweep).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthIndicator(BaseModel):
    """One row in ``DealHealthReport.indicators``."""

    name: str
    label: str | None = None
    score: int
    weight: int
    raw_value: Any = None
    description: str | None = None

    model_config = {"from_attributes": True}


class DealHealthBlock(BaseModel):
    """Inline view of ``DealHealthReport`` returned by the intelligence
    endpoint. Mirrors ``DealHealthService.compute_deal_health`` output but
    declared independently so future ``DealHealthReport`` changes don't
    silently break the API contract."""

    opportunity_id: int
    score: int
    risk_level: str
    indicators: list[HealthIndicator] = []
    recommendations: list[str] = []

    model_config = {"from_attributes": True}


class OpportunitySignalSummary(BaseModel):
    """Subset of ``OpportunitySignal`` columns surfaced to the SPA."""

    id: int
    signal_type: str
    severity: str
    evidence: str | None = None
    source_type: str | None = None
    source_id: int | None = None
    is_resolved: bool
    created_at: str | None = None  # ISO-8601 string (already formatted server-side)

    model_config = {"from_attributes": True}


class TaskSummary(BaseModel):
    """Subset of ``Task`` columns surfaced to the SPA on this endpoint."""

    id: int
    title: str
    description: str | None = None
    due_at: str | None = None
    status: str
    source: str | None = None
    priority: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True}


class OpportunityIntelligenceResponse(BaseModel):
    """Unified intelligence payload for Opportunity Detail + Board.

    Used by ``GET /api/v1/opportunities/{opp_id}/intelligence``.
    """

    opportunity: dict[str, Any]
    health: DealHealthBlock | None = None
    probability: float | None = None
    signals: list[OpportunitySignalSummary] = []
    tasks: list[TaskSummary] = []
    open_tasks_count: int = 0

    model_config = {"from_attributes": True}
