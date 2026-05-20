"""Pydantic response schemas for /api/v1/reports/* (Reports V2) endpoints.

Round-15 typing pass — every JSON endpoint in ``api/v1/reports_v2.py``
gets a typed ``response_model`` so OpenAPI / SDK codegen consumers
stop seeing ``any`` payloads.

Note: the XLSX export endpoint (``/templates/{id}/export-excel``) is
EXEMPT because it returns ``StreamingResponse`` (binary file). The CSV
export uses ``PlainTextResponse`` and is also EXEMPT.

The folder + template LIST endpoints stay typed as
``PaginatedResponse[dict]`` (owned by another agent) per the round-15
scope split.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class FolderItem(BaseModel):
    """Single folder row — used inside POST/PUT folder responses.

    The ``data`` wrapping envelope reflects the legacy SPA shape; new
    consumers should treat ``data`` as the canonical payload.
    """

    id: int
    name: str | None = None
    parent_id: int | None = None
    owner_id: int | None = None
    is_shared: bool | None = None
    # PUT response omits these, POST includes them; both fields nullable.
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class FolderEnvelope(BaseModel):
    """POST/PUT /folders[/{id}] — ``{"data": {...}}`` wrapper."""

    data: FolderItem

    model_config = {"from_attributes": True}


class ReportTemplateOut(BaseModel):
    """Template row used inside template envelopes."""

    id: int
    name: str
    description: str | None = None
    entity_type: str | None = None
    columns_json: str | None = None
    filters_json: str | None = None
    group_by: str | None = None
    sort_by: str | None = None
    sort_order: str | None = None
    chart_type: str | None = None
    is_system: bool | None = None
    created_by: int | None = None
    is_public: bool | None = None
    last_run_at: datetime | None = None
    email_schedule: str | None = None
    email_recipients: list[str] | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class ReportTemplateEnvelope(BaseModel):
    """POST/PUT /templates[/{id}] — ``{"data": {...}}`` wrapper."""

    data: ReportTemplateOut

    model_config = {"from_attributes": True}


class ReportExecutionResult(BaseModel):
    """Free-form execution payload from ``ReportEngine`` — typed as
    extras-allowed so engine-specific fields (rows, columns, totals,
    metadata, chart hints, …) flow through without breaking the
    contract.
    """

    page: int | None = None
    page_size: int | None = None
    rows: list[dict[str, Any]] | None = None
    columns: list[str] | None = None
    total: int | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class ReportExecutionEnvelope(BaseModel):
    """POST /templates/{id}/execute and /preview — ``{"data": {...}}`` wrapper."""

    data: ReportExecutionResult

    model_config = {"from_attributes": True}


class AvailableColumnsPayload(BaseModel):
    entity_type: str
    columns: list[str]
    join_columns: list[str]

    model_config = {"from_attributes": True}


class AvailableColumnsResponse(BaseModel):
    """GET /reports/available-columns — column metadata."""

    data: AvailableColumnsPayload

    model_config = {"from_attributes": True}


class ScheduleResultPayload(BaseModel):
    id: int
    name: str
    email_schedule: str | None = None
    email_recipients: list[str] | None = None

    model_config = {"from_attributes": True}


class ScheduleResponse(BaseModel):
    """PATCH /templates/{id}/schedule — schedule update ack."""

    data: ScheduleResultPayload

    model_config = {"from_attributes": True}
