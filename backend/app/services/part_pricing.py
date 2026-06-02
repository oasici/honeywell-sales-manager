"""Sell-price resolution for spare parts (Phase-1 pricing correctness).

Zero-tolerance rule for the email → quote pipeline: a customer quote must
**never** be priced at cost. The authoritative sell price is the customer
price list (``PriceEntry.net_price``). Only when no price-list entry is
available do we derive a price from cost — and then only by applying the
part's ``min_margin_pct``; if that still doesn't clear cost we refuse to
auto-price and leave the line unpriced for human review.

Precedence (was inverted pre-Phase-1 — the line item was quoted at
``transfer_price`` / ``supplier_price``, i.e. at *cost*, with the price
list used only as a last resort and ``min_margin_pct`` never read):

  1. ``price_list``       — newest valid, currency-consistent ``PriceEntry``
  2. ``cost_plus_margin`` — ``cost * (1 + min_margin_pct/100)`` when > cost
  3. ``unpriced``         — 0.0; the caller must route the line to review

The functions are deliberately duck-typed (``getattr``) so they work
against both ORM rows and lightweight test stand-ins.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

PRICE_SOURCE_LIST = "price_list"
PRICE_SOURCE_COST_MARGIN = "cost_plus_margin"
PRICE_SOURCE_UNPRICED = "unpriced"


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _is_valid(entry: Any, today: date) -> bool:
    """A price entry is valid when today falls within its (optional) window."""
    valid_from = getattr(entry, "valid_from", None)
    valid_until = getattr(entry, "valid_until", None)
    if valid_from is not None and valid_from > today:
        return False
    if valid_until is not None and valid_until < today:
        return False
    return True


def select_price_entry(
    part: Any,
    *,
    preferred_currency: str | None = None,
    today: date | None = None,
) -> Any | None:
    """Pick the authoritative ``PriceEntry`` for a part.

    Filters to currently-valid entries (falling back to all entries when
    none are in-window so a quote isn't blocked purely on stale dates),
    prefers the quote's currency, and breaks ties by recency
    (``valid_from`` then ``id``) so selection is deterministic.
    """
    entries = list(getattr(part, "prices", None) or [])
    if not entries:
        return None

    today = today or _today()
    # T4 — only entries whose validity window includes today are usable.
    # Entries with no dates are open-ended (always valid). If EVERY entry
    # is explicitly expired or future-dated, we return None → the line is
    # left unpriced for review rather than quoting an out-of-window price.
    valid = [e for e in entries if _is_valid(e, today)]
    if not valid:
        return None

    if preferred_currency:
        pref = preferred_currency.upper()
        matched = [
            e for e in valid if (getattr(e, "currency", None) or "").upper() == pref
        ]
        if matched:
            valid = matched

    def _sort_key(entry: Any) -> tuple:
        valid_from = getattr(entry, "valid_from", None) or date.min
        return (valid_from, getattr(entry, "id", 0) or 0)

    valid.sort(key=_sort_key, reverse=True)
    return valid[0]


def resolve_unit_price_with_currency(
    part: Any,
    *,
    preferred_currency: str | None = None,
    today: date | None = None,
) -> tuple[float, str, str | None]:
    """Resolve a unit price plus the currency it is denominated in.

    Returns ``(unit_price, price_source, currency)``. ``currency`` is the
    source currency of the chosen price (``PriceEntry.currency`` for a
    price-list hit, ``SparePart.price_currency`` for cost+margin, ``None``
    when unpriced). The caller (R4) converts this into the quote currency
    rather than silently treating, say, a USD ``net_price`` as TRY.
    """
    entry = select_price_entry(
        part, preferred_currency=preferred_currency, today=today
    )
    if entry is not None:
        net = getattr(entry, "net_price", None)
        if net is not None and float(net) > 0:
            return (
                round(float(net), 2),
                PRICE_SOURCE_LIST,
                getattr(entry, "currency", None) or None,
            )

    cost = getattr(part, "transfer_price", None) or getattr(part, "supplier_price", None)
    if cost is not None and float(cost) > 0:
        margin_pct = float(getattr(part, "min_margin_pct", 0.0) or 0.0)
        sell = float(cost) * (1.0 + margin_pct / 100.0)
        # Strictly greater than cost — a 0% (or missing) margin must not
        # let the part be quoted at cost.
        if sell > float(cost):
            return (
                round(sell, 2),
                PRICE_SOURCE_COST_MARGIN,
                getattr(part, "price_currency", None) or None,
            )

    return 0.0, PRICE_SOURCE_UNPRICED, None


def resolve_unit_price(
    part: Any,
    *,
    preferred_currency: str | None = None,
    today: date | None = None,
) -> tuple[float, str]:
    """Resolve a customer-facing unit price for a spare part.

    Returns ``(unit_price, price_source)`` where ``price_source`` is one
    of :data:`PRICE_SOURCE_LIST`, :data:`PRICE_SOURCE_COST_MARGIN`, or
    :data:`PRICE_SOURCE_UNPRICED`. An ``unpriced`` result (``0.0``) means
    the caller must NOT auto-confirm the line — there is no safe price.

    Currency-agnostic convenience wrapper around
    :func:`resolve_unit_price_with_currency` for callers that don't need
    to reconcile currency (e.g. the best-effort gate estimate).
    """
    price, source, _currency = resolve_unit_price_with_currency(
        part, preferred_currency=preferred_currency, today=today
    )
    return price, source
