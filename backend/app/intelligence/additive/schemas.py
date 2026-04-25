from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CanonicalSalesEvent(BaseModel):
    """Target `sales_events` shape (subset) — produced read-only from V1 sources."""

    synthetic_id: str = Field(description="Stable id for dedupe in clients: source:pk")
    provenance: Literal["activity_logs", "opportunity_events", "revenue_signals", "opportunity_signals"]
    account_id: int | None = None
    opportunity_id: int | None = None
    contact_id: int | None = None
    event_type: str
    event_ts: str
    actor_type: Literal["rep", "buyer", "system"]
    actor_id: int | None = None
    channel: Literal["email", "call", "meeting", "quote", "task", "system", "other"]
    direction: Literal["inbound", "outbound", "internal", "system"]
    payload_json: dict[str, Any] = Field(default_factory=dict)
    source_ref: str | None = None


class ConversationSignalView(BaseModel):
    """Read-model aligned with target `conversation_signals` (subset; `event_id` optional)."""

    feed: Literal["revenue_signals", "opportunity_signals"] = "revenue_signals"
    synthetic_id: str
    opportunity_id: int | None
    account_id: int | None
    signal_type: str
    signal_strength: str
    confidence: float
    evidence_text: str | None
    model_version: str | None
    event_key: str | None
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)
