"""Webhook subscription response schema.

Round-13 Sprint 6b — see ``invoice.py`` for the design pattern. The
``secret`` HMAC is intentionally not surfaced; ``_subscription_to_dict``
only emits ``secret_present: bool`` (R4-TEN-10 — never echo the HMAC
back to API consumers, even managers within the tenant).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WebhookSubscriptionResponse(BaseModel):
    id: int
    tenant_id: int | None = None
    name: str | None = None
    url: str | None = None
    event_types: list[str] | None = None
    secret_present: bool | None = None
    is_active: bool | None = None
    created_by: int | None = None
    last_triggered_at: str | None = None
    failure_count: int | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
