"""Re-audit remediation tests (2026-06-02 spare-parts re-audit R1–R5).

R1 — quantity uncertainty (conflict/suspect) blocks auto-quote AND leaves
     the quote line unconfirmed.
R2 — the auto-quote value cap fires once catalog prices are stamped.
R3 — the per-call input cap trims thread history, never the current email.
R4 — a catalog price in another currency is converted, not silently used;
     conversion failure leaves the line unpriced.
R5 — quote money math accumulates in Decimal (no float cent drift).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.email_processing_service import (
    _auto_quote_eligible,
    _bound_llm_input,
)
from app.services.part_pricing import (
    PRICE_SOURCE_LIST,
    resolve_unit_price_with_currency,
)
from app.services.quote_service import QuoteService


# ── shared fakes ──────────────────────────────────────────────────
def _email(**over):
    base = dict(
        parse_skipped_reason=None,
        sender_auth_status="pass",
        attachment_pages_truncated=False,
        first_time_sender=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _price(net, *, currency="TRY", id=1):
    return SimpleNamespace(
        id=id, net_price=net, list_price=net, currency=currency,
        valid_from=None, valid_until=None,
    )


def _part(part_id=1, code="C7061A1012", *, net_price=None, currency="TRY",
          transfer_price=None, price_currency=None, min_margin_pct=0.0):
    prices = [_price(net_price, currency=currency)] if net_price is not None else []
    return SimpleNamespace(
        id=part_id, honeywell_code=code, name_en="Flame detector", name_tr="Alev",
        prices=prices, transfer_price=transfer_price, supplier_price=None,
        price_currency=price_currency, min_margin_pct=min_margin_pct,
    )


# ── R1 ────────────────────────────────────────────────────────────
class TestR1QuantityUncertainty:
    def test_conflict_blocks_auto_quote(self):
        parsed = {"parts": [
            {"part_code": "C7061A1012", "catalog_status": "exact",
             "quantity": 3, "quantity_conflict": {"body": 3, "attachment": 10}}
        ]}
        ok, reason = _auto_quote_eligible(_email(), parsed)
        assert ok is False and reason == "quantity_uncertain"

    def test_suspect_blocks_auto_quote(self):
        parsed = {"parts": [
            {"part_code": "X", "catalog_status": "normalized",
             "quantity": 1, "quantity_suspect": True}
        ]}
        ok, reason = _auto_quote_eligible(_email(), parsed)
        assert ok is False and reason == "quantity_uncertain"

    @pytest.mark.asyncio
    async def test_conflict_line_is_not_confirmed(self):
        # currency query -> "TRY", then the part lookup.
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        ccy = MagicMock(); ccy.scalar_one_or_none.return_value = "TRY"
        part_res = MagicMock()
        part_res.scalar_one_or_none.return_value = _part(42, net_price=250.0)
        db.execute = AsyncMock(side_effect=[ccy, part_res])
        svc = QuoteService(db)
        parsed = json.dumps({"parts": [{
            "part_code": "C7061A1012", "catalog_part_id": 42,
            "catalog_status": "exact", "quantity": 3,
            "quantity_conflict": {"body": 3, "attachment": 10},
        }]})
        await svc._create_items_with_matching(1, parsed)
        item = db.add.call_args_list[-1][0][0]
        assert item.quantity == 3
        assert item.is_confirmed is False  # conflict forces review
        assert item.unit_price == 250.0    # still priced from catalog


# ── R2 ────────────────────────────────────────────────────────────
class TestR2ValueCap:
    def test_cap_fires_once_prices_present(self):
        # _annotate_catalog_sell_prices stamps unit_price; the gate then
        # estimates a real total and blocks a too-large order.
        parsed = {"parts": [
            {"part_code": "C7061A1012", "catalog_status": "exact",
             "quantity": 5, "unit_price": 250.0}
        ]}
        cfg = SimpleNamespace(auto_quote_max_amount=1000.0)
        ok, reason = _auto_quote_eligible(_email(), parsed, tenant_config=cfg)
        assert ok is False and reason == "value_above_threshold"  # 1250 > 1000

    def test_under_cap_passes(self):
        parsed = {"parts": [
            {"part_code": "C7061A1012", "catalog_status": "exact",
             "quantity": 1, "unit_price": 250.0}
        ]}
        cfg = SimpleNamespace(auto_quote_max_amount=1000.0)
        ok, reason = _auto_quote_eligible(_email(), parsed, tenant_config=cfg)
        assert ok is True and reason is None


# ── R3 ────────────────────────────────────────────────────────────
class TestR3InputCapKeepsCurrentEmail:
    def test_current_email_survives_huge_thread(self):
        current = "# Current email\n\nRFQ: 5x C7061A1012 SENTINEL_PART"
        threaded = ("OLD THREAD " * 5000) + "\n\n---\n\n" + current  # ~55k
        out = _bound_llm_input(current, threaded, max_input=24000)
        assert "SENTINEL_PART" in out          # current email preserved
        assert out.endswith(current)           # current at the tail, intact
        assert len(out) <= 24000 + 200

    def test_no_truncation_when_under_cap(self):
        current = "current"
        threaded = "thread\n---\ncurrent"
        assert _bound_llm_input(current, threaded, 24000) == threaded


# ── R4 ────────────────────────────────────────────────────────────
class TestR4CurrencyConversion:
    def test_resolve_reports_source_currency(self):
        price, source, ccy = resolve_unit_price_with_currency(
            _part(net_price=300.0, currency="USD"), preferred_currency="TRY"
        )
        assert source == PRICE_SOURCE_LIST and ccy == "USD" and price == 300.0

    @pytest.mark.asyncio
    async def test_foreign_currency_is_converted(self):
        out = {"spare_part_id": None, "honeywell_code": "", "description": "",
               "unit_price": 0.0, "match_score": None, "match_strategy": None,
               "is_confirmed": False}
        part = _part(9, net_price=300.0, currency="USD")
        svc = QuoteService(AsyncMock())
        with patch("app.services.currency_service.convert_currency",
                   new=AsyncMock(return_value=9600.0)):
            await svc._apply_part_to_resolution(out, part, "TRY", code="C7061A1012")
        assert out["unit_price"] == 9600.0  # converted USD->TRY, not 300

    @pytest.mark.asyncio
    async def test_conversion_failure_leaves_line_unpriced(self):
        out = {"spare_part_id": None, "honeywell_code": "", "description": "",
               "unit_price": 0.0, "match_score": None, "match_strategy": None,
               "is_confirmed": False}
        part = _part(9, net_price=300.0, currency="USD")
        svc = QuoteService(AsyncMock())
        with patch("app.services.currency_service.convert_currency",
                   new=AsyncMock(side_effect=ValueError("no FX"))):
            await svc._apply_part_to_resolution(out, part, "TRY", code="C7061A1012")
        assert out["unit_price"] == 0.0  # never a raw USD number on a TRY quote

    @pytest.mark.asyncio
    async def test_same_currency_no_conversion(self):
        out = {"spare_part_id": None, "honeywell_code": "", "description": "",
               "unit_price": 0.0, "match_score": None, "match_strategy": None,
               "is_confirmed": False}
        part = _part(9, net_price=250.0, currency="TRY")
        svc = QuoteService(AsyncMock())
        # convert_currency must NOT be called when currencies match
        with patch("app.services.currency_service.convert_currency",
                   new=AsyncMock(side_effect=AssertionError("should not convert"))):
            await svc._apply_part_to_resolution(out, part, "TRY", code="C7061A1012")
        assert out["unit_price"] == 250.0


# ── R5 ────────────────────────────────────────────────────────────
class TestR5DecimalMoney:
    @pytest.mark.asyncio
    async def test_totals_no_float_drift(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        # three 0.10 lines -> subtotal exactly 0.30, not 0.30000000000000004
        items = [SimpleNamespace(line_total=0.10, unit_price=0.10, quantity=1)
                 for _ in range(3)]
        res = MagicMock(); res.scalars.return_value.all.return_value = items
        db.execute = AsyncMock(return_value=res)
        quote = SimpleNamespace(id=1, tax_rate=0.0, subtotal=0.0,
                                discount_total=0.0, tax_amount=0.0, grand_total=0.0)
        await QuoteService(db)._recalculate_totals(quote)
        assert quote.subtotal == 0.30
        assert quote.grand_total == 0.30
