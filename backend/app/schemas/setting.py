"""Pydantic response schemas for /api/v1/settings/* endpoints.

Round-15 typing pass — every JSON endpoint in ``api/v1/settings.py``
gets a typed ``response_model`` so OpenAPI / SDK codegen consumers
stop seeing ``any`` payloads.
"""
from __future__ import annotations

from pydantic import BaseModel


class SettingsMapResponse(BaseModel):
    """GET /settings/ — masked key/value map."""

    settings: dict[str, str | None]

    model_config = {"from_attributes": True}


class SettingsUpdateResponse(BaseModel):
    """PUT /settings/ — ack + refreshed (masked) settings map."""

    message: str
    updated_keys: list[str]
    settings: dict[str, str | None]

    model_config = {"from_attributes": True}


class EmailCredentialsSaveResponse(BaseModel):
    """POST /settings/email-credentials — save ack."""

    message: str
    email_setup_completed: bool

    model_config = {"from_attributes": True}


class EmailCredentialsReadResponse(BaseModel):
    """GET /settings/email-credentials — masked password roundtrip."""

    email_address: str
    email_password: str
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    is_configured: bool

    model_config = {"from_attributes": True}


class EmailTestResponse(BaseModel):
    """POST /settings/email-credentials/test — connection probe result."""

    success: bool
    message: str
    imap_host: str | None = None
    imap_port: int | None = None

    model_config = {"from_attributes": True}


class ApiKeyItem(BaseModel):
    """Single API key row (no hash returned)."""

    id: int
    name: str
    scopes_json: str | None = None
    rate_limit: int
    is_active: bool
    last_used_at: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True}


class ApiKeyListResponse(BaseModel):
    """GET /settings/api-keys — canonical pagination envelope."""

    items: list[ApiKeyItem]
    total: int
    page: int
    page_size: int
    pages: int

    model_config = {"from_attributes": True}


class ApiKeyCreateResponse(BaseModel):
    """POST /settings/api-keys — returns plain key ONCE."""

    message: str
    id: int
    name: str
    api_key: str

    model_config = {"from_attributes": True}


class ApiKeyRevokeResponse(BaseModel):
    """DELETE /settings/api-keys/{id} — revoke ack."""

    message: str
    id: int

    model_config = {"from_attributes": True}


class SystemConfigCompany(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None

    model_config = {"from_attributes": True}


class SystemConfigQuoteDefaults(BaseModel):
    prefix: str | None = None
    default_tax_rate: float | None = None
    default_currency: str | None = None
    validity_days: int | None = None

    model_config = {"from_attributes": True}


class SystemConfigRateLimits(BaseModel):
    login: int | str | None = None
    api: int | str | None = None

    model_config = {"from_attributes": True}


class SystemConfigResponse(BaseModel):
    """GET /settings/system-config — feature flags + rate limits + company."""

    feature_flags: dict[str, bool]
    rate_limits: SystemConfigRateLimits
    company: SystemConfigCompany
    quote_defaults: SystemConfigQuoteDefaults

    model_config = {"from_attributes": True}


class SystemConfigUpdateResponse(BaseModel):
    """PUT /settings/system-config/{key} — single-setting update ack."""

    message: str
    key: str
    value: str

    model_config = {"from_attributes": True}


class StageConfigItemResponse(BaseModel):
    id: int
    stage_name: str
    label: str | None = None
    probability_pct: float
    rotting_threshold_days: int
    sort_order: int
    is_active: bool

    model_config = {"from_attributes": True}


class StageConfigListResponse(BaseModel):
    """GET /settings/stage-config — pipeline stage definitions."""

    items: list[StageConfigItemResponse]
    total: int

    model_config = {"from_attributes": True}


class StageConfigUpdateResponse(BaseModel):
    """PUT /settings/stage-config — bulk-update ack."""

    message: str
    updated: int

    model_config = {"from_attributes": True}


class NotificationChannelStatus(BaseModel):
    slack_configured: bool
    teams_configured: bool

    model_config = {"from_attributes": True}


class NotificationChannelsResponse(BaseModel):
    """GET /settings/notification-channels — wraps data in canonical envelope."""

    data: NotificationChannelStatus

    model_config = {"from_attributes": True}


class NotificationChannelsTestResponse(BaseModel):
    """POST /settings/notification-channels/test — per-channel send result."""

    data: dict[str, bool]

    model_config = {"from_attributes": True}
