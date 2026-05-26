"""F-029 / future Phase 4 — per-tenant typed configuration.

Single row per tenant. Each column is a *narrow, typed* setting —
deliberately not a key-value store, because the eligibility gate
and forecast engine want to fail-loud at startup if a column is
missing, not silently get ``None`` from a string lookup.

Adding a new setting:
  1. Add column here.
  2. Add idempotent ALTER in a new migration.
  3. Backfill default in the migration ``UPDATE`` step.

Callers should use :func:`get_tenant_settings` (in
``app/services/tenant_settings_service.py``) instead of querying
this table directly — the service handles the "row may not exist
yet for legacy tenants" case by returning a defaults-only object.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TenantSettings(Base):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    # F-029 — auto-quote eligibility gate caps each draft at this
    # amount (across all line items, in this currency). NULL = no
    # cap (current behaviour for legacy tenants).
    auto_quote_max_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    auto_quote_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="TRY"
    )
    # Future-Phase placeholders so callers can read these without
    # null-checking once Phase 4 lands the forecast multi-currency
    # work (F-012) and AI cost guardrails.
    base_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="TRY"
    )
    ocr_max_pages: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5
    )
    ai_monthly_quota_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
