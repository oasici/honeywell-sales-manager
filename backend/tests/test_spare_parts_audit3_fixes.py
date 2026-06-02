"""Third-audit remediation tests (T1, T2, T4) — boundary hardening.

T1 — discontinued (is_active=False) parts don't resolve / don't quote.
T2 — duplicate same-SKU parsed parts collapse to one (summed, flagged).
T4 — an expired-only price list yields no price (unpriced → review).
(T3 is covered in test_quote_service::TestApproveQuote; T5 estimate-currency
 is exercised via the conversion path in test_spare_parts_reaudit_fixes.)
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.models.spare_part import SparePart
from app.services.part_catalog_resolver import dedupe_parsed_parts, resolve_part_code
from app.services.part_pricing import (
    PRICE_SOURCE_UNPRICED,
    resolve_unit_price,
    select_price_entry,
)

TODAY = date(2026, 6, 2)


# ── T1 ────────────────────────────────────────────────────────────
@pytest.fixture
async def catalog(db):
    db.add(SparePart(honeywell_code="C7061A1012", name_en="Flame detector", is_active=True))
    db.add(SparePart(honeywell_code="OLD9999X", name_en="Discontinued", is_active=False))
    await db.commit()


class TestT1InactiveParts:
    @pytest.mark.asyncio
    async def test_active_part_resolves_exact(self, db, catalog):
        r = await resolve_part_code(db, "C7061A1012")
        assert r.status == "exact" and r.part_id is not None

    @pytest.mark.asyncio
    async def test_inactive_part_does_not_resolve(self, db, catalog):
        # exact code of a discontinued SKU must NOT resolve -> review.
        r = await resolve_part_code(db, "OLD9999X")
        assert r.status == "unknown"
        assert r.part_id is None

    @pytest.mark.asyncio
    async def test_inactive_part_not_matched_by_normalization(self, db, catalog):
        r = await resolve_part_code(db, "OLD-9999-X")
        assert r.status == "unknown"


# ── T2 ────────────────────────────────────────────────────────────
class TestT2Dedup:
    def test_duplicate_codes_collapse_and_flag(self):
        parts = [
            {"part_code": "C7061A1012", "quantity": 3, "catalog_status": "exact"},
            {"part_code": "C7061-A1012", "quantity": 5, "catalog_status": "exact"},
        ]
        out = dedupe_parsed_parts(parts)
        assert len(out) == 1
        assert out[0]["quantity"] == 8            # summed
        assert out[0]["quantity_suspect"] is True  # flagged for review
        assert out[0]["duplicate_merged"] is True

    def test_canonical_code_used_when_present(self):
        parts = [
            {"part_code": "c7061a1012", "canonical_part_code": "C7061A1012", "quantity": 1},
            {"part_code": "C7061A1012", "canonical_part_code": "C7061A1012", "quantity": 2},
        ]
        out = dedupe_parsed_parts(parts)
        assert len(out) == 1 and out[0]["quantity"] == 3

    def test_distinct_codes_kept(self):
        parts = [
            {"part_code": "C7061A1012", "quantity": 1},
            {"part_code": "RM7895A1014", "quantity": 2},
        ]
        out = dedupe_parsed_parts(parts)
        assert len(out) == 2

    def test_codeless_entries_passed_through(self):
        parts = [
            {"part_description": "flame detector", "quantity": 1},
            {"part_description": "valve", "quantity": 1},
        ]
        out = dedupe_parsed_parts(parts)
        assert len(out) == 2  # no code -> not merged


# ── T4 ────────────────────────────────────────────────────────────
def _entry(net, *, valid_from=None, valid_until=None, currency="TRY", id=1):
    return SimpleNamespace(id=id, net_price=net, list_price=net, currency=currency,
                           valid_from=valid_from, valid_until=valid_until)


def _part(prices, **over):
    base = dict(prices=prices, transfer_price=None, supplier_price=None,
                price_currency=None, min_margin_pct=0.0)
    base.update(over)
    return SimpleNamespace(**base)


class TestT4ExpiredPrices:
    def test_expired_only_yields_no_entry(self):
        part = _part([_entry(250.0, valid_until=date(2025, 1, 1))])  # expired
        assert select_price_entry(part, today=TODAY) is None

    def test_future_only_yields_no_entry(self):
        part = _part([_entry(250.0, valid_from=date(2027, 1, 1))])  # not yet valid
        assert select_price_entry(part, today=TODAY) is None

    def test_expired_only_is_unpriced_not_quoted(self):
        part = _part([_entry(250.0, valid_until=date(2025, 1, 1))])
        price, source = resolve_unit_price(part, today=TODAY)
        assert source == PRICE_SOURCE_UNPRICED and price == 0.0

    def test_undated_entry_still_valid(self):
        part = _part([_entry(250.0)])  # no dates -> open-ended
        assert select_price_entry(part, today=TODAY).net_price == 250.0
