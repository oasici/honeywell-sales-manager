"""Round-17 catalog cross-check unit tests.

Verifies the resolution ladder: exact → normalized → fuzzy_prefix →
fuzzy_levenshtein → unknown.
"""

from __future__ import annotations

import pytest

from app.models.spare_part import SparePart
from app.services.part_catalog_resolver import (
    _damerau_levenshtein,
    resolve_part_code,
    resolve_parsed_parts,
)


@pytest.fixture
async def seeded_catalog(db) -> list[SparePart]:
    parts = [
        SparePart(
            honeywell_code="C7061A1012",
            name_en="Flame detector",
            supplier_price=100.0,
            transfer_price=120.0,
        ),
        SparePart(
            honeywell_code="RM7895A1014",
            name_en="Burner controller",
            supplier_price=200.0,
            transfer_price=240.0,
        ),
        SparePart(
            honeywell_code="51309276-150",
            name_en="Pressure transmitter",
            supplier_price=300.0,
            transfer_price=360.0,
        ),
    ]
    for p in parts:
        db.add(p)
    await db.commit()
    return parts


@pytest.mark.asyncio
async def test_exact_match(db, seeded_catalog) -> None:
    r = await resolve_part_code(db, "C7061A1012")
    assert r.status == "exact"
    assert r.canonical_code == "C7061A1012"
    assert r.part_id is not None


@pytest.mark.asyncio
async def test_exact_case_insensitive(db, seeded_catalog) -> None:
    r = await resolve_part_code(db, "c7061a1012")
    assert r.status == "exact"


@pytest.mark.asyncio
async def test_normalized_strips_hyphens(db, seeded_catalog) -> None:
    """`51309276150` should resolve to `51309276-150` via normalization."""
    r = await resolve_part_code(db, "51309276150")
    assert r.status == "normalized"
    assert r.canonical_code == "51309276-150"


@pytest.mark.asyncio
async def test_fuzzy_prefix(db, seeded_catalog) -> None:
    """Customer truncated the suffix — unique prefix → resolved."""
    r = await resolve_part_code(db, "C7061")
    assert r.status == "fuzzy_prefix"
    assert r.canonical_code == "C7061A1012"


@pytest.mark.asyncio
async def test_fuzzy_levenshtein_single_char_typo(db, seeded_catalog) -> None:
    """Letter O instead of zero — edit distance 1."""
    r = await resolve_part_code(db, "C7O61A1012")
    assert r.status == "fuzzy_levenshtein"
    assert r.canonical_code == "C7061A1012"
    assert r.edit_distance is not None and r.edit_distance <= 2


@pytest.mark.asyncio
async def test_unknown_when_too_different(db, seeded_catalog) -> None:
    r = await resolve_part_code(db, "ZZ99XX")
    assert r.status == "unknown"
    assert r.part_id is None


@pytest.mark.asyncio
async def test_empty_input_returns_unknown(db, seeded_catalog) -> None:
    r = await resolve_part_code(db, "")
    assert r.status == "unknown"


@pytest.mark.asyncio
async def test_resolve_parsed_parts_annotates_list(db, seeded_catalog) -> None:
    parsed = [
        {"part_code": "C7061A1012", "quantity": 5},
        {"part_code": "UNKNOWN999", "quantity": 1},
        {"part_code": "", "part_description": "flame detector", "quantity": 1},
    ]
    out = await resolve_parsed_parts(db, parsed)
    assert out[0]["catalog_status"] == "exact"
    assert out[0]["catalog_part_id"] is not None
    assert out[1]["catalog_status"] == "unknown"
    assert out[2]["catalog_status"] == "no_code"


# ── Damerau-Levenshtein helper ────────────────────────────────────


@pytest.mark.parametrize(
    "a,b,expected_le",
    [
        ("abc", "abc", 0),
        ("abc", "abd", 1),
        ("abcd", "acbd", 1),  # transposition
        ("kitten", "sitting", 3),
        ("c7061a1012", "c70610a1012", 1),  # insertion
    ],
)
def test_damerau_levenshtein_distances(a, b, expected_le) -> None:
    d = _damerau_levenshtein(a, b, cap=10)
    assert d == expected_le, f"d({a!r}, {b!r}) = {d}, expected {expected_le}"


def test_damerau_levenshtein_caps_early() -> None:
    """Far-apart strings should return ``cap + 1`` early."""
    d = _damerau_levenshtein("abc", "xyzwxyz", cap=2)
    assert d > 2
