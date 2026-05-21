from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.customer import CustomerResponse


class QuoteItemCreate(BaseModel):
    spare_part_id: int | None = None
    # R6-API-2b — DB column is VARCHAR(500); R5-API-5 lifted SparePart
    # but missed the quote-item input schemas. Concatenated SKU strings
    # >100 chars hit by import flows were rejecting at boundary with 422.
    honeywell_code: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=500)
    quantity: int = Field(ge=1)
    unit_price: float = Field(ge=0)
    discount_pct: float = Field(default=0.0, ge=0, le=100)


class QuoteCreate(BaseModel):
    customer_id: int | None = None
    language: str = Field(default="tr", max_length=5)
    currency: str = Field(default="TRY", max_length=10)
    tax_rate: float = Field(default=20.0, ge=0)
    # R5-FORM-5 — valid_days was already on the model + DTO but was
    # silently dropped from create/update payloads, leaving every quote
    # at the model default (typically 30 days).
    valid_days: int | None = Field(default=None, ge=1, le=365)
    notes: str | None = None
    items: list[QuoteItemCreate] = []


class QuoteItemUpdate(BaseModel):
    spare_part_id: int | None = None
    # R6-API-2b — see QuoteItemCreate.honeywell_code.
    honeywell_code: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=500)
    quantity: int | None = Field(default=None, ge=1)
    unit_price: float | None = Field(default=None, ge=0)
    discount_pct: float | None = Field(default=None, ge=0, le=100)


class QuoteUpdate(BaseModel):
    customer_id: int | None = None
    language: str | None = Field(default=None, max_length=5)
    currency: str | None = Field(default=None, max_length=10)
    tax_rate: float | None = Field(default=None, ge=0)
    valid_days: int | None = Field(default=None, ge=1, le=365)
    notes: str | None = None
    items: list[QuoteItemCreate] | None = None


class QuoteItemResponse(BaseModel):
    id: int
    quote_id: int
    spare_part_id: int | None = None
    original_text: str | None = None
    honeywell_code: str | None = None
    description: str | None = None
    quantity: int
    unit_price: float
    discount_pct: float
    line_total: float
    match_score: float | None = None
    match_strategy: str | None = None
    is_confirmed: bool
    sort_order: int

    # Inline spare part info
    spare_part_name: str | None = None
    spare_part_category: str | None = None

    model_config = {"from_attributes": True}


class QuoteResponse(BaseModel):
    """Quote response surface.

    R5-API-6 — ``pdf_path`` is no longer returned by the handler
    (round-4 swapped to a boolean ``has_pdf``); declaring it on the
    schema would only mislead codegen consumers.
    R5-API-3 — ``revision_no`` and ``superseded_by`` exposed so the
    V9 revision tree UI can render the v1→v2→v3 chain.

    Round-10 R10-API-6 — Sprint 11 wires this as the response_model
    item type for PaginatedResponse on /quotes/. Same four realities
    as CustomerResponse (see customer.py): masking can strip/mask,
    callers add extras, legacy rows have NULL columns. Schema is
    therefore extras-tolerant and every field is nullable.
    """

    id: int
    tenant_id: int | None = None
    quote_number: str | None = None
    customer_id: int | None = None
    email_request_id: int | None = None
    opportunity_id: int | None = None
    created_by: int | None = None
    approved_by: int | None = None
    status: str | None = None
    language: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    discount_total: float | None = None
    tax_rate: float | None = None
    tax_amount: float | None = None
    grand_total: float | None = None
    valid_days: int | None = None
    notes: str | None = None
    has_pdf: bool | None = None
    version: int | None = None
    parent_quote_id: int | None = None
    revision_no: int | None = None
    superseded_by: int | None = None
    closed_at: datetime | None = None
    close_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    items: list[QuoteItemResponse] = []
    customer: CustomerResponse | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class QuoteStrictResponse(BaseModel):
    """C6 canary — Round-16 (N15-API-3 RFC Option A).

    Strong-contract variant of ``QuoteResponse`` for routes where
    field-permission masking is NOT active. Per the RFC at
    ``docs/decisions/2026-05-21-polymorphic-response-schemas.md``.

    NOT-NULL fields (per ORM ``Mapped[int]`` declarations):
      id, quote_number, created_at, updated_at.

    Note on ``tenant_id``: NOT NULL in the DB but ``_quote_to_dict``
    intentionally omits it (R10-API-2 — see the serializer's
    comment). The strict schema reflects what the serializer emits,
    not the raw ORM, so ``tenant_id`` stays Optional.

    ``extra="allow"`` mirrors the masked variant so per-route
    enrichments (``items`` list, ``customer`` nested object,
    computed totals) round-trip through the strict-shape validator
    unchanged.
    """

    id: int
    quote_number: str
    created_at: datetime
    updated_at: datetime

    # NOT NULL in the DB but deliberately omitted by the serializer
    # — see ``_quote_to_dict`` docstring.
    tenant_id: int | None = None

    # Truly nullable on the ORM
    customer_id: int | None = None
    email_request_id: int | None = None
    opportunity_id: int | None = None
    created_by: int | None = None
    approved_by: int | None = None
    status: str | None = None
    language: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    discount_total: float | None = None
    tax_rate: float | None = None
    tax_amount: float | None = None
    grand_total: float | None = None
    valid_days: int | None = None
    notes: str | None = None
    has_pdf: bool | None = None
    version: int | None = None
    parent_quote_id: int | None = None
    revision_no: int | None = None
    superseded_by: int | None = None
    closed_at: datetime | None = None
    close_reason: str | None = None

    # Computed / joined extras
    items: list[QuoteItemResponse] = []
    customer: CustomerResponse | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# Aliases for service-layer consumers
QuoteItemInput = QuoteItemCreate
QuoteCreateRequest = QuoteCreate
QuoteUpdateRequest = QuoteUpdate
