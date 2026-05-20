"""Response schemas for engagement endpoints (transcripts, keyword packs,
sequences, segments, coaching scorecards).

Generated for Round-15 audit F-027: typed JSON envelopes for every
endpoint in ``app.api.v1.engagement`` (except the
``PaginatedResponse[dict]`` transcripts list which is being closed in
a parallel agent task).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ── Transcripts ─────────────────────────────────────────────────────────


class KeywordFound(BaseModel):
    """Single keyword hit produced by ``_scan_keywords_in_text``."""

    model_config = {"from_attributes": True}

    keyword: str
    category: str
    pack: str | None = None


class TranscriptCreateResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    keywords_found: list[KeywordFound] = []
    created_at: str | None = None


class TranscriptSummarizeResponse(BaseModel):
    """Free-form summary payload from
    ``app.services.transcript_summarizer.summarize_transcript``.

    Shape varies between rule-based and AI paths, so ``extra='allow'``.
    """

    model_config = {"from_attributes": True, "extra": "allow"}


class TranscriptSearchItem(BaseModel):
    """Either an ``ilike`` snippet row or a ``semantic_search`` row.

    Semantic results carry ``score`` + extra columns coming from the
    vector store; ``extra='allow'`` keeps the union flexible.
    """

    model_config = {"from_attributes": True, "extra": "allow"}

    id: int | None = None
    title: str | None = None
    snippet: str | None = None
    opportunity_id: int | None = None
    created_at: str | None = None


class TranscriptSearchResponse(BaseModel):
    model_config = {"from_attributes": True}

    query: str
    total: int
    search_method: str
    items: list[TranscriptSearchItem]


# ── Keyword packs ───────────────────────────────────────────────────────


class KeywordPackItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    category: str
    keywords: list[str] = []
    is_active: bool


class KeywordPackListResponse(BaseModel):
    model_config = {"from_attributes": True}

    packs: list[KeywordPackItem]


class KeywordPackCreateResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    category: str


# ── Sequences ───────────────────────────────────────────────────────────


class EnrollResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    status: str
    current_step: int


class EnrollmentItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: int | None = None
    sequence_id: int
    opportunity_id: int | None = None
    customer_id: int | None = None
    lead_id: int | None = None
    current_step: int
    is_paused: bool
    status: str
    created_at: str | None = None


class EnrollmentListResponse(BaseModel):
    model_config = {"from_attributes": True}

    enrollments: list[EnrollmentItem]


class EnrollmentToggleResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    is_paused: bool
    status: str


class SequenceAnalyticsResponse(BaseModel):
    model_config = {"from_attributes": True}

    exit_reason_distribution: dict[str, int]
    avg_touches_per_target: float
    status_distribution: dict[str, int]
    total_step_runs: int


class SequencePerformanceRow(BaseModel):
    model_config = {"from_attributes": True}

    sequence_id: int
    name: str
    is_active: bool
    enrollments_total: int
    enrollments_active: int
    enrollments_completed: int
    enrollments_exited: int
    enrollments_paused: int
    enrollments_cancelled: int
    avg_completed_steps_per_enrollment: float


class SequencePerformanceRollup(BaseModel):
    model_config = {"from_attributes": True}

    sequence_count: int
    enrollment_count: int


class SequencePerformanceResponse(BaseModel):
    model_config = {"from_attributes": True}

    sequences: list[SequencePerformanceRow]
    rollup: SequencePerformanceRollup


class VariantMetricRow(BaseModel):
    model_config = {"from_attributes": True}

    sequence_id: int
    step_number: int
    variant_key: str | None = None
    total: int
    completed: int
    failed: int


class VariantMetricsResponse(BaseModel):
    model_config = {"from_attributes": True}

    variants: list[VariantMetricRow]


class DomainEventItem(BaseModel):
    """Domain event row — ``payload`` is loaded from JSON so its shape is
    polymorphic. ``extra='allow'`` lets us round-trip unknown payload
    columns without losing data.
    """

    model_config = {"from_attributes": True, "extra": "allow"}

    id: int
    event_type: str
    entity_type: str | None = None
    entity_id: int | None = None
    payload: Any | None = None
    actor_id: int | None = None
    created_at: str | None = None


class DomainEventListResponse(BaseModel):
    model_config = {"from_attributes": True}

    events: list[DomainEventItem]


class StepRunItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    step_number: int
    step_action: str | None = None
    variant_key: str | None = None
    status: str
    reason_codes: list[str] = []
    payload_snapshot: Any | None = None
    started_at: str | None = None
    completed_at: str | None = None


class EnrollmentDetailEnrollment(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    sequence_id: int
    sequence_name: str | None = None
    opportunity_id: int | None = None
    customer_id: int | None = None
    lead_id: int | None = None
    current_step: int
    status: str
    is_paused: bool
    exit_reason: str | None = None
    completed_at: str | None = None
    next_action_at: str | None = None
    created_at: str | None = None


class EnrollmentDetailResponse(BaseModel):
    model_config = {"from_attributes": True}

    enrollment: EnrollmentDetailEnrollment
    step_runs: list[StepRunItem]
    total_steps: int


class StepRunListResponse(BaseModel):
    model_config = {"from_attributes": True}

    enrollment_id: int
    step_runs: list[StepRunItem]


class SequenceUpdateResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: int | None = None
    name: str
    description: str | None = None
    steps: list[dict] = []
    auto_enroll_rules: dict | None = None


class AutoEnrollResponse(BaseModel):
    model_config = {"from_attributes": True}

    sequence_id: int | None = None
    enrolled: int
    message: str


# ── Segments ────────────────────────────────────────────────────────────


class SegmentItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: int | None = None
    name: str
    description: str | None = None
    rules: list[dict] = []
    customer_count: int
    created_at: str | None = None


class SegmentListResponse(BaseModel):
    model_config = {"from_attributes": True}

    segments: list[SegmentItem]


class SegmentCreateResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    tenant_id: int | None = None
    name: str
    customer_count: int


class SegmentCustomerItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str | None = None
    company: str | None = None
    email: str | None = None


class SegmentCustomersResponse(BaseModel):
    model_config = {"from_attributes": True}

    segment_id: int
    segment_name: str
    customers: list[SegmentCustomerItem]


# ── Coaching ────────────────────────────────────────────────────────────


class CoachingScorecardItem(BaseModel):
    model_config = {"from_attributes": True}

    user_id: int
    full_name: str | None = None
    total_quotes: int
    sent_quotes: int
    emails_assigned: int
    emails_processed: int
    process_rate: float
    signals_detected: int
    coaching_notes: list[str] = []


class CoachingScorecardsResponse(BaseModel):
    model_config = {"from_attributes": True}

    window_days: int
    scorecards: list[CoachingScorecardItem]
