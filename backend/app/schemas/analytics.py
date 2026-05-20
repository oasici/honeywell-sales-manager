"""Response schemas for analytics endpoints (top parts, monthly trend,
funnel, scorecards, slippage, forecast, etc.).

Generated for Round-15 audit F-027: typed JSON envelopes for every
endpoint in ``app.api.v1.analytics``.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ── Top parts / categories / monthly trend ──────────────────────────────


class TopPartItem(BaseModel):
    model_config = {"from_attributes": True}

    honeywell_code: str | None = None
    request_count: int
    total_quantity: float | int
    total_value: float
    name_en: str | None = None
    name_tr: str | None = None
    category: str | None = None


class MonthlyTrendItem(BaseModel):
    model_config = {"from_attributes": True}

    year: int
    month: int
    quote_count: int
    revenue: float
    sent_count: int


class CategoryBreakdownItem(BaseModel):
    model_config = {"from_attributes": True}

    category: str
    item_count: int
    total_quantity: float | int
    total_value: float


# ── AI usage / quality ──────────────────────────────────────────────────


class AIReviewBreakdown(BaseModel):
    model_config = {"from_attributes": True}

    approved: int
    pending_review: int
    rejected: int


class AIUsageResponse(BaseModel):
    """Base shape produced by ``_compute_ai_metrics``."""

    model_config = {"from_attributes": True}

    total_parsed: int
    review_breakdown: AIReviewBreakdown
    average_confidence: float
    total_corrections: int
    correction_rate_pct: float
    most_corrected_fields: dict[str, int]
    estimated_api_cost_usd: float


class CorrectionTrendItem(BaseModel):
    model_config = {"from_attributes": True}

    year: int
    month: int
    corrections: int


class AIQualityResponse(BaseModel):
    """``ai-quality`` extends ``ai-usage`` with success/fallback metrics.

    The handler spreads ``base_metrics`` into the response so all
    ``AIUsageResponse`` fields appear here too.
    """

    model_config = {"from_attributes": True}

    total_parsed: int
    review_breakdown: AIReviewBreakdown
    average_confidence: float
    total_corrections: int
    correction_rate_pct: float
    most_corrected_fields: dict[str, int]
    estimated_api_cost_usd: float
    total_emails: int
    parse_success: int
    parse_errors: int
    success_rate_pct: float
    fallback_rate_pct: float
    correction_trend: list[CorrectionTrendItem]


# ── Forecast / slippage / funnel ────────────────────────────────────────


class ForecastDayItem(BaseModel):
    model_config = {"from_attributes": True}

    date: str | None = None
    value: float
    count: int


class ForecastResponse(BaseModel):
    model_config = {"from_attributes": True}

    window_days: int
    open_quotes_total: float
    forecast_total: float
    win_rate: float
    coverage_ratio: float
    by_day: list[ForecastDayItem]


class RiskyQuoteItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    quote_number: str | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    status: str
    grand_total: float | None = None
    days_since_touch: int
    updated_at: str | None = None


class AgingBucketItem(BaseModel):
    model_config = {"from_attributes": True}

    bucket: str
    count: int


class SlippageResponse(BaseModel):
    model_config = {"from_attributes": True}

    no_touch_days: int
    risky_quotes: list[RiskyQuoteItem]
    aging_buckets: list[AgingBucketItem]


class FunnelStageItem(BaseModel):
    model_config = {"from_attributes": True}

    stage: str
    count: int
    pct: float


class FunnelConversionItem(BaseModel):
    # Source dict uses the reserved word "from" — keep extra='allow' so
    # the raw dict (with literal ``from`` key) round-trips.
    model_config = {"from_attributes": True, "extra": "allow"}

    rate: float


class FunnelResponse(BaseModel):
    """``conversions`` items use the reserved key ``from``; we keep this
    response permissive (``extra='allow'``) so the raw dict round-trips
    untouched without alias gymnastics in the handler.
    """

    model_config = {"from_attributes": True, "extra": "allow"}

    window_days: int
    funnel: list[FunnelStageItem]
    # conversions: declared as list[dict] in handler with reserved-word
    # 'from' key — allow extra to round-trip without alias collisions.
    conversions: list[dict[str, Any]]


# ── Rep scorecards ──────────────────────────────────────────────────────


class RepScorecardItem(BaseModel):
    model_config = {"from_attributes": True}

    user_id: int
    full_name: str | None = None
    role: str | None = None
    quote_count: int
    sent_count: int
    approved_count: int
    won_count: int
    win_rate: float
    revenue: float
    avg_discount: float


class RepScorecardsResponse(BaseModel):
    model_config = {"from_attributes": True}

    window_days: int
    scorecards: list[RepScorecardItem]


# ── Discounts ───────────────────────────────────────────────────────────


class DiscountOutlierItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    quote_number: str | None = None
    discount_rate: float
    discount_total: float
    grand_total: float


class DiscountsResponse(BaseModel):
    model_config = {"from_attributes": True}

    window_days: int
    total_quotes: int
    p50_discount_rate: float
    p90_discount_rate: float
    avg_discount_rate: float
    outlier_count: int
    outliers: list[DiscountOutlierItem]


class DiscountFlaggedItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    quote_number: str | None = None
    discount_rate: float
    discount_total: float
    grand_total: float
    status: str
    needs_approval: bool


class DiscountGuardrailsResponse(BaseModel):
    model_config = {"from_attributes": True}

    threshold_pct: float
    flagged_count: int
    flagged_quotes: list[DiscountFlaggedItem]


# ── SLA ─────────────────────────────────────────────────────────────────


class SLABreachItem(BaseModel):
    model_config = {"from_attributes": True}

    email_id: int
    from_address: str | None = None
    subject: str | None = None
    response_minutes: int


class SLAResponse(BaseModel):
    model_config = {"from_attributes": True}

    window_days: int
    sla_target_minutes: int
    total_emails: int
    emails_with_action: int
    median_first_action_minutes: int
    breaches_count: int
    breaches: list[SLABreachItem]


# ── Win/loss & data quality & pipeline ──────────────────────────────────


class WinLossReasonItem(BaseModel):
    model_config = {"from_attributes": True}

    reason: str | None = None
    count: int
    total_value: float


class WinLossReasonsResponse(BaseModel):
    model_config = {"from_attributes": True}

    window_days: int
    reasons: list[WinLossReasonItem]


class DataQualityScores(BaseModel):
    model_config = {"from_attributes": True}

    avg_score: float


class DataQualityCustomers(BaseModel):
    model_config = {"from_attributes": True}

    total: int
    missing_phone: int
    missing_email: int
    missing_company: int
    completeness_pct: float


class DataQualityQuotes(BaseModel):
    model_config = {"from_attributes": True}

    total: int
    missing_customer: int
    missing_items: int
    completeness_pct: float


class DataQualityResponse(BaseModel):
    model_config = {"from_attributes": True}

    data: DataQualityScores
    customers: DataQualityCustomers
    quotes: DataQualityQuotes


class PipelineWeeklyDiffResponse(BaseModel):
    model_config = {"from_attributes": True}

    period: str
    new_opportunities: int
    stage_changes: int
    new_quotes: int
    current_pipeline_total: float


# ── Deal velocity & win/loss detail ─────────────────────────────────────


class StageConversionRate(BaseModel):
    model_config = {"from_attributes": True}

    from_stage: str
    to_stage: str
    rate: float


class DealVelocityResponse(BaseModel):
    model_config = {"from_attributes": True}

    window_days: int
    avg_days_per_stage: dict[str, float]
    avg_cycle_time_days: float
    conversions: list[StageConversionRate]


class WinLossOwnerItem(BaseModel):
    model_config = {"from_attributes": True}

    owner_id: int | None = None
    full_name: str | None = None
    total: int
    won: int
    win_rate: float
    won_value: float
    lost_value: float


class AvgDealSizeBucket(BaseModel):
    model_config = {"from_attributes": True}

    avg_amount: float
    count: int


class AvgDealSizes(BaseModel):
    model_config = {"from_attributes": True}

    closed_won: AvgDealSizeBucket
    closed_lost: AvgDealSizeBucket


class LossReasonItem(BaseModel):
    model_config = {"from_attributes": True}

    reason: str | None = None
    count: int
    total_value: float


class WinLossDetailResponse(BaseModel):
    model_config = {"from_attributes": True}

    window_days: int
    overall_win_rate: float
    total_closed: int
    total_won: int
    by_owner: list[WinLossOwnerItem]
    avg_deal_size: AvgDealSizes
    top_loss_reasons: list[LossReasonItem]


# ── Activity drought / single record DQ / waterfall / leaks ─────────────


class ActivityDroughtItem(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str | None = None
    stage: str | None = None
    days_since_last: int
    owner_name: str | None = None


class ActivityDroughtResponse(BaseModel):
    model_config = {"from_attributes": True}

    items: list[ActivityDroughtItem]
    total: int


class RecordQualityResponse(BaseModel):
    """Per-record DQ score — service returns a free-form payload."""

    model_config = {"from_attributes": True, "extra": "allow"}

    data: Any


class WaterfallResponse(BaseModel):
    """Service returns a free-form ``RevenueWaterfallService.get_waterfall``
    payload — keep ``extra='allow'`` to round-trip it untouched.
    """

    model_config = {"from_attributes": True, "extra": "allow"}

    data: Any


class RevenueLeaksResponse(BaseModel):
    """Service returns a free-form ``LeakDetectionService.detect_leaks``
    payload — keep ``extra='allow'`` for the same reason.
    """

    model_config = {"from_attributes": True, "extra": "allow"}

    data: Any
