"""Round-16 N15-API-7 catch-all for aggregate ``response_model=dict``
holdouts identified in ``docs/audits/2026-05-20-cross-layer-audit-round15.md``.

Each schema mirrors the dict shape its handler emits today. ``extra=
"allow"`` is reserved for endpoints whose inner shape isn't yet
contract-stable (per-rep enrichments, free-form aggregates). The aim
is to make every router's ``response_model=`` reference a typed
schema so the OpenAPI / SPA codegen path stops emitting bare
``Record<string, unknown>`` types — not to lock every nested key.

Schemas live in a single file (similar to ``round15_pagination.py``)
because each is small (3-10 fields). Future sprints may extract them
per-entity if the namespace grows past ~25 classes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ──────────────────────────────────────────────────────────────────
# Revenue Recognition (app/api/v1/revenue_recognition.py)
# ──────────────────────────────────────────────────────────────────


class RevenueScheduleDetailResponse(BaseModel):
    """``GET /revenue-schedules/{id}`` — schedule + entry breakdown.

    ``entries`` stays free-form to avoid a circular import with the
    existing ``RevenueScheduleRow`` (round15_pagination.py).
    """

    id: int
    tenant_id: int | None = None
    contract_id: int | None = None
    recognition_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    total_amount: float | None = None
    recognized_amount: float | None = None
    currency: str | None = None
    created_by: int | None = None
    created_at: str | None = None
    entries: list[dict[str, Any]]

    model_config = {"from_attributes": True, "extra": "allow"}


class GenerateEntriesResponse(BaseModel):
    """``POST /revenue-schedules/{id}/generate-entries`` — split ack."""

    generated: int
    entries: list[dict[str, Any]]
    message: str | None = None

    model_config = {"from_attributes": True}


class RecognizeEntryResponse(BaseModel):
    """``PATCH .../entries/{id}/recognize`` — single entry ack."""

    entry: dict[str, Any]
    schedule_recognized_amount: float

    model_config = {"from_attributes": True}


class RecognitionDashboardResponse(BaseModel):
    """``GET /revenue-recognition/dashboard`` — tenant rollup."""

    total_scheduled: float
    total_recognized: float
    this_month_pending: float
    recognition_rate_pct: float

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────
# Leads (app/api/v1/leads.py)
# ──────────────────────────────────────────────────────────────────


class LeadAnalyticsResponse(BaseModel):
    """``GET /leads/analytics`` — funnel + by-source + weekly trend.

    Inner fields stay as ``list[dict]`` because each chart point's
    shape is rendering-driven and changing it would churn the SPA.
    """

    window_days: int
    funnel: list[dict[str, Any]]
    by_source: list[dict[str, Any]]
    weekly_trend: list[dict[str, Any]]

    model_config = {"from_attributes": True}


class LeadScoringConfigUpdateResponse(BaseModel):
    """``PUT /leads/scoring-config/{factor_name}`` — single config ack."""

    id: int
    factor_name: str
    weight: int | None = None
    is_active: bool | None = None
    description: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True}


class LeadConvertResponse(BaseModel):
    """``POST /leads/{id}/convert`` — IDs of the rows created."""

    lead_id: int
    customer_id: int
    opportunity_id: int | None = None

    model_config = {"from_attributes": True}


class LeadRescoreResponse(BaseModel):
    """``POST /leads/{id}/rescore`` — new score after manual re-run."""

    lead_id: int
    lead_score: int | float | None = None

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────
# Pricing (app/api/v1/pricing.py)
# ──────────────────────────────────────────────────────────────────


class CustomerPricingRow(BaseModel):
    """Single row in customer-contracted pricing lists / mutations."""

    id: int
    tenant_id: int | None = None
    customer_id: int | None = None
    spare_part_id: int | None = None
    contracted_price: float | None = None
    currency: str | None = None
    discount_pct: float | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    notes: str | None = None
    created_by: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class CustomerPricingListResponse(BaseModel):
    """``GET /pricing/customer/{customer_id}`` — contracted price list."""

    customer_id: int
    pricing: list[CustomerPricingRow]

    model_config = {"from_attributes": True}


class MarginUpdateResponse(BaseModel):
    """``PATCH /pricing/margin/{spare_part_id}`` — minimum-margin ack."""

    id: int
    honeywell_code: str | None = None
    min_margin_pct: float | None = None

    model_config = {"from_attributes": True}


class PriceLookupResponse(BaseModel):
    """``GET /pricing/lookup`` — best resolved price for a (part, customer,
    qty) triple. ``source`` is one of customer_contract / tier / standard."""

    source: str
    unit_price: float
    discount_pct: float | None = None
    currency: str | None = None

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────
# Insights (app/api/v1/insights.py)
# ──────────────────────────────────────────────────────────────────


class SignalsDashboardResponse(BaseModel):
    """``GET /insights/signals`` — topic/severity/impacted summary."""

    window_days: int
    topic_counts: dict[str, int]
    severity_buckets: dict[str, int]
    impacted_opportunity_ids: list[int]
    impacted_total: int
    impacted_returned: int
    impacted_has_more: bool

    model_config = {"from_attributes": True}


class SignalsTrendsResponse(BaseModel):
    """``GET /insights/signals/trends`` — daily counts for trend charts."""

    window_days: int
    series: list[dict[str, Any]]

    model_config = {"from_attributes": True}


class ConversationInsightsResponse(BaseModel):
    """``GET /insights/conversation-insights`` — transcript keyword buckets."""

    window_days: int
    transcript_keyword_hits: dict[str, Any]

    model_config = {"from_attributes": True, "extra": "allow"}


class ConversationSearchResponse(BaseModel):
    """``GET /insights/conversation-search`` — paginated transcript hits."""

    query: str
    page: int
    page_size: int
    total: int
    items: list[dict[str, Any]]

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────
# Opportunities (app/api/v1/opportunities.py)
# ──────────────────────────────────────────────────────────────────


class PipelineStageRow(BaseModel):
    stage: str
    count: int
    total_amount: float
    avg_health_score: float
    stale_count: int

    model_config = {"from_attributes": True}


class PipelineInspectionResponse(BaseModel):
    """``GET /opportunities/pipeline-inspection`` — by-stage health rollup."""

    stages: list[PipelineStageRow]
    pipeline_total: float
    weighted_forecast: float
    coverage_ratio: float

    model_config = {"from_attributes": True}


class OpportunityTimelineRow(BaseModel):
    id: int
    event_type: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    description: str | None = None
    occurred_at: str | None = None
    synthetic: bool | None = None
    via_quote: bool | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class OpportunityTimelineResponse(BaseModel):
    """``GET /opportunities/{id}/timeline`` — mixed events + email rows."""

    opportunity_id: int
    events: list[OpportunityTimelineRow]

    model_config = {"from_attributes": True}


class KanbanColumn(BaseModel):
    stage: str
    count: int
    total_amount: float
    items: list[dict[str, Any]]

    model_config = {"from_attributes": True, "extra": "allow"}


class KanbanBoardResponse(BaseModel):
    """``GET /board/kanban`` — columns of opportunity cards."""

    columns: list[KanbanColumn]

    model_config = {"from_attributes": True}


class ActivitySummaryResponse(BaseModel):
    """``GET /opportunities/{id}/activity-summary`` — per-deal cadence."""

    opportunity_id: int
    total_activities: int
    by_type: dict[str, int]
    last_activity_at: str | None = None
    days_since_last_activity: int
    avg_activities_for_stage: float

    model_config = {"from_attributes": True}


class BoardSummaryResponse(BaseModel):
    """``GET /board/summary`` — manager KPIs."""

    window_days: int
    open_pipeline_total: float
    win_rate: float
    won_count: int
    rotting_count: int

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────
# Deal Health (app/api/v1/deal_health.py)
# ──────────────────────────────────────────────────────────────────


class DealHealthIndicatorRow(BaseModel):
    name: str | None = None
    label: str | None = None
    score: float | None = None
    weight: float | None = None
    raw_value: str | None = None
    description: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class DealHealthReportRow(BaseModel):
    opportunity_id: int
    title: str | None = None
    score: float | None = None
    risk_level: str | None = None
    indicators: list[DealHealthIndicatorRow] = []
    recommendations: list[str] = []

    model_config = {"from_attributes": True, "extra": "allow"}


class DealHealthSummaryBlock(BaseModel):
    total_opportunities: int
    healthy_count: int
    at_risk_count: int
    critical_count: int
    average_score: float

    model_config = {"from_attributes": True}


class DealHealthOverviewResponse(BaseModel):
    """``GET /deal-health/overview/all`` — tenant rollup + per-deal rows."""

    summary: DealHealthSummaryBlock
    opportunities: list[DealHealthReportRow]

    model_config = {"from_attributes": True}


class DealHealthAtRiskResponse(BaseModel):
    """``GET /deal-health/at-risk/list`` — filtered low-health rows."""

    threshold: int
    count: int
    opportunities: list[DealHealthReportRow]

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────
# Coaching (app/api/v1/coaching.py)
# ──────────────────────────────────────────────────────────────────


class CoachingOverviewSummary(BaseModel):
    total_reps: int
    healthy: int
    needs_improvement: int
    at_risk: int
    avg_score: float

    model_config = {"from_attributes": True}


class CoachingOverviewResponse(BaseModel):
    """``GET /coaching/overview`` — manager rollup + per-rep results."""

    summary: CoachingOverviewSummary
    reps: list[dict[str, Any]]

    model_config = {"from_attributes": True}


class CoachingSnapshotRow(BaseModel):
    id: int
    score: float | None = None
    indicators_json: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class CoachingRepTrendsResponse(BaseModel):
    """``GET /coaching/rep/{user_id}/trends`` — score history."""

    user_id: int
    snapshots: list[CoachingSnapshotRow]
    total: int

    model_config = {"from_attributes": True}


class CoachingRepDetailResponse(BaseModel):
    """``GET /coaching/rep/{user_id}`` — full coaching profile.

    The service emits a heterogeneous shape (score, indicators,
    recommendations, risk_level, plus debug fields). ``extra="allow"``
    keeps the wire compatible while still declaring the canonical
    keys for OpenAPI consumers.
    """

    user_id: int | None = None
    score: float | None = None
    risk_level: str | None = None
    indicators: list[dict[str, Any]] = []
    recommendations: list[str] = []

    model_config = {"from_attributes": True, "extra": "allow"}


# ──────────────────────────────────────────────────────────────────
# Webhooks (app/api/v1/webhooks.py)
# ──────────────────────────────────────────────────────────────────


class WebhookDeliveryRow(BaseModel):
    id: int | None = None
    subscription_id: int | None = None
    event_type: str | None = None
    delivered_at: str | None = None
    response_status: int | None = None
    response_body: str | None = None
    retry_count: int | None = None
    payload_size: int | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class WebhookDeliveriesResponse(BaseModel):
    """``GET /webhooks/{id}/deliveries`` — delivery history."""

    webhook_id: int
    count: int
    deliveries: list[WebhookDeliveryRow]

    model_config = {"from_attributes": True, "extra": "allow"}


class WebhookRetryResponse(BaseModel):
    """``POST /webhooks/deliveries/{id}/retry`` — retry ack.

    Shape mirrors ``_delivery_to_dict`` plus the retry counters; uses
    ``extra="allow"`` because the service helper may add timing
    enrichments.
    """

    id: int | None = None
    subscription_id: int | None = None
    event_type: str | None = None
    retry_count: int | None = None
    response_status: int | None = None
    delivered_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class WebhookTestResponse(BaseModel):
    """``POST /webhooks/{id}/test`` — synchronous delivery probe.

    ``status`` is one of ``delivered`` / ``failed``; remaining keys
    come from the service result dict (response_status, retry_count,
    error, etc.) and round-trip via ``extra="allow"``.
    """

    status: str
    success: bool | None = None
    response_status: int | None = None
    error: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ──────────────────────────────────────────────────────────────────
# Sales DNA (app/api/v1/sales_dna.py)
# ──────────────────────────────────────────────────────────────────


class SalesDnaSnapshotResponse(BaseModel):
    """``GET /sales-dna/opportunities/{id}/latest`` and
    ``GET /sales-dna/opportunities/{id}/snapshots/{date}`` — both
    return the same materialised-trait shape."""

    opportunity_id: int
    snapshot_date: str
    traits: dict[str, Any]
    meta: dict[str, Any]

    model_config = {"from_attributes": True, "extra": "allow"}


class MaterializeDnaResponse(BaseModel):
    """``POST /sales-dna/opportunities/{id}/materialize`` — synchronous
    snapshot generation ack."""

    ok: bool
    opportunity_id: int
    snapshot_date: str
    risk_posture: str | None = None
    coaching_hooks: list[dict[str, Any]] | dict[str, Any] | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ──────────────────────────────────────────────────────────────────
# Bundles (app/api/v1/bundles.py)
# ──────────────────────────────────────────────────────────────────


class BundleRow(BaseModel):
    id: int
    tenant_id: int | None = None
    name: str | None = None
    description: str | None = None
    items: list[dict[str, Any]] = []
    bundle_price: float | None = None
    discount_pct: float | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class BundleListResponse(BaseModel):
    """``GET /bundles/`` — active product bundles catalogue."""

    bundles: list[BundleRow]

    model_config = {"from_attributes": True}


class BundleCreateAckResponse(BaseModel):
    """``POST /bundles/`` — ack with new bundle ID."""

    id: int
    name: str

    model_config = {"from_attributes": True}


class BundleQuoteItem(BaseModel):
    spare_part_id: int | None = None
    honeywell_code: str | None = None
    description: str | None = None
    quantity: int | None = None
    unit_price: float | None = None
    discount_pct: float | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class BundleExpandResponse(BaseModel):
    """``POST /bundles/{id}/to-quote-items`` — bundle expansion."""

    items: list[BundleQuoteItem]
    bundle_name: str | None = None

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────
# Subscriptions (app/api/v1/subscriptions.py — non-CRUD endpoints)
# ──────────────────────────────────────────────────────────────────


class MRRDashboardResponse(BaseModel):
    """``GET /subscriptions/mrr-dashboard`` — tenant MRR rollup.

    Service emits a free-form aggregate (current_mrr, growth, churn,
    new MRR, etc.); ``extra="allow"`` keeps the wire compatible while
    declaring "this is a JSON object" in OpenAPI.
    """

    model_config = {"from_attributes": True, "extra": "allow"}


class CancelSubscriptionResponse(BaseModel):
    """``POST /subscriptions/{id}/cancel`` — cancel ack."""

    status: str

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────
# AI Attributes (app/api/v1/ai_attributes.py)
# ──────────────────────────────────────────────────────────────────


class AiAttributeDefinitionResponse(BaseModel):
    """Definition CRUD endpoints emit the service's free-form record
    shape (id + the body fields, plus timestamps and tenant_id).
    ``extra="allow"`` keeps that flexible while still declaring the
    canonical contract."""

    id: int | None = None
    tenant_id: int | None = None
    entity_type: str | None = None
    key: str | None = None
    label: str | None = None
    description: str | None = None
    data_type: str | None = None
    prompt_template: str | None = None
    refresh_hours: int | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class AiAttributeGenerateResponse(BaseModel):
    """``POST /ai-attributes/definitions/{id}/generate`` — synchronous
    generation ack. The service emits a value record plus tracing
    fields (model, prompt_hash, tokens); ``extra="allow"`` keeps the
    wire compatible."""

    model_config = {"from_attributes": True, "extra": "allow"}


# ──────────────────────────────────────────────────────────────────
# Guided Selling (app/api/v1/guided_selling.py)
# ──────────────────────────────────────────────────────────────────


class GuideCreateAckResponse(BaseModel):
    """``POST /guided-selling/`` — create ack."""

    id: int
    name: str

    model_config = {"from_attributes": True}


class GuidedSellingResponse(BaseModel):
    """``GET /guided-selling/{id}`` — guide detail with steps & rules.

    The service returns a heterogeneous dict (guide row + nested
    steps + product rules); ``extra="allow"`` mirrors the
    pre-tightening shape while declaring the canonical fields.
    """

    id: int | None = None
    tenant_id: int | None = None
    name: str | None = None
    description: str | None = None
    steps: list[dict[str, Any]] = []
    product_rules: list[dict[str, Any]] = []
    is_active: bool | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class GuideEvaluateResponse(BaseModel):
    """``POST /guided-selling/{id}/evaluate`` — match score + reasons."""

    model_config = {"from_attributes": True, "extra": "allow"}


# ──────────────────────────────────────────────────────────────────
# Contracts (app/api/v1/contracts.py — non-CRUD endpoints)
# ──────────────────────────────────────────────────────────────────


class ContractAmendmentAck(BaseModel):
    """``POST /contracts/{id}/amend`` — amendment creation ack."""

    id: int
    amendment_type: str | None = None
    contract_status: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ──────────────────────────────────────────────────────────────────
# Quotes (app/api/v1/quotes.py — non-CRUD endpoints)
# ──────────────────────────────────────────────────────────────────


class QuoteVersionsResponse(BaseModel):
    """``GET /quotes/{id}/versions`` — revision chain."""

    quote_id: int | None = None
    versions: list[dict[str, Any]] = []

    model_config = {"from_attributes": True, "extra": "allow"}


class QuoteCompareResponse(BaseModel):
    """``GET /quotes/{a}/compare/{b}`` — line-item diff + summary."""

    quote_a: dict[str, Any] | None = None
    quote_b: dict[str, Any] | None = None
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    summary: dict[str, Any] | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ──────────────────────────────────────────────────────────────────
# Dashboard (app/api/v1/dashboard.py)
# ──────────────────────────────────────────────────────────────────


class DashboardStatsResponse(BaseModel):
    """``GET /dashboard/stats`` — tenant KPI rollup.

    The handler emits a large heterogeneous payload (counts, ratios,
    pipeline rollups) that already has stable keys on the FE side.
    ``extra="allow"`` makes the schema additive while still declaring
    the canonical contract.
    """

    total_emails: int | None = None
    parsed_emails: int | None = None
    total_quotes: int | None = None
    total_customers: int | None = None
    total_parts: int | None = None
    total_users: int | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ──────────────────────────────────────────────────────────────────
# Notifications (app/api/v1/notifications.py)
# ──────────────────────────────────────────────────────────────────


class UnreadCountResponse(BaseModel):
    """``GET /notifications/unread-count`` — sidebar badge counter."""

    unread_count: int

    model_config = {"from_attributes": True}
