from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class ManualEmailCreate(BaseModel):
    from_address: EmailStr
    subject: str = Field(min_length=1, max_length=500)
    body_text: str = Field(min_length=1, max_length=50000)


class ParsedPart(BaseModel):
    part_code: str | None = None
    part_description: str | None = None
    quantity: int | None = None
    urgency: str | None = None


class EmailParsedData(BaseModel):
    language: str | None = None
    customer_name: str | None = None
    customer_company: str | None = None
    parts: list[ParsedPart] = []


class EmailMatchResult(BaseModel):
    part_id: int
    honeywell_code: str
    name: str
    score: float
    strategy: str


class EmailResponse(BaseModel):
    """Email request response surface.

    R6-API-8 — pre-R6 the schema declared 19 fields while the router
    emitted 32. The schema isn't currently used as a runtime return
    annotation (so no functional bug), but OpenAPI / SDK codegen drift
    silently spread to every consumer of the spec. Same shape as
    R5-API-2 fix on UserResponse.
    """

    id: int
    # R6-API-8 — tenant_id round-trips per R4-CLOSE-1.
    tenant_id: int | None = None
    customer_id: int | None = None
    message_id: str
    from_address: str
    subject: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    language: str | None = None
    received_at: datetime | None = None
    status: str
    # ``parsed_data`` is stored as a JSON string in the DB but emitted
    # as a dict by ``_email_to_dict(..., include_body=True)`` — the
    # serializer ``json.loads()``-es it. Earlier schema versions declared
    # ``str`` which made the response_model validator reject the dict
    # at runtime. Accept either shape (CI run 26196006175 caught the
    # regression after Round-16 picker work tightened other surfaces).
    parsed_data: dict[str, Any] | str | None = None
    error_message: str | None = None
    category: str | None = None
    category_confidence: float | None = None
    price_sensitivity: bool | None = None
    review_status: str | None = None
    assigned_to: int | None = None
    reviewed_by: int | None = None
    created_at: datetime

    # R6-API-8 — duplicate detection. Set when the parser identifies a
    # message-id we've already processed; the SPA renders a "Yinelenen"
    # banner with a link to the original (R6-RENDER-5).
    is_duplicate: bool | None = None
    duplicate_of_id: int | None = None

    # R6-API-8 — opportunity linkage written by the auto-router.
    opportunity_id: int | None = None

    # R6-API-8 — threading. ``thread_id`` groups messages that belong to
    # the same back-and-forth; ``in_reply_to`` is the parent message id.
    thread_id: str | None = None
    in_reply_to: str | None = None

    # R6-API-8 — read state + agent-priority signals.
    is_read: bool | None = None
    priority: str | None = None
    triage_reason: str | None = None

    # R6-API-8 — sentiment analysis output.
    sentiment: str | None = None
    sentiment_score: float | None = None

    # R6-API-8 — KVKK metadata. ``data_classification`` drives the
    # restricted-message banner (R6-RENDER-3).
    data_classification: str | None = None

    # R6-API-8 — last AI parse timestamp; SPA shows "Son güncelleme".
    last_parsed_at: datetime | None = None

    # Round-17 — sender authentication verdict from SPF/DKIM/DMARC.
    # ``pass`` / ``fail`` / ``none`` / ``unverified``. The SPA shows a
    # "verified sender" badge only when ``pass``; everything else gets
    # a "needs review" banner.
    sender_auth_status: str | None = None

    # Round-17 — list of parsed attachments (Excel/CSV/PDF). Each entry
    # is ``{filename, content_type, size_bytes, text, heuristic_parts,
    # error}``. Persisted as JSON in ``email_requests.attachments_json``;
    # the schema returns the parsed list directly so the SPA detail
    # page can render per-attachment chips with row counts.
    attachments_json: list[dict[str, Any]] | str | None = None

    model_config = {"from_attributes": True}


# Alias for service-layer consumers
ManualEmailRequest = ManualEmailCreate
