"""F-027 — pricing precedence resolver.

Multiple price sources compete for each quote line:

  1. Active campaign promo (customer ∈ promo segment, within dates)
  2. Customer-specific contract price (active contract on the part)
  3. Customer tier price (Platinum/Gold/Silver/Bronze)
  4. Catalog list price (the part's default)

Without an explicit precedence the codebase was picking inconsistently
(sometimes catalog, sometimes tier). This module makes the rule
explicit + auditable: every resolved price carries a ``source`` tag
that the UI/PDF/report can render ("$X — Platinum tier discount").

The resolver is pure: takes pre-fetched candidate prices and returns
the winner. Fetching live data is the caller's job — keeps this
testable without a DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional


# Stable enum-style strings. Stored on ``quote_items.price_source``.
SRC_CAMPAIGN = "campaign_promo"
SRC_CONTRACT = "customer_contract"
SRC_TIER = "customer_tier"
SRC_CATALOG = "catalog"

_PRECEDENCE = (SRC_CAMPAIGN, SRC_CONTRACT, SRC_TIER, SRC_CATALOG)


@dataclass(frozen=True)
class PriceCandidate:
    """One eligible price for a part, with provenance."""

    amount: Decimal
    currency: str
    source: str             # one of SRC_*
    ref: Optional[str] = None  # campaign_id / contract_id / tier name


@dataclass(frozen=True)
class ResolvedPrice:
    """Winner of the precedence resolution."""

    amount: Decimal
    currency: str
    source: str
    ref: Optional[str]


class PricingResolutionError(Exception):
    """Raised when no candidate is available."""


def resolve_price(candidates: Iterable[PriceCandidate]) -> ResolvedPrice:
    """Pick the highest-precedence candidate.

    A candidate is only valid if ``amount > 0``. A zero-priced
    candidate is ignored (catalog defaults of 0 are usually
    "unconfigured", not "free"). Raises
    :class:`PricingResolutionError` when no candidate qualifies.

    Stable: among equal-precedence candidates, the first one in
    iteration order wins. Pure: no I/O.
    """
    by_source: dict[str, PriceCandidate] = {}
    for c in candidates:
        if c.amount is None or c.amount <= 0:
            continue
        # Keep first occurrence of each source so callers can supply
        # multiple "candidate" rows without surprises.
        by_source.setdefault(c.source, c)

    for src in _PRECEDENCE:
        if src in by_source:
            c = by_source[src]
            return ResolvedPrice(
                amount=c.amount,
                currency=c.currency,
                source=c.source,
                ref=c.ref,
            )

    raise PricingResolutionError("No valid price candidate available")


def precedence_index(source: str) -> int:
    """Position of ``source`` in the precedence list (0 = highest).

    Returns a high sentinel for unknown sources so they sort last.
    Used by reports that "explain" a quote line's chosen price.
    """
    try:
        return _PRECEDENCE.index(source)
    except ValueError:
        return 99
