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
    # Sprint 16g (Round-15) — computed fields that the SPA's manual
    # ``Opportunity`` interface in lib/types.ts has read for months but
    # the OpenAPI contract didn't document. Declaring them here lets the
    # generated api-types.gen.ts replace the hand-written shape (audit
    # N15-ARCH-1 pre-step). All are populated by ``_opp_to_dict`` /
    # ``_board_opp_to_dict`` extras and pass through ``extra=allow``.
    last_activity_at: datetime | None = None
    open_tasks_count: int | None = None
    open_quotes_count: int | None = None
    customer: _CustomerSummary | None = None
    owner: _OwnerSummary | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    quotes: list[_QuoteSummary] = []

    model_config = {"from_attributes": True, "extra": "allow"}


class OpportunityStrictResponse(BaseModel):
    """C4 canary — Round-16 (N15-API-3 RFC Option A).

    Strong-contract variant of ``OpportunityResponse`` for routes
    where field-permission masking is NOT active. Every NOT-NULL
    column on the Opportunity ORM is declared Required; only
    genuinely nullable columns stay Optional.

    Per the RFC at ``docs/decisions/2026-05-21-polymorphic-response-schemas.md``,
    this is the second per-entity rollout after C3 (Customer). Routes
    opt in via the picker at
    ``backend/app/services/response_model_picker.py``; if any
    field-permission rule is active for ``opportunity`` on the
    current request, the picker falls back to ``OpportunityResponse``
    so masking behaviour is preserved.

    NOT-NULL fields (per ORM ``Mapped[int]`` declarations):
      id, tenant_id, title, stage, owner_id, created_at, updated_at.

    ``extra="allow"`` mirrors the masked variant so per-route
    enrichments (``open_quotes_count`` on GET single, ``customer`` /
    ``owner`` joins) round-trip through the strict-shape validator
    unchanged.
    """

    id: int
    tenant_id: int
    title: str
    stage: str
    owner_id: int
    created_at: datetime
    updated_at: datetime

    # Truly nullable on the ORM
    amount: float | None = None
    currency: str | None = None
    close_date: date | str | None = None
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

    # Computed / joined extras — Optional because they're not always
    # populated (list view vs detail view).
    last_activity_at: datetime | None = None
    open_tasks_count: int | None = None
    open_quotes_count: int | None = None
    customer: _CustomerSummary | None = None
    owner: _OwnerSummary | None = None
    quotes: list[_QuoteSummary] = []

    model_config = {"from_attributes": True, "extra": "allow"}
