"""Request/response schemas for the ERP Connector API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

ERP_TYPES = {"parasut", "logo", "netsis", "sap_b1", "webhook", "mikro"}
ENTITY_TYPES = {"customer", "product", "invoice", "order", "all"}
SYNC_MODES = {"full", "delta"}
CONFLICT_ACTIONS = {"hss_wins", "erp_wins", "merge", "dismiss"}


class ERPConnectionCreate(BaseModel):
    type: str = Field(..., description="Adapter key: parasut | logo | sap_b1 | webhook")
    name: str = Field(..., max_length=120)
    endpoint: str = Field(..., max_length=500)
    credentials: dict[str, Any] = Field(
        ..., description="Adapter-specific secrets; encrypted at rest"
    )
    sync_cron: str | None = None
    config: dict[str, Any] | None = None


class ERPConnectionUpdate(BaseModel):
    name: str | None = Field(None, max_length=120)
    endpoint: str | None = None
    credentials: dict[str, Any] | None = None
    sync_cron: str | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class ERPConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    name: str
    endpoint: str
    is_active: bool
    sync_cron: str | None
    last_customer_sync_at: datetime | None
    last_product_sync_at: datetime | None
    last_invoice_sync_at: datetime | None
    created_at: datetime


class ERPTestConnectionResult(BaseModel):
    ok: bool
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ERPSyncTrigger(BaseModel):
    entity: str = Field("all", description="customer | product | invoice | order | all")
    mode: str = Field("delta", description="full | delta")


class ERPSyncJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connection_id: int
    entity: str
    mode: str
    status: str
    triggered_by: str
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    records_created: int
    records_updated: int
    records_skipped: int
    records_failed: int
    error_message: str | None


class ERPMappingRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    internal_id: int
    external_id: str
    last_source: str
    last_synced_at: datetime


class ERPMappingUpsert(BaseModel):
    entity_type: str
    internal_id: int
    external_id: str


class ERPConflictOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connection_id: int
    entity_type: str
    internal_id: int
    external_id: str
    hss_snapshot: str
    erp_snapshot: str
    field_diffs: str
    status: str
    detected_at: datetime
    resolved_at: datetime | None
    resolved_by: int | None


class ERPConflictResolve(BaseModel):
    action: str = Field(..., description="hss_wins | erp_wins | merge | dismiss")
    merged_payload: dict[str, Any] | None = None
    note: str | None = None
