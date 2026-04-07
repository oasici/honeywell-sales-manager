"""TDD tests for the parts_matcher module."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.parts_matcher import (
    FUZZY_NAME_CUTOFF,
    PREFIX_MIN_CHARS,
    TOP_N,
    _catalog_cache,
    _normalize_code,
    match_parts,
)


def _make_spare_part(
    part_id=1,
    honeywell_code="ABC123",
    name_en="Test Part",
    name_tr="Test Parca",
    category="Sensors",
    is_active=True,
    model_number=None,
):
    """Create a mock SparePart object."""
    part = MagicMock()
    part.id = part_id
    part.honeywell_code = honeywell_code
    part.model_number = model_number
    part.name_en = name_en
    part.name_tr = name_tr
    part.category = category
    part.is_active = is_active
    return part


def _make_mock_db(catalog):
    """Create a mock AsyncSession returning the given catalog."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = catalog
    db.execute = AsyncMock(return_value=result_mock)
    return db


@pytest.fixture(autouse=True)
def _mock_semantic_matcher():
    """Inject a mock semantic_matcher module to prevent real imports."""
    mock_module = MagicMock()
    mock_search = AsyncMock(return_value=[])
    mock_module.search_similar = mock_search
    sys.modules["app.services.semantic_matcher"] = mock_module
    yield
    sys.modules.pop("app.services.semantic_matcher", None)


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    """Reset catalog cache so mock DB is always called."""
    _catalog_cache["parts"] = None
    _catalog_cache["ts"] = 0
    yield
    _catalog_cache["parts"] = None
    _catalog_cache["ts"] = 0


def _make_mock_db_with_catalog(catalog):
    """Create mock DB that returns catalog on first execute (for _get_cached_catalog)
    and empty on subsequent calls (for semantic matcher etc.)."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = catalog
    db.execute = AsyncMock(return_value=result_mock)
    return db


class TestNormalizeCode:
    """Test cycle 2: normalize codes removing dashes and spaces."""

    def test_should_normalize_codes_removing_dashes_and_spaces(self):
        assert _normalize_code("ABC-123") == "ABC123"
        assert _normalize_code("abc 123") == "ABC123"
        assert _normalize_code("A.B/C_1-2 3") == "ABC123"

    def test_should_uppercase_result(self):
        assert _normalize_code("abc") == "ABC"

    def test_should_handle_empty_string(self):
        assert _normalize_code("") == ""


class TestExactCodeMatch:
    """Test cycle 1: exact honeywell_code match = 100%."""

    @pytest.mark.asyncio
    async def test_should_return_100_score_for_exact_code_match(self):
        _catalog_cache["parts"] = None
        _catalog_cache["ts"] = 0

        part = _make_spare_part(part_id=1, honeywell_code="ABC123")
        db = _make_mock_db([part])

        requested = [{"part_code": "ABC123", "part_description": ""}]
        results = await match_parts(db, requested)

        matches = results[0]["matches"]
        exact_matches = [m for m in matches if m["strategy"] == "exact_code"]
        assert len(exact_matches) >= 1
        assert exact_matches[0]["score"] == 100.0
        assert exact_matches[0]["honeywell_code"] == "ABC123"

    @pytest.mark.asyncio
    async def test_should_match_exact_despite_formatting(self):
        _catalog_cache["parts"] = None
        _catalog_cache["ts"] = 0

        part = _make_spare_part(part_id=1, honeywell_code="ABC-123")
        db = _make_mock_db([part])

        requested = [{"part_code": "ABC 123", "part_description": ""}]
        results = await match_parts(db, requested)

        matches = results[0]["matches"]
        exact_matches = [m for m in matches if m["strategy"] == "exact_code"]
        assert len(exact_matches) >= 1
        assert exact_matches[0]["score"] == 100.0


class TestPrefixMatch:
    """Test cycles 3 and 4: prefix match and minimum length."""

    @pytest.mark.asyncio
    async def test_should_return_85_score_for_prefix_match(self):
        _catalog_cache["parts"] = None
        _catalog_cache["ts"] = 0

        part = _make_spare_part(part_id=1, honeywell_code="ABCD1234XYZ")
        db = _make_mock_db([part])

        requested = [{"part_code": "ABCD1234", "part_description": ""}]
        results = await match_parts(db, requested)

        matches = results[0]["matches"]
        prefix_matches = [m for m in matches if m["strategy"] == "prefix_code"]
        assert len(prefix_matches) >= 1
        assert prefix_matches[0]["score"] == 85.0

    @pytest.mark.asyncio
    async def test_should_require_minimum_4_chars_for_prefix_match(self):
        part = _make_spare_part(part_id=1, honeywell_code="AB99999")
        db = _make_mock_db([part])

        requested = [{"part_code": "AB", "part_description": ""}]
        results = await match_parts(db, requested)

        matches = results[0]["matches"]
        prefix_matches = [m for m in matches if m["strategy"] == "prefix_code"]
        assert len(prefix_matches) == 0


class TestEmptyInput:
    """Test cycle 5: empty parts list = empty result."""

    @pytest.mark.asyncio
    async def test_should_return_empty_matches_for_empty_input(self):
        db = _make_mock_db([])

        results = await match_parts(db, [])

        assert results == []

    @pytest.mark.asyncio
    async def test_should_return_empty_matches_when_catalog_empty(self):
        db = _make_mock_db([])

        requested = [{"part_code": "ABC123", "part_description": "Some part"}]
        results = await match_parts(db, requested)

        assert len(results) == 1
        assert results[0]["matches"] == []


class TestFuzzyNameMatch:
    """Test cycle 6: fuzzy name match above 50% threshold."""

    @pytest.mark.asyncio
    async def test_should_return_fuzzy_match_above_threshold(self):
        _catalog_cache["parts"] = None
        _catalog_cache["ts"] = 0

        part = _make_spare_part(
            part_id=1,
            honeywell_code="ZZZZZ999",
            name_en="Temperature Sensor Module",
            name_tr="Sicaklik Sensor Modulu",
        )
        db = _make_mock_db([part])

        requested = [
            {
                "part_code": "",
                "part_description": "Temperature Sensor Module",
            }
        ]
        results = await match_parts(db, requested)

        matches = results[0]["matches"]
        fuzzy_name_matches = [m for m in matches if m["strategy"] == "fuzzy_name"]
        assert len(fuzzy_name_matches) >= 1
        assert fuzzy_name_matches[0]["score"] > 0


class TestTopNSorting:
    """Test cycle 7: results sorted descending, max 5."""

    @pytest.mark.asyncio
    async def test_should_return_top_5_matches_sorted_by_score(self):
        parts = []
        for i in range(8):
            parts.append(
                _make_spare_part(
                    part_id=i + 1,
                    honeywell_code=f"TESTPART{i:04d}",
                    name_en=f"Test Part Number {i}",
                    name_tr=f"Test Parca Numarasi {i}",
                )
            )
        db = _make_mock_db(parts)

        requested = [{"part_code": "TESTPART", "part_description": "Test Part Number"}]
        results = await match_parts(db, requested)

        matches = results[0]["matches"]
        assert len(matches) <= TOP_N

        scores = [m["score"] for m in matches]
        assert scores == sorted(scores, reverse=True)
