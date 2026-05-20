"""Pydantic schemas for the Account 360 surface.

Round-15 F-009 follow-up — ``GET /customers/{id}/account-360`` returned
a bare dict so the SPA maintained ``Account360Enrichment``,
``Account360LastTouch``, ``Account360OpenDeal``, ``Account360RiskSummary``,
``Account360TimelineItem``, and ``Account360Response`` by hand. The
shape is computed (joins across multiple tables) so it doesn't map to
a single ORM row — but typing the response surface still gives the
SPA + openapi-typescript a contract to enforce.
"""

from __future__ import annotations

from pydantic import BaseModel


class Account360EnrichmentBlock(BaseModel):
    """Rollup figures cached on ``account_enrichments``."""

    customer_id: int
    pipeline_open_amount: float
    closed_won_revenue: float
    active_deal_count: int
    won_deal_count: int
    lost_deal_count: int
    total_deal_count: int
    risk_index: float
    engagement_score: float
    computed_at: str | None = None
    health_score: int | None = None
    health_risk_level: str | None = None
    currency: str = "TRY"

    model_config = {"from_attributes": True}


class Account360LastTouchBlock(BaseModel):
    """Most recent customer touchpoint."""

    at: str | None = None
    source: str  # 'email' | 'meeting' | 'call' | 'note' | 'unknown'
    summary: str

    model_config = {"from_attributes": True}


class Account360OpenDealItem(BaseModel):
    """One open opportunity inlined on Account 360.

    Matches the dict shape emitted by
    ``AccountAggregateService.open_deals``.
    """

    id: int
    title: str
    stage: str
    amount: float | None = None
    currency: str
    owner_id: int | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True}


class Account360RiskSummaryBlock(BaseModel):
    """Risk summary keyed off the customer-health report + unresolved
    high-severity signals.

    Matches the dict shape emitted by
    ``AccountAggregateService.risk_summary``.
    """

    health_score: int | None = None
    risk_level: str  # 'healthy' | 'at_risk' | 'churning' | 'unknown'
    risk_index: float | None = None
    unresolved_high_signals: int
    recommendations: list[str] = []

    model_config = {"from_attributes": True}


class Account360TimelineItemResponse(BaseModel):
    """One row in the merged multi-opportunity timeline.

    The shape is heterogeneous (mixes activity_log + opportunity_event
    + revenue_signal rows) so the body is permissive via
    ``extra='allow'``.
    """

    kind: str
    occurred_at: str | None = None
    opportunity_id: int | None = None
    opportunity_title: str | None = None
    event_type: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    description: str | None = None

    model_config = {"extra": "allow", "from_attributes": True}


class Account360Response(BaseModel):
    """Unified Account 360 payload.

    Returned by ``GET /api/v1/customers/{id}/account-360``.
    """

    customer_id: int
    enrichment: Account360EnrichmentBlock
    last_touch: Account360LastTouchBlock
    open_deals: list[Account360OpenDealItem] = []
    risk_summary: Account360RiskSummaryBlock
    timeline: list[Account360TimelineItemResponse] = []

    model_config = {"from_attributes": True}
