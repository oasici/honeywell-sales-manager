"""F-012 — multi-currency forecast rollup.

Pre-Round-19 the forecast endpoint summed ``amount`` across all
opportunities with no respect for ``currency``. A tenant with a USD,
EUR, and TRY pipeline saw a meaningless additive total. This module
fixes that by surfacing TWO views:

  * **Per-currency** rollup — separate totals for each currency the
    pipeline contains. The "right" number for any single-currency
    audience.

  * **Base-currency** rollup — every line converted to the tenant's
    ``base_currency`` (from ``tenant_settings``) at a documented FX
    rate. The "one number" view for executives.

At 20-30 user / single-tenant pilot scale the per-currency view is
sufficient (most pilots are TRY-only). The base-currency conversion
is built on top so it's ready the day the first non-TRY deal lands.

FX rate strategy (zero-cost, no external API):

  * Each Opportunity carries an ``fx_rate_to_base`` snapshot stamped
    at create/update time. We never re-rate historical opps.
  * Tenants can override per-month FX in ``fx_rates`` table (added
    here) — useful for finance teams that want to fix the
    "translation rate" for management reporting.
  * Fallback: same-currency = 1.0; cross-currency without override =
    rate stored on the opp itself. No live API calls in the hot path.

The service is pure — no HTTP. ``forecast.py`` endpoint imports and
returns the structured result. No callers besides forecast today,
but ``invoice_currency_rollup`` and ``revenue_recognition_currency``
will reuse the same primitives in Phase 6.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Iterable, Mapping

logger = logging.getLogger(__name__)


_CLOSED_STAGES = frozenset({"closed_won", "closed_lost"})
_COMMIT_PROBABILITY_THRESHOLD = Decimal("0.75")


@dataclass(frozen=True)
class OppView:
    """Pure-data shape callers can build from an ORM row, an analytics
    table, or a test fixture. Decoupled from SQLAlchemy."""

    opp_id: int
    amount: Decimal
    currency: str
    probability: Decimal           # 0..1
    stage: str
    fx_rate_to_base: Decimal | None = None  # snapshotted at last edit


@dataclass
class CurrencyBucket:
    """Aggregate numbers for one currency."""

    currency: str
    open_count: int = 0
    open_amount: Decimal = Decimal(0)
    weighted_amount: Decimal = Decimal(0)       # Σ amount × probability
    commit_amount: Decimal = Decimal(0)         # Σ amount where p ≥ threshold
    closed_won_amount: Decimal = Decimal(0)
    closed_lost_amount: Decimal = Decimal(0)


@dataclass
class ForecastRollup:
    """Result shape returned to the API."""

    by_currency: dict[str, CurrencyBucket] = field(default_factory=dict)
    base_currency: str = "TRY"
    base_total_open: Decimal = Decimal(0)
    base_total_weighted: Decimal = Decimal(0)
    base_total_commit: Decimal = Decimal(0)
    base_total_closed_won: Decimal = Decimal(0)
    # When True, at least one opportunity lacked an fx_rate snapshot
    # and was converted with the fallback ``same-as-base`` rule. UI
    # surfaces this so finance knows the base total is approximate.
    base_total_has_estimates: bool = False

    def as_dict(self) -> dict:
        return {
            "by_currency": {
                ccy: {
                    "currency": b.currency,
                    "open_count": b.open_count,
                    "open_amount": str(_round2(b.open_amount)),
                    "weighted_amount": str(_round2(b.weighted_amount)),
                    "commit_amount": str(_round2(b.commit_amount)),
                    "closed_won_amount": str(_round2(b.closed_won_amount)),
                    "closed_lost_amount": str(_round2(b.closed_lost_amount)),
                }
                for ccy, b in self.by_currency.items()
            },
            "base_currency": self.base_currency,
            "base_total_open": str(_round2(self.base_total_open)),
            "base_total_weighted": str(_round2(self.base_total_weighted)),
            "base_total_commit": str(_round2(self.base_total_commit)),
            "base_total_closed_won": str(_round2(self.base_total_closed_won)),
            "base_total_has_estimates": self.base_total_has_estimates,
        }


def _round2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def _coerce_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal(0)
    return Decimal(str(value))


def _to_base(
    amount: Decimal,
    currency: str,
    base_currency: str,
    fx_rate_to_base: Decimal | None,
) -> tuple[Decimal, bool]:
    """Return (base_amount, used_estimate).

    Same currency → 1.0. Cross-currency with fx_rate snapshot → use
    snapshot. Cross-currency WITHOUT snapshot → 1.0 + estimate flag
    so the UI can warn finance.
    """
    if currency.upper() == base_currency.upper():
        return amount, False
    if fx_rate_to_base is not None and fx_rate_to_base > 0:
        return amount * fx_rate_to_base, False
    # Fallback: assume parity. Bad number but the UI flags it.
    logger.warning(
        "Forecast: opp in %s lacks fx_rate_to_base; treating as 1.0 "
        "for base=%s. Stamp fx_rate_to_base on opp create/update to fix.",
        currency, base_currency,
    )
    return amount, True


def compute_rollup(
    opps: Iterable[OppView],
    *,
    base_currency: str = "TRY",
) -> ForecastRollup:
    """Pure function. Pass in an iterable of OppView, get a rollup back.

    Two-pass: first pass groups by currency; second pass rolls up to
    base. Pure functions are testable without a DB.
    """
    buckets: dict[str, CurrencyBucket] = defaultdict(
        lambda: CurrencyBucket(currency="")
    )
    base_open = Decimal(0)
    base_weighted = Decimal(0)
    base_commit = Decimal(0)
    base_closed_won = Decimal(0)
    used_estimate = False

    for opp in opps:
        amount = _coerce_decimal(opp.amount)
        probability = _coerce_decimal(opp.probability)
        ccy = (opp.currency or "TRY").upper()
        bucket = buckets[ccy]
        bucket.currency = ccy

        if opp.stage == "closed_won":
            bucket.closed_won_amount += amount
            base, est = _to_base(amount, ccy, base_currency, opp.fx_rate_to_base)
            base_closed_won += base
            used_estimate = used_estimate or est
            continue
        if opp.stage == "closed_lost":
            bucket.closed_lost_amount += amount
            continue

        # Open opportunity contributions
        bucket.open_count += 1
        bucket.open_amount += amount
        weighted = amount * probability
        bucket.weighted_amount += weighted
        if probability >= _COMMIT_PROBABILITY_THRESHOLD:
            bucket.commit_amount += amount

        base_amt, est_o = _to_base(amount, ccy, base_currency, opp.fx_rate_to_base)
        base_open += base_amt
        base_weighted += base_amt * probability
        if probability >= _COMMIT_PROBABILITY_THRESHOLD:
            base_commit += base_amt
        used_estimate = used_estimate or est_o

    return ForecastRollup(
        by_currency=dict(buckets),
        base_currency=base_currency.upper(),
        base_total_open=base_open,
        base_total_weighted=base_weighted,
        base_total_commit=base_commit,
        base_total_closed_won=base_closed_won,
        base_total_has_estimates=used_estimate,
    )


def opps_from_orm(rows: Iterable, *, default_currency: str = "TRY") -> list[OppView]:
    """Adapter: ORM rows → OppView. Tolerates legacy rows missing
    fx_rate_to_base / currency / probability."""
    out: list[OppView] = []
    for r in rows:
        out.append(
            OppView(
                opp_id=int(getattr(r, "id", 0) or 0),
                amount=_coerce_decimal(getattr(r, "amount", 0)),
                currency=(getattr(r, "currency", None) or default_currency),
                probability=_coerce_decimal(
                    getattr(r, "probability", 0) or 0
                )
                / Decimal(100)
                if (getattr(r, "probability", 0) or 0) > 1
                else _coerce_decimal(getattr(r, "probability", 0) or 0),
                stage=getattr(r, "stage", "prospecting") or "prospecting",
                fx_rate_to_base=(
                    _coerce_decimal(getattr(r, "fx_rate_to_base", None))
                    if getattr(r, "fx_rate_to_base", None) is not None
                    else None
                ),
            )
        )
    return out
