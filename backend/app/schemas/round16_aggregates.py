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
