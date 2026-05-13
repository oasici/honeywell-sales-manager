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

    model_config = {"from_attributes": True, "extra": "allow"}
