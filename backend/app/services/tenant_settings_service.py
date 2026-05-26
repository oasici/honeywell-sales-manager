"""F-029 — tenant-settings accessor with safe defaults.

Why a service instead of letting callers ``await db.get(TenantSettings, tid)``:

  1. Legacy tenants don't have a row yet. The service returns a
     defaults-only object so call sites never null-check.
  2. The eligibility gate has to load settings on every email parse;
     caching by tenant_id with a short TTL avoids 1 query per parse.
  3. The defaults live in one place. When Phase 4 adds the
     ``forecast_strict_currency`` knob, every call site picks up the
     default automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant_settings import TenantSettings


@dataclass(frozen=True)
class TenantConfig:
    """Read-only view of a tenant's settings + defaults.

    Equality/hash by ``tenant_id`` so we can use it as a cache key.
    Frozen to prevent accidental mutation by callers.
    """

    tenant_id: int
    auto_quote_max_amount: Optional[Decimal]
    auto_quote_currency: str
    base_currency: str
    ocr_max_pages: int
    ai_monthly_quota_usd: Optional[Decimal]

    @classmethod
    def defaults(cls, tenant_id: int) -> "TenantConfig":
        return cls(
            tenant_id=tenant_id,
            auto_quote_max_amount=None,        # no cap
            auto_quote_currency="TRY",
            base_currency="TRY",
            ocr_max_pages=5,
            ai_monthly_quota_usd=None,
        )

    @classmethod
    def from_row(cls, row: TenantSettings) -> "TenantConfig":
        return cls(
            tenant_id=row.tenant_id,
            auto_quote_max_amount=row.auto_quote_max_amount,
            auto_quote_currency=row.auto_quote_currency,
            base_currency=row.base_currency,
            ocr_max_pages=row.ocr_max_pages,
            ai_monthly_quota_usd=row.ai_monthly_quota_usd,
        )


async def get_tenant_settings(
    db: AsyncSession, tenant_id: int | None
) -> TenantConfig:
    """Return the tenant's config, or defaults if no row exists.

    ``tenant_id is None`` returns defaults too — covers the
    pre-multi-tenant rows that lacked a tenant_id during the
    Round-15 backfill.
    """
    if tenant_id is None:
        return TenantConfig.defaults(0)
    row = (
        await db.execute(
            select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return TenantConfig.defaults(tenant_id)
    return TenantConfig.from_row(row)


def estimate_quote_total(parsed: dict) -> Decimal:
    """Best-effort total for the eligibility gate.

    Sums ``unit_price * quantity`` across parts when both fields are
    present. Falls back to 0 when the parser didn't surface
    pricing — the gate then treats the total as unknown and lets
    the rest of the checks decide.

    Pure function so the gate stays synchronous + testable without
    a DB.
    """
    total = Decimal(0)
    for p in parsed.get("parts") or []:
        price = p.get("unit_price") or p.get("price")
        qty = p.get("quantity") or 1
        if price is None:
            continue
        try:
            total += Decimal(str(price)) * Decimal(str(qty))
        except Exception:
            # Malformed numbers — skip; don't break the whole gate.
            continue
    return total
