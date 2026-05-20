"""Response schemas for AI endpoints (summaries, signals, tasks, deal
risk, churn, competitive intel, email draft, etc.).

Generated for Round-15 audit F-027: typed JSON envelopes for every
endpoint in ``app.api.v1.ai``. Several endpoints proxy service-layer
free-form payloads (deal risk, predictions, RAG status) — those use
``extra='allow'`` with an explanatory comment.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ── Summaries ───────────────────────────────────────────────────────────


class SourceItem(BaseModel):
    """Summary source pointer. Handler may also return plain strings;
    those are typed separately via ``Any`` at the field level.
    """

    model_config = {"from_attributes": True, "extra": "allow"}

    type: str | None = None
    id: int | None = None
    label: str | None = None


class SummarizeResponse(BaseModel):
    """``summary`` endpoint result. Sources may be dicts or strings —
    keep ``list[Any]`` and rely on the handler-side normalization.
    """

    model_config = {"from_attributes": True}

    summary: str
    sources: list[Any] = []
    generated_at: str | None = None
    cached: bool = False


class SummarizeChangesResponse(BaseModel):
    model_config = {"from_attributes": True}

    summary: str
    sources: list[Any] = []
    generated_at: str | None = None
    cached: bool = False
    days: int


class MeetingPrepResponse(BaseModel):
    model_config = {"from_attributes": True}

    prep: str
    customer_id: int


# ── Pipeline suggestions ────────────────────────────────────────────────


class PipelineSuggestResponse(BaseModel):
    model_config = {"from_attributes": True}

    opportunity_id: int
    current_stage: str | None = None
    suggested_stage: str | None = None
    suggested_next_steps: list[str] = []
    factors: list[str] = []


# ── Signals ─────────────────────────────────────────────────────────────


class SignalItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int | None = None
    opportunity_id: int | None = None
    signal_type: str
    severity: str
    evidence: str | None = None
    source_type: str | None = None
    is_resolved: bool | None = None
    created_at: str | None = None


class ExtractedSignalItem(BaseModel):
    model_config = {"from_attributes": True}

    signal_type: str
    severity: str
    evidence: str | None = None


class ExtractSignalsResponse(BaseModel):
    """May return either an empty-signals envelope or the populated form.

    Both shapes share the optional ``message`` field when no data was
    available, so we declare both keys as optional.
    """

    model_config = {"from_attributes": True}

    signals: list[ExtractedSignalItem] = []
    message: str | None = None
    opportunity_id: int | None = None
    method: str | None = None


class GetSignalsResponse(BaseModel):
    """Canonical paginated envelope + legacy aliases (R11-API-1)."""

    model_config = {"from_attributes": True}

    items: list[SignalItem]
    total: int
    page: int
    page_size: int
    pages: int
    # Legacy aliases retained for SPA callers mid-migration.
    opportunity_id: int
    signals: list[SignalItem]


# ── Tasks ───────────────────────────────────────────────────────────────


class TaskItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    description: str | None = None
    opportunity_id: int | None = None
    due_at: str | None = None
    status: str
    source: str | None = None
    priority: str | None = None
    created_at: str | None = None


class TaskListResponse(BaseModel):
    """Canonical paginated envelope + legacy ``tasks`` alias."""

    model_config = {"from_attributes": True}

    items: list[TaskItem]
    total: int
    page: int
    page_size: int
    pages: int
    tasks: list[TaskItem]


class TaskCreateResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    status: str


class TaskUpdateResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    status: str


# ── Generate actions / deal risk / predictions ─────────────────────────


class GenerateActionsResponse(BaseModel):
    """``actions`` is whatever ``ai_action_generator.generate_actions``
    returns — keep ``Any`` so service-side schema evolutions don't
    require coordinated changes here.
    """

    model_config = {"from_attributes": True, "extra": "allow"}

    actions: list[Any]
    count: int


class DealRiskResponse(BaseModel):
    """Free-form payload from
    ``ai_deal_risk_service.assess_deal_risk``. Schema currently includes
    ``risk_score``, ``factors``, ``recommendations`` but is allowed to
    evolve service-side — ``extra='allow'`` keeps the contract loose.
    """

    model_config = {"from_attributes": True, "extra": "allow"}


class PredictCloseResponse(BaseModel):
    """Service payload nested under ``data``. Payload schema lives in
    ``ai_deal_risk_service.predict_close_probability`` — kept open.
    """

    model_config = {"from_attributes": True, "extra": "allow"}

    data: Any


class PredictChurnResponse(BaseModel):
    """Service payload nested under ``data`` from
    ``customer_health_service.predict_churn_risk``. Kept open.
    """

    model_config = {"from_attributes": True, "extra": "allow"}

    data: Any


# ── Competitive intel ───────────────────────────────────────────────────


class CompetitiveIntelResponse(BaseModel):
    """Free-form payload from
    ``competitive_intel_service.get_competitor_dashboard``.
    """

    model_config = {"from_attributes": True, "extra": "allow"}


class CrawlCompetitorsResponse(BaseModel):
    """``crawl_all_competitors`` returns a service-defined free-form
    payload; nest under ``data`` to match the existing envelope.
    """

    model_config = {"from_attributes": True, "extra": "allow"}

    data: Any


class CrawlSingleCompetitorPayload(BaseModel):
    model_config = {"from_attributes": True, "extra": "allow"}

    competitor: str
    results: list[Any]


class CrawlSingleCompetitorResponse(BaseModel):
    model_config = {"from_attributes": True}

    data: CrawlSingleCompetitorPayload


# ── RAG status ──────────────────────────────────────────────────────────


class RAGCollectionItem(BaseModel):
    model_config = {"from_attributes": True}

    name: str
    points_count: int | None = None


class RAGStatusPayload(BaseModel):
    """Variant payload: ``{enabled: bool}`` or
    ``{enabled, collections: [...]}`` or ``{enabled, error}``.
    """

    model_config = {"from_attributes": True, "extra": "allow"}

    enabled: bool
    collections: list[RAGCollectionItem] | None = None
    error: str | None = None


class RAGStatusResponse(BaseModel):
    model_config = {"from_attributes": True}

    data: RAGStatusPayload


# ── Email draft ─────────────────────────────────────────────────────────


class EmailDraftResponse(BaseModel):
    model_config = {"from_attributes": True}

    draft: str
    draft_type: str
    tone: str
    detected_language: str
