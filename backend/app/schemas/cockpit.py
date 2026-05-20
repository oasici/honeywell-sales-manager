"""Cockpit response schemas.

Round-X — typed shapes for the Revenue Cockpit JSON endpoints. All
schemas are extras-tolerant (``extra='allow'``) and every field is
nullable to match the hand-built dict serializers in
``app.api.v1.cockpit``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SignalStats(BaseModel):
    """Signal stats sub-shape used by ``/cockpit/kpis``."""

    model_config = {"extra": "allow"}


class CockpitKPIsResponse(BaseModel):
    pipeline_total: float | None = None
    pipeline_currency: str | None = None
    win_rate: float | None = None
    at_risk_count: int | None = None
    avg_deal_velocity_days: float | None = None
    open_ai_tasks: int | None = None
    signal_stats: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class CockpitActionItem(BaseModel):
    id: int | None = None
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    opportunity_id: int | None = None
    owner_id: int | None = None
    due_at: str | None = None
    created_at: str | None = None
    rotting_days: int | None = None
    last_activity_at: str | None = None
    open_tasks_count: int | None = None
    deal_health: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class CockpitActionsResponse(BaseModel):
    items: list[CockpitActionItem] = []
    total: int | None = None

    model_config = {"extra": "allow"}


class CockpitRiskyAccountItem(BaseModel):
    customer_id: int | None = None
    customer_name: str | None = None
    company: str | None = None
    health_score: float | None = None
    health_risk_level: str | None = None
    active_opportunities: int | None = None
    pipeline_total: float | None = None
    open_tasks_count: int | None = None
    unresolved_high_signals: int | None = None
    last_activity_at: str | None = None

    model_config = {"extra": "allow"}


class CockpitRiskyAccountsResponse(BaseModel):
    items: list[CockpitRiskyAccountItem] = []
    total: int | None = None
    page: int | None = None
    page_size: int | None = None
    pages: int | None = None

    model_config = {"extra": "allow"}


class CockpitMomentumItem(BaseModel):
    id: int | None = None
    title: str | None = None
    stage: str | None = None
    amount: float | None = None
    currency: str | None = None
    owner_id: int | None = None
    customer_id: int | None = None
    momentum_score: int | None = None
    momentum_band: str | None = None
    drivers: list[Any] | None = None

    model_config = {"extra": "allow"}


class CockpitMomentumResponse(BaseModel):
    snapshot_date: str | None = None
    items: list[CockpitMomentumItem] = []
    total: int | None = None
    page: int | None = None
    page_size: int | None = None
    pages: int | None = None

    model_config = {"extra": "allow"}


class CockpitStallingItem(BaseModel):
    id: int | None = None
    title: str | None = None
    stage: str | None = None
    amount: float | None = None
    currency: str | None = None
    owner_id: int | None = None
    customer_id: int | None = None
    days_since_last_buyer_touch: int | None = None
    buyer_reply_count_14d: int | None = None
    meeting_count_30d: int | None = None
    negative_signal_count_14d: int | None = None

    model_config = {"extra": "allow"}


class CockpitStallingResponse(BaseModel):
    snapshot_date: str | None = None
    items: list[CockpitStallingItem] = []
    total: int | None = None
    page: int | None = None
    page_size: int | None = None
    pages: int | None = None

    model_config = {"extra": "allow"}


class CockpitTrendsResponse(BaseModel):
    signal_volume: list[dict[str, Any]] = []

    model_config = {"extra": "allow"}


class ResolveSignalResponse(BaseModel):
    message: str | None = None
    signal_id: int | None = None

    model_config = {"extra": "allow"}


class SignalStreamResponse(BaseModel):
    """Generic signal-stream shape used by `/cockpit/signals` (service emits)."""

    items: list[dict[str, Any]] = []
    total: int | None = None
    page: int | None = None
    page_size: int | None = None
    pages: int | None = None

    model_config = {"extra": "allow"}
