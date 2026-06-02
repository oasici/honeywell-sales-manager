"""Phase-5 tests: catalog-resolver hardening (audit M1/M2).

M1 — a structurally-complete code that is one digit away from a real but
     *different* SKU (…1013 vs …1012) must NOT be silently mapped to that
     neighbour; route to review. OCR letter↔digit slips still resolve.
M2 — two catalog SKUs that normalize to the same key are ambiguous; a
     normalized hit on that key routes to review instead of guessing.
"""

from __future__ import annotations

import pytest

from app.models.spare_part import SparePart
from app.services.part_catalog_resolver import resolve_part_code


@pytest.fixture
async def m1_catalog(db) -> None:
    db.add(SparePart(honeywell_code="C7061A1012", name_en="Flame detector"))
    db.add(SparePart(honeywell_code="RM7895A1014", name_en="Burner controller"))
    await db.commit()


@pytest.fixture
async def m2_catalog(db) -> None:
    # Two distinct codes that both normalize to "ab1299".
    db.add(SparePart(honeywell_code="AB-1299", name_en="Part A"))
    db.add(SparePart(honeywell_code="AB1-299", name_en="Part B"))
    await db.commit()


class TestM1DigitNeighbourSuppressed:
    @pytest.mark.asyncio
    async def test_one_digit_off_full_code_routes_to_review(self, db, m1_catalog):
        # …1013 is one edit from the real …1012, but it's a *different*
        # part number, not a typo. Must not auto-suggest C7061A1012.
        r = await resolve_part_code(db, "C7061A1013")
        assert r.status == "unknown"
        assert r.part_id is None

    @pytest.mark.asyncio
    async def test_ocr_letter_for_digit_still_resolves(self, db, m1_catalog):
        # 'O' instead of '0' changes the letter skeleton -> genuine typo.
        r = await resolve_part_code(db, "C7O61A1012")
        assert r.status == "fuzzy_levenshtein"
        assert r.canonical_code == "C7061A1012"


class TestM2NormalizedCollision:
    @pytest.mark.asyncio
    async def test_colliding_normalized_key_routes_to_review(self, db, m2_catalog):
        # Input normalizes to "ab1299" which maps to two distinct SKUs.
        r = await resolve_part_code(db, "AB1299")
        assert r.status == "unknown"
        assert r.part_id is None

    @pytest.mark.asyncio
    async def test_exact_still_wins_over_collision(self, db, m2_catalog):
        # An exact (case-insensitive) hit on one of the colliding codes
        # still resolves — collision only blocks the ambiguous normalized
        # path.
        r = await resolve_part_code(db, "ab-1299")
        assert r.status == "exact"
        assert r.canonical_code == "AB-1299"
