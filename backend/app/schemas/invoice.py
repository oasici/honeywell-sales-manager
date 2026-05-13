"""Invoice response schema.

Round-13 Sprint 6b — Pydantic surface for the invoice list / detail /
create / update endpoints. The serialiser (``_invoice_to_dict``) emits
computed extras (e.g. customer summary join, days_overdue), so the
schema is extras-tolerant via ``extra='allow'``, matching the pattern
established for CustomerResponse / QuoteResponse / OpportunityResponse
in R10-API-6.

Every field is nullable because:
  1. Pre-bootstrap rows can carry NULL on timestamps / amounts.
  2. ``apply_request_perms`` may strip or mask fields based on the
     caller's permission tier.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class InvoiceResponse(BaseModel):
    id: int
    tenant_id: int | None = None
    invoice_number: str | None = None
    quote_id: int | None = None
    contract_id: int | None = None
    customer_id: int | None = None
    created_by: int | None = None
    issue_date: datetime | None = None
    due_date: datetime | None = None
    status: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax_rate: float | None = None
    tax_amount: float | None = None
    grand_total: float | None = None
    items_json: str | None = None
    notes: str | None = None
    pdf_path: str | None = None
    paid_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
