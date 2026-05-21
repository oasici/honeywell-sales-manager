"""Lead response schema.

Round-13 follow-up to Sprint 6a — Lead was deferred when there was no
``app/schemas/lead.py``. This module adds the per-item Pydantic schema
matching the pattern established for ``CustomerResponse`` /
``QuoteResponse`` / ``OpportunityResponse`` in R10-API-6:

  1. ``extra='allow'`` — the existing serializers attach computed
     extras (``owner_summary``, ``converted_customer_summary``, etc.)
     that should still round-trip.
  2. Every field nullable — supports both pre-bootstrap rows and
     field-permission masking via ``apply_request_perms``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LeadResponse(BaseModel):
    id: int
    tenant_id: int | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    source: str | None = None
    status: str | None = None
    lead_score: int | None = None
    owner_id: int | None = None
    converted_customer_id: int | None = None
    converted_opportunity_id: int | None = None
    converted_at: datetime | None = None
    converted_by: int | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Sprint 16g (Round-15) — computed fields the SPA's manual ``Lead``
    # interface in lib/types.ts has read for months but OpenAPI didn't
    # document. Declaring here unblocks the api-types.gen.ts migration
    # (audit N15-ARCH-1 pre-step). ``full_name`` is a server-computed
    # concatenation; ``owner_name`` resolves the owner_id FK.
    full_name: str | None = None
    owner_name: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class LeadStrictResponse(BaseModel):
    """C5 canary — Round-16 (N15-API-3 RFC Option A).

    Strong-contract variant of ``LeadResponse`` for routes where
    field-permission masking is NOT active. Per the RFC at
    ``docs/decisions/2026-05-21-polymorphic-response-schemas.md``,
    this is the third per-entity rollout after C3 (Customer) and
    C4 (Opportunity).

    NOT-NULL fields (per ORM ``Mapped[int]`` declarations):
      id, tenant_id, first_name, last_name, email, owner_id,
      created_at, updated_at.

    ``extra="allow"`` mirrors the masked variant so per-route
    enrichments (``score_breakdown`` on detail view, ``full_name``,
    ``owner_name``) round-trip through the strict-shape validator
    unchanged.
    """

    id: int
    tenant_id: int
    first_name: str
    last_name: str
    email: str
    owner_id: int
    created_at: datetime
    updated_at: datetime

    # Truly nullable on the ORM
    phone: str | None = None
    company: str | None = None
    title: str | None = None
    source: str | None = None
    status: str | None = None
    lead_score: int | None = None
    converted_customer_id: int | None = None
    converted_opportunity_id: int | None = None
    converted_at: datetime | None = None
    converted_by: int | None = None
    notes: str | None = None

    # Computed / joined extras
    full_name: str | None = None
    owner_name: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
