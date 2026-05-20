"""Response schemas for V9 gap closure endpoints."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class CrmConnectionCreatedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    label: str
    is_active: bool


class CrmConnectionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    label: str
    is_active: bool
    sync_state: str | None = None
    last_sync_at: str | None = None


class CrmConnectionsListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[CrmConnectionItem]
    total: int


class CrmConnectionTestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool
    provider: str


class CrmSyncJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str | None = None
    items_pulled: int | None = None
    items_failed: int | None = None


class CrmJobItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connection_id: int | None = None
    entity_type: str | None = None
    status: str | None = None
    items_pulled: int | None = None
    items_failed: int | None = None
    started_at: str | None = None
    finished_at: str | None = None


class CrmJobsListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[CrmJobItem]
    total: int


class CalendarConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    is_active: bool


class CalendarConnectionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    calendar_id: str | None = None
    is_active: bool
    expires_at: str | None = None


class CalendarConnectionsListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[CalendarConnectionItem]
    total: int


class MeetingAutoLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    opportunity_id: int | None = None
    matched_by: str | None = None
    confidence: float | None = None


class BoardWipStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[dict[str, Any]]


class ReviewQueueItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    opportunity_id: int | None = None
    suggested_stage: str | None = None
    suggested_close_date: str | None = None
    suggested_amount: float | None = None
    suggestion_source: str | None = None
    evidence: Any | None = None
    suggested_at: str | None = None


class ReviewQueueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[ReviewQueueItem]
    total: int


class ReviewDecideResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    decision: str | None = None
    decided_at: str | None = None


class SemanticSearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    query: str
    items: list[dict[str, Any]]
    total: int


class QuoteRevisionsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    opportunity_id: int
    trees: Any


class ReviseQuoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quote_number: str | None = None
    revision_no: int | None = None
    parent_quote_id: int | None = None


class SlippageEnvelope(BaseModel):
    """Slippage summary varies in shape — passthrough."""
    model_config = ConfigDict(from_attributes=True, extra="allow")


class SlippageByOwnerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[dict[str, Any]]
