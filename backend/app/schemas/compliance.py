"""Response schemas for KVKK / compliance endpoints."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ConsentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str | None = None
    customer_id: int
    has_consent: bool | None = None
    consent_date: str | None = None
    method: str | None = None
    purpose: str | None = None
    retention_until: str | None = None


class CustomerExportEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    id: int | None = None


class CustomerDataExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer: dict[str, Any]
    quotes: list[dict[str, Any]]
    emails: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]
    activities: list[dict[str, Any]]


class DataDeleteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str
    customer_id: int


class RetentionReportCustomerEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    email: str | None = None
    retention_until: str | None = None
    kvkk_consent: bool | None = None


class RetentionReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    overdue_count: int
    customers: list[RetentionReportCustomerEntry]


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    action: str | None = None
    changes: str | None = None
    ip_address: str | None = None
    created_at: str | None = None


class AuditTrailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: int
    audit_entries: list[AuditEntry]


class RetentionPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    retention_days: int
    action: str
    is_active: bool


class BreachResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    breach_type: str
    status: str | None = None
    severity: str | None = None
    description: str | None = None
    notified_at: str | None = None
    created_at: str | None = None
