"""Response schemas for V5 Intelligence endpoints."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class BenchmarkGapResponse(BaseModel):
    """Segment gap envelope returned by benchmark_gap_service. Shape varies."""
    model_config = ConfigDict(from_attributes=True, extra="allow")


class TimingWindowItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action_type: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    urgency_score: float | None = None
    reason_codes: list[Any] = []
    status: str | None = None


class TimingWindowsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    opportunity_id: int
    items: list[TimingWindowItem]
    total: int


class TimingWindowDoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str | None = None
    done_at: str | None = None


class ObjectionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    objection_type: str | None = None
    severity: str | None = None
    evidence_text: str | None = None
    resolved_flag: bool | None = None
    ttr_hours: float | None = None
    created_at: str | None = None
    resolved_at: str | None = None


class ObjectionsListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    opportunity_id: int
    items: list[ObjectionItem]
    total: int


class ObjectionDetectItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    objection_type: str | None = None
    severity: str | None = None
    evidence_text: str | None = None


class ObjectionDetectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    opportunity_id: int
    items: list[ObjectionDetectItem]
    total: int


class ResolutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    objection_id: int
    action_type: str | None = None
    action_ts: str | None = None


class SimilarOpportunitiesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    opportunity_id: int
    items: list[dict[str, Any]]
    total: int


class DnaRecommendationsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    segment_key: str
    items: list[dict[str, Any]]
    total: int


class NetworkAnomalyItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    segment_key: str | None = None
    metric_name: str | None = None
    expected_value: float | None = None
    actual_value: float | None = None
    z_score: float | None = None
    severity: str | None = None
    explanation: Any | None = None
    detected_at: str | None = None


class NetworkAnomaliesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[NetworkAnomalyItem]
    total: int


class RepDnaProfileEnvelope(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cluster_label: str | None = None
    strengths: list[Any] = []
    gaps: list[Any] = []
    metrics: Any | None = None
    sample_period_start: str | None = None
    sample_period_end: str | None = None
    generated_at: str | None = None


class RepDnaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rep_id: int
    profile: RepDnaProfileEnvelope | None = None
