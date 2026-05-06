from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


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


class CustomerResponse(BaseModel):
    """Customer response surface.

    R6-API-9 — pre-R6 the canonical ``_customer_to_dict`` emitted 17
    fields while the schema declared 7, leaving 11 fields invisible to
    OpenAPI / SDK codegen consumers. Mirrors R5-FORM-3/4 which widened
    the input side; this brings the output side back in sync.
    """

    id: int
    # R6-API-9 — round-trip tenant_id, mirroring R4-CLOSE-1 for
    # opportunity/quote/etc.
    tenant_id: int | None = None
    name: str
    company: str | None = None
    email: str
    phone: str | None = None
    address: str | None = None
    tax_id: str | None = None
    preferred_lang: str
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime

    quote_count: int | None = None
    total_quote_value: float | None = None

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

    model_config = {"from_attributes": True}
