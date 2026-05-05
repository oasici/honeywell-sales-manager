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
    id: int
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

    model_config = {"from_attributes": True}
