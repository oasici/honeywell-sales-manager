"""Response schemas for v2 integration endpoints (calendar + e-sign)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class CalendarAuthUrlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    auth_url: str
    provider: str


class OAuthCallbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str
    provider: str
    status: str


class CalendarConnectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str
    provider: str
    status: str
    next_step: str | None = None


class CalendarStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    connected: bool
    provider: str | None = None
    status: str | None = None
    token_present: bool | None = None
    last_sync_at: str | None = None


class CalendarLinkEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str
    event_id: int
    opportunity_id: int


class CalendarSyncResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str
    synced_count: int
    status: str
    provider: str | None = None


class CalendarHealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool
    status: str
    provider: str | None = None
    error: str | None = None


class CalendarEventCreateResponse(BaseModel):
    """Provider-shaped event payload — passthrough with optional link id."""
    model_config = ConfigDict(from_attributes=True, extra="allow")

    opportunity_event_id: int | None = None


class EsignConnectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str
    provider: str
    status: str


class EsignStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    connected: bool
    provider: str | None = None


class EsignSendResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message: str
    status: str
    provider: str | None = None
    quote_id: int | None = None
    quote_number: str | None = None
    signer_email: str | None = None
    pdf_available: bool | None = None
    next_step: str | None = None


class EsignWebhookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    provider: str | None = None
