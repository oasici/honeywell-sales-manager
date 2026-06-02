"""Phase-1 pricing-correctness tests (spare-parts extraction audit P1).

Invariants encoded here are the ones the pre-fix code violated:
  * a customer quote is NEVER priced at cost
  * the customer price list (``PriceEntry.net_price``) wins over cost fields
  * when only cost is known, ``min_margin_pct`` is applied (and a 0% margin
    refuses to auto-price rather than quoting at cost)
  * price selection is currency-consistent with the quote
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from app.services.part_pricing import (
    PRICE_SOURCE_COST_MARGIN,
    PRICE_SOURCE_LIST,
    PRICE_SOURCE_UNPRICED,
    resolve_unit_price,
    select_price_entry,
)

TODAY = date(2026, 6, 1)


def _price(net, *, currency="TRY", list_price=None, valid_from=None, valid_until=None, id=1):
    return SimpleNamespace(
        id=id,
        net_price=net,
        list_price=list_price if list_price is not None else net,
        currency=currency,
        valid_from=valid_from,
        valid_until=valid_until,
    )


def _part(*, prices=None, transfer_price=None, supplier_price=None, min_margin_pct=0.0):
    return SimpleNamespace(
        prices=prices or [],
        transfer_price=transfer_price,
        supplier_price=supplier_price,
        min_margin_pct=min_margin_pct,
    )


class TestNeverQuoteAtCost:
    def test_cost_only_zero_margin_is_unpriced_not_at_cost(self):
        part = _part(transfer_price=100.0, supplier_price=80.0, min_margin_pct=0.0)
        price, source = resolve_unit_price(part, today=TODAY)
        assert source == PRICE_SOURCE_UNPRICED
        assert price == 0.0  # never the 100.0 transfer (cost) price

    def test_cost_only_with_margin_is_above_cost(self):
        part = _part(transfer_price=100.0, min_margin_pct=25.0)
        price, source = resolve_unit_price(part, today=TODAY)
        assert source == PRICE_SOURCE_COST_MARGIN
        assert price == 125.0
        assert price > 100.0


class TestPriceListPrecedence:
    def test_price_list_wins_over_cost_fields(self):
        part = _part(
            prices=[_price(250.0)],
            transfer_price=100.0,
            supplier_price=80.0,
            min_margin_pct=50.0,
        )
        price, source = resolve_unit_price(part, today=TODAY)
        assert source == PRICE_SOURCE_LIST
        assert price == 250.0  # not 100 (cost) and not 150 (cost+margin)

    def test_zero_net_price_falls_through_to_cost_margin(self):
        part = _part(prices=[_price(0.0)], transfer_price=100.0, min_margin_pct=10.0)
        price, source = resolve_unit_price(part, today=TODAY)
        assert source == PRICE_SOURCE_COST_MARGIN
        assert price == 110.0


class TestCurrencyConsistency:
    def test_prefers_entry_matching_quote_currency(self):
        part = _part(
            prices=[
                _price(300.0, currency="USD", id=1),
                _price(250.0, currency="TRY", id=2),
            ]
        )
        price, source = resolve_unit_price(part, preferred_currency="TRY", today=TODAY)
        assert source == PRICE_SOURCE_LIST
        assert price == 250.0

    def test_picks_newest_valid_entry(self):
        part = _part(
            prices=[
                _price(100.0, valid_from=date(2025, 1, 1), id=1),
                _price(200.0, valid_from=date(2026, 1, 1), id=2),
            ]
        )
        entry = select_price_entry(part, today=TODAY)
        assert entry.net_price == 200.0

    def test_expired_entries_skipped_when_a_valid_one_exists(self):
        part = _part(
            prices=[
                _price(999.0, valid_until=date(2025, 1, 1), id=1),  # expired
                _price(200.0, valid_from=date(2026, 1, 1), id=2),  # current
            ]
        )
        price, source = resolve_unit_price(part, today=TODAY)
        assert price == 200.0


class TestNoData:
    def test_no_price_no_cost_is_unpriced(self):
        part = _part()
        price, source = resolve_unit_price(part, today=TODAY)
        assert source == PRICE_SOURCE_UNPRICED
        assert price == 0.0
