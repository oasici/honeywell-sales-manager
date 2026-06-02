"""Phase-2 tests: line-item matching unification + confidence guard.

Encodes the spare-parts audit invariants P2 / P3:
  * the catalog resolver's verdict (the gate's engine) decides the SKU —
    the parts_matcher is not even consulted when the resolver resolved it
  * a sub-threshold matcher result never auto-populates SKU + price
  * fuzzy resolver suggestions are populated but never auto-confirmed
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.quote_service import QuoteService


def _db_returning(part):
    """Mock AsyncSession whose every execute().scalar_one_or_none() == part."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = part
    db.execute = AsyncMock(return_value=result)
    return db


def _part(part_id, code, *, net_price=None, transfer_price=None, min_margin_pct=0.0):
    prices = []
    if net_price is not None:
        prices = [
            SimpleNamespace(
                id=1,
                net_price=net_price,
                list_price=net_price,
                currency="TRY",
                valid_from=None,
                valid_until=None,
            )
        ]
    return SimpleNamespace(
        id=part_id,
        honeywell_code=code,
        name_en="Flame detector",
        name_tr="Alev dedektoru",
        prices=prices,
        transfer_price=transfer_price,
        supplier_price=None,
        min_margin_pct=min_margin_pct,
    )


class TestResolverVerdictIsSourceOfTruth:
    @pytest.mark.asyncio
    async def test_exact_verdict_uses_catalog_part_id_and_confirms(self):
        part = _part(42, "C7061A1012", net_price=250.0)
        service = QuoteService(_db_returning(part))

        # A *different* matcher result must be ignored when the resolver
        # already produced a gate verdict.
        out = await service._resolve_line_match(
            part_req={"catalog_part_id": 42, "catalog_status": "exact"},
            code="C7061A1012",
            match_result={"matches": [{"spare_part_id": 999, "score": 100.0, "strategy": "x"}]},
            preferred_currency="TRY",
        )
        assert out["spare_part_id"] == 42  # NOT 999 from the matcher
        assert out["match_strategy"] == "catalog_exact"
        assert out["unit_price"] == 250.0
        assert out["is_confirmed"] is True

    @pytest.mark.asyncio
    async def test_fuzzy_verdict_populates_but_never_confirms(self):
        part = _part(7, "C7061A1011", net_price=100.0)
        service = QuoteService(_db_returning(part))
        out = await service._resolve_line_match(
            part_req={"catalog_part_id": 7, "catalog_status": "fuzzy_levenshtein"},
            code="C7061A1011",
            match_result=None,
            preferred_currency="TRY",
        )
        assert out["spare_part_id"] == 7
        assert out["is_confirmed"] is False
        assert out["match_strategy"] == "catalog_fuzzy_levenshtein"


class TestMatcherFallbackConfidenceGuard:
    @pytest.mark.asyncio
    async def test_subthreshold_match_leaves_sku_unset(self):
        part = _part(5, "VALVE99", net_price=50.0)
        service = QuoteService(_db_returning(part))
        out = await service._resolve_line_match(
            part_req={"catalog_status": "unknown"},  # resolver couldn't resolve
            code="",
            match_result={
                "matches": [
                    {"spare_part_id": 5, "score": 50.0, "strategy": "fuzzy_name"}
                ]
            },
            preferred_currency="TRY",
        )
        assert out["spare_part_id"] is None  # 50 < 80 threshold
        assert out["unit_price"] == 0.0
        assert out["is_confirmed"] is False
        # but the suggestion is recorded for the review UI
        assert out["match_score"] == 50.0
        assert out["match_strategy"] == "fuzzy_name"

    @pytest.mark.asyncio
    async def test_above_threshold_match_populates_sku_and_price(self):
        part = _part(9, "C7061A1012", net_price=300.0)
        service = QuoteService(_db_returning(part))
        out = await service._resolve_line_match(
            part_req={"catalog_status": "unknown"},
            code="",
            match_result={
                "matches": [
                    {"spare_part_id": 9, "score": 85.0, "strategy": "prefix_code"}
                ]
            },
            preferred_currency="TRY",
        )
        assert out["spare_part_id"] == 9
        assert out["unit_price"] == 300.0
        # 85 >= LINE_ITEM_MATCH_THRESHOLD but < AUTO_CONFIRM_THRESHOLD(80)? 85>=80 -> confirmed
        assert out["is_confirmed"] is True

    @pytest.mark.asyncio
    async def test_resolved_but_unpriced_is_not_confirmed(self):
        # cost-only, zero margin -> unpriced -> cannot confirm even at exact
        part = _part(11, "C7061A1012", transfer_price=100.0, min_margin_pct=0.0)
        service = QuoteService(_db_returning(part))
        out = await service._resolve_line_match(
            part_req={"catalog_part_id": 11, "catalog_status": "exact"},
            code="C7061A1012",
            match_result=None,
            preferred_currency="TRY",
        )
        assert out["spare_part_id"] == 11
        assert out["unit_price"] == 0.0  # never the 100 cost
        assert out["is_confirmed"] is False
