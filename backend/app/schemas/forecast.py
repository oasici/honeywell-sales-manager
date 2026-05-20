"""Response schemas for ``app.api.v1.forecast`` aggregate endpoints.

Round-16 N15-API-7 — these schemas replace ``response_model=dict`` on
the five non-paginated forecast aggregates. The shapes mirror what
each handler returns today; ``extra="allow"`` is reserved for the
``team-rollup`` payload because the service helper returns a free-form
``dict[str, Any]`` whose contract we don't want to lock down in this
sprint.

Compatibility note: additive. Runtime payloads are unchanged; only
the OpenAPI contract becomes explicit so the SPA's manual
``WoWData`` / ``HybridForecast`` interfaces can be replaced with
codegen-derived types in a follow-up.
"""

from __future__ import annotations

from pydantic import BaseModel


class HybridForecastByStage(BaseModel):
    stage: str
    count: int
    amount: float
    legacy_weighted: float
    hybrid_weighted: float

    model_config = {"from_attributes": True, "extra": "allow"}


class HybridForecastByConfidenceBand(BaseModel):
    count: int
    amount: float
    hybrid_weighted: float

    model_config = {"from_attributes": True}


class HybridForecastByConfidence(BaseModel):
    low: HybridForecastByConfidenceBand
    medium: HybridForecastByConfidenceBand
    high: HybridForecastByConfidenceBand

    model_config = {"from_attributes": True}


class HybridForecastResponse(BaseModel):
    """``GET /forecast/hybrid`` — legacy vs hybrid weighted forecast."""

    owner_id: int | None = None
    legacy_weighted_total: float
    hybrid_weighted_total: float
    by_stage: list[HybridForecastByStage]
    by_confidence: HybridForecastByConfidence

    model_config = {"from_attributes": True}


class TakeSnapshotResponse(BaseModel):
    """``POST /forecast/snapshot`` — items list of the snapshots just
    written. Each row mirrors ``ForecastSnapshotRow`` but extras stay
    open in case the service helper adds enrichments."""

    items: list[dict]

    model_config = {"from_attributes": True}


class WoWWeekPoint(BaseModel):
    week_label: str
    total: float

    model_config = {"from_attributes": True}


class WoWForecastResponse(BaseModel):
    """``GET /forecast/wow`` — week-over-week pipeline comparison."""

    weeks: list[WoWWeekPoint]
    current_total: float
    previous_total: float
    delta: float
    delta_pct: float

    model_config = {"from_attributes": True}


class ForecastAccuracyPerRep(BaseModel):
    user_id: int
    user_name: str
    forecast: float
    actual: float
    accuracy: float

    model_config = {"from_attributes": True, "extra": "allow"}


class ForecastAccuracyResponse(BaseModel):
    """``GET /forecast/accuracy`` — forecast vs actuals comparison."""

    period: str
    commit_forecast: float
    actual_won: float
    accuracy_pct: float
    per_rep: list[ForecastAccuracyPerRep]

    model_config = {"from_attributes": True}


class TeamForecastRollupResponse(BaseModel):
    """``GET /forecast/team-rollup`` — manager view of team pipeline.

    The underlying service returns a free-form aggregate; we declare
    the schema with ``extra="allow"`` so the OpenAPI contract surfaces
    "this is JSON object" instead of "any". Future sprints can lock
    the inner keys once the SPA stabilizes.
    """

    model_config = {"from_attributes": True, "extra": "allow"}
