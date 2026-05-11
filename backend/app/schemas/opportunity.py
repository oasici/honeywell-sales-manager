"""Opportunity schema surfaces — Round-10 R10-API-6.

Mirrors the existing ``_opp_to_dict`` serializer in
``app.api.v1.opportunities``. Used as the per-item type on
``PaginatedResponse[OpportunityResponse]`` for the /opportunities/
list endpoint.

Same four realities as CustomerResponse / QuoteResponse:

  1. ``apply_request_perms`` can strip any field (``hidden`` rule).
  2. ``apply_request_perms`` can mask any field to ``"***"``.
  3. Callers add caller-specific extras (e.g. ``last_activity_at`` is
     injected by the intelligence endpoint).
  4. Legacy rows may have NULL on otherwise-required columns.

The schema is therefore extras-tolerant (``extra='allow'``) and every
field is nullable.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class _CustomerSummary(BaseModel):
    """Tiny embedded customer used in opportunity responses."""

    id: int | None = None
    name: str | None = None
    company: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class _OwnerSummary(BaseModel):
    """Tiny embedded owner used in opportunity responses."""

    id: int | None = None
    full_name: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class _QuoteSummary(BaseModel):
    """Tiny embedded quote used when ``include_quotes=True``."""

    id: int | None = None
    quote_number: str | None = None
    status: str | None = None
    grand_total: float | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class OpportunityResponse(BaseModel):
    """Opportunity list-item response.

    Mirrors ``_opp_to_dict`` in app/api/v1/opportunities.py exactly so
    the FastAPI response_model validator passes every existing
    serializer output unchanged.
    """

    id: int
    tenant_id: int | None = None
    title: str | None = None
    stage: str | None = None
    amount: float | None = None
    currency: str | None = None
    close_date: date | str | None = None
    owner_id: int | None = None
    customer_id: int | None = None
    status: str | None = None
    probability: float | None = None
    loss_reason: str | None = None
    forecast_category: str | None = None
    pipeline_id: int | None = None
    territory_id: int | None = None
    previous_stage: str | None = None
    previous_close_date: date | str | None = None
    previous_amount: float | None = None
    source: str | None = None
    rotting_days: int | None = None
    customer: _CustomerSummary | None = None
    owner: _OwnerSummary | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    quotes: list[_QuoteSummary] = []

    model_config = {"from_attributes": True, "extra": "allow"}
