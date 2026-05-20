from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# KVKK / data-handling classification — DB column allows
# ``public|internal|confidential|restricted`` (see
# ``backend/app/models/customer.py:64`` and the SPA Select at
# ``CustomerDetailPage.tsx:362-366``).
DataClassification = Literal[
    "public",
    "internal",
    "confidential",
    "restricted",
]


class CustomerCreate(BaseModel):
    """Customer create payload.

    R5-FORM-3 — the SPA's create modal already submits ``website`` and
    ``linkedin_url`` (CustomerListPage.tsx:283-296). Pre-Round-5 these
    fields were silently dropped because Pydantic ignores extras by
    default. The full enrichment field set is also accepted so manual
    overrides aren't blown away by the AI enrichment pipeline.
    """

    name: str = Field(min_length=1, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    tax_id: str | None = Field(default=None, max_length=50)
    preferred_lang: str = Field(default="tr", max_length=5)
    # Enrichment / firmographic fields — edited by hand in the SPA,
    # also written by EnrichmentService when the AI pipeline runs.
    website: str | None = Field(default=None, max_length=255)
    linkedin_url: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=100)
    employee_count: int | None = Field(default=None, ge=0)
    annual_revenue: str | None = Field(default=None, max_length=50)
    parent_id: int | None = None
    territory_id: int | None = None
    # N15-FE-2 (Round-15) — KVKK / GDPR-relevant column the SPA already
    # surfaces in the create + edit forms (CustomerDetailPage.tsx:362,
    # CustomerListPage.tsx create modal). Pre-Round-15 the field was
    # silently dropped on the wire because the schema didn't declare it.
    data_classification: DataClassification | None = None


class CustomerUpdate(BaseModel):
    """Customer update payload — same writable surface as CustomerCreate
    minus ``email`` (which has a separate uniqueness check path)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    tax_id: str | None = Field(default=None, max_length=50)
    preferred_lang: str | None = Field(default=None, max_length=5)
    website: str | None = Field(default=None, max_length=255)
    linkedin_url: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=100)
    employee_count: int | None = Field(default=None, ge=0)
    annual_revenue: str | None = Field(default=None, max_length=50)
    parent_id: int | None = None
    territory_id: int | None = None
    # N15-FE-2 — see CustomerCreate above. The SPA already serializes
    # ``data_classification`` on every PATCH; declaring it here unblocks
    # persistence.
    data_classification: DataClassification | None = None


class CustomerResponse(BaseModel):
    """Customer response surface.

    R6-API-9 — pre-R6 the canonical ``_customer_to_dict`` emitted 17
    fields while the schema declared 7, leaving 11 fields invisible to
    OpenAPI / SDK codegen consumers. Mirrors R5-FORM-3/4 which widened
    the input side; this brings the output side back in sync.

    Round-10 R10-API-6 — Sprint 11 turned this from a documentation-
    only schema into the runtime response_model for /customers/ and
    /customers/high-intent. To stay non-breaking against the four
    realities of the live serializer:

      1. ``apply_request_perms`` can strip any field (``hidden`` rule).
      2. ``apply_request_perms`` can mask any field to ``"***"``
         (``masked`` rule).
      3. Callers add caller-specific extras (``pinned``, ``stats``,
         ``health_score``, …) on top of the dict.
      4. Pre-bootstrap rows still exist with ``created_at`` / ``email``
         /etc. set to None.

    The schema is therefore extras-tolerant (``extra='allow'``) and
    every field nullable.
    """

    id: int
    # R6-API-9 — round-trip tenant_id, mirroring R4-CLOSE-1 for
    # opportunity/quote/etc.
    tenant_id: int | None = None
    name: str | None = None
    company: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tax_id: str | None = None
    preferred_lang: str | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    quote_count: int | None = None
    total_quote_value: float | None = None
    # Sprint 16g (Round-15) — per-user pin state, computed by the
    # /customers handler via the ``user_customer_pins`` lookup. The SPA's
    # manual ``Customer`` interface in lib/types.ts has read it for
    # months; declaring it here unblocks the api-types.gen.ts migration
    # (audit N15-ARCH-1 pre-step).
    pinned: bool | None = None

    # R6-API-9 — firmographic fields populated by the AI enrichment
    # pipeline + manual overrides.
    industry: str | None = None
    employee_count: int | None = None
    annual_revenue: str | None = None
    website: str | None = None
    linkedin_url: str | None = None
    enriched_at: datetime | None = None

    # R6-API-9 — account hierarchy + territory rollups.
    parent_id: int | None = None
    territory_id: int | None = None

    # R6-API-9 / R6-RENDER-6 — KVKK metadata. ``deletion_requested_at``
    # gates the SPA's pending-delete banner; ``data_classification``
    # drives row-level masking decisions.
    data_classification: str | None = None
    deletion_requested_at: datetime | None = None

    # Round-15 F-006 — KVKK / GDPR consent state, populated by
    # ``/customers/{id}/kvkk-consent``. The DB columns existed and the
    # serializer emitted them via ``extra='allow'`` pass-through, but
    # OpenAPI didn't document them, so SDK codegen + the SPA had to
    # ``as unknown as`` cast. Now declared so the contract is explicit.
    kvkk_consent: bool | None = None
    kvkk_consent_date: datetime | None = None
    # 'web' | 'email' | 'in_person' | 'import' — kept as `str | None`
    # so we don't lock the wire format if a new method is added before
    # the SPA ships the literal union.
    kvkk_consent_method: str | None = None
    data_processing_purpose: str | None = None
    data_retention_until: datetime | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class CustomerStrictResponse(BaseModel):
    """C2 canary — Round-16 (N15-API-3 RFC Option A).

    Strong-contract variant of ``CustomerResponse`` for routes where
    field-permission masking is NOT active. Every NOT-NULL column on
    the Customer ORM is declared Required; only genuinely nullable
    columns stay Optional.

    Per the RFC at ``docs/decisions/2026-05-21-polymorphic-response-schemas.md``,
    this schema is the canary deliverable. Routes opt in via the picker
    at ``backend/app/services/response_model_picker.py``; if any
    field-permission rule is active for ``customer`` on the current
    request, the picker falls back to ``CustomerResponse`` so masking
    behaviour is preserved.

    Compatibility note: additive only. No existing route uses it yet;
    existing routes continue to return ``CustomerResponse``. Round-17
    will wire the picker on /customers/{id} as the first canary route.
    """

    id: int
    tenant_id: int
    name: str
    email: str
    preferred_lang: str
    created_at: datetime
    updated_at: datetime
    kvkk_consent: bool

    # Truly nullable on the ORM
    company: str | None = None
    phone: str | None = None
    address: str | None = None
    tax_id: str | None = None
    created_by: int | None = None
    kvkk_consent_date: datetime | None = None
    kvkk_consent_method: str | None = None
    data_processing_purpose: str | None = None
    data_retention_until: datetime | None = None
    deletion_requested_at: datetime | None = None
    data_classification: DataClassification | None = None
    industry: str | None = None
    employee_count: int | None = None
    annual_revenue: str | None = None
    website: str | None = None
    linkedin_url: str | None = None
    enriched_at: datetime | None = None
    territory_id: int | None = None
    parent_id: int | None = None

    # Computed extras emitted by _customer_to_dict — Optional because
    # they're not always populated (e.g. /high-intent doesn't compute
    # quote_count).
    quote_count: int | None = None
    total_quote_value: float | None = None
    pinned: bool | None = None

    model_config = {"from_attributes": True}


# ──────────────────────────────────────────────────────────────────
# Round-15 typing pass — schemas for the remaining JSON endpoints in
# ``api/v1/customers.py`` that previously returned bare ``dict``.
# Each schema is extras-tolerant where the handler emits enrichments
# the contract doesn't try to lock down.
# ──────────────────────────────────────────────────────────────────


class CustomerPinResponse(BaseModel):
    """POST/DELETE /customers/{id}/pin — pinned-state ack."""

    pinned: bool
    customer_id: int

    model_config = {"from_attributes": True}


class CustomerIntelligenceOpportunity(BaseModel):
    id: int
    title: str | None = None
    stage: str | None = None
    amount: float | None = None
    currency: str | None = None
    owner_id: int | None = None
    close_date: str | None = None
    updated_at: str | None = None
    last_activity_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class CustomerIntelligenceSignal(BaseModel):
    id: int
    opportunity_id: int | None = None
    signal_type: str | None = None
    severity: str | None = None
    evidence: str | None = None
    source_type: str | None = None
    source_id: int | None = None
    is_resolved: bool | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class CustomerIntelligenceResponse(BaseModel):
    """GET /customers/{id}/intelligence — operational rollup."""

    customer: CustomerResponse
    opportunities: list[CustomerIntelligenceOpportunity]
    open_tasks_count: int
    signals: list[CustomerIntelligenceSignal]

    model_config = {"from_attributes": True}


class CustomerEnrichResponse(BaseModel):
    """POST /customers/{id}/enrich — wraps service payload in ``data``."""

    data: dict[str, object] | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class CustomerDeleteResponse(BaseModel):
    """DELETE /customers/{id} — single-line ack."""

    message: str

    model_config = {"from_attributes": True}


class CustomerImportResponse(BaseModel):
    """POST /customers/import — bulk import summary."""

    message: str
    imported: int
    skipped: int
    errors: list[str | dict[str, object]] = []

    model_config = {"from_attributes": True}


class CustomerTimelineEvent(BaseModel):
    type: str
    id: int
    title: str | None = None
    detail: str | None = None
    status: str | None = None
    timestamp: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class CustomerTimelineResponse(BaseModel):
    """GET /customers/{id}/timeline — chronological events."""

    customer_id: int
    events: list[CustomerTimelineEvent]

    model_config = {"from_attributes": True}


class CustomerActivity(BaseModel):
    id: int
    activity_type: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    summary: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class CustomerActivityTimelineResponse(BaseModel):
    """GET /customers/{id}/activity-timeline — unified activity feed."""

    customer_id: int
    activities: list[CustomerActivity]

    model_config = {"from_attributes": True}


class CustomerBulkActionResponse(BaseModel):
    """POST /customers/bulk-action — applies to delete/assign/export."""

    message: str
    affected_count: int | None = None
    # Only populated by the ``export`` action.
    data: list[dict[str, object]] | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class CustomerHierarchyNode(BaseModel):
    id: int
    name: str | None = None
    company: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class CustomerHierarchyResponse(BaseModel):
    """GET /customers/{id}/hierarchy — parents + subsidiaries."""

    customer_id: int
    parents: list[CustomerHierarchyNode]
    subsidiaries: list[CustomerHierarchyNode]

    model_config = {"from_attributes": True}


class CustomerParentResponse(BaseModel):
    """PATCH /customers/{id}/parent — reparent ack."""

    status: str
    parent_id: int | None = None

    model_config = {"from_attributes": True}


class CustomerRollupResponse(BaseModel):
    """GET /customers/{id}/rollup — aggregate metrics across subsidiaries."""

    customer_id: int
    subsidiary_count: int
    total_opportunities: int
    total_opportunity_value: float
    total_quotes: int
    total_quote_value: float

    model_config = {"from_attributes": True}


class HighIntentAccountResponse(BaseModel):
    """Wire shape for ``GET /api/v1/customers/high-intent``.

    Round-15 N15-API-1 quick-win 5 — pre-Round-15 the endpoint was typed
    as ``PaginatedResponse[dict]`` even though ``ProspectingAgent`` already
    emits this exact 6-field shape (``customers.py:115-125``). The schema
    closes that contract gap without changing the wire payload.
    """

    customer_id: int
    name: str | None = None
    company: str | None = None
    score: float
    # ``signals`` is a free-form list of human-readable badges
    # (e.g. ``["3 quotes in 7 days", "Pinned"]``). Typed as
    # ``list[str]`` so the SPA can render badges directly.
    signals: list[str] = []
    pinned: bool = False

    model_config = {"from_attributes": True}
