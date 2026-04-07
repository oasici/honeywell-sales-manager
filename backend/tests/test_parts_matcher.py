import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.parts_matcher import _catalog_cache


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    """Clear the parts matcher catalog cache before each test."""
    _catalog_cache["parts"] = None
    _catalog_cache["ts"] = 0
    yield
    _catalog_cache["parts"] = None
    _catalog_cache["ts"] = 0


@pytest.mark.asyncio
async def test_exact_code_match():
    """Test exact code matching with normalization."""
    from app.services.parts_matcher import _normalize_code

    assert _normalize_code("ABC-123-DEF") == "ABC123DEF"
    assert _normalize_code("abc 123 def") == "ABC123DEF"
    assert _normalize_code("  ABC--123  ") == "ABC123"


@pytest.mark.asyncio
async def test_match_parts_empty_input():
    """Test matching with empty parts list."""
    from app.services.parts_matcher import match_parts

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await match_parts(mock_db, [])
    assert result == []


@pytest.mark.asyncio
async def test_match_parts_with_code():
    """Test matching when part_code is provided."""
    from app.services.parts_matcher import match_parts
    from app.models.spare_part import SparePart

    _catalog_cache["parts"] = None
    _catalog_cache["ts"] = 0

    mock_part = MagicMock()
    mock_part.id = 1
    mock_part.honeywell_code = "ABC123"
    mock_part.model_number = None
    mock_part.name_tr = "Test Parca"
    mock_part.name_en = "Test Part"
    mock_part.category = "Sensor"
    mock_part.is_active = True
    mock_part.keywords_json = None
    mock_part.aliases_json = None

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_part]
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await match_parts(mock_db, [{"part_code": "ABC-123", "part_description": ""}])
    assert len(result) == 1
    assert len(result[0]["matches"]) > 0
    assert result[0]["matches"][0]["score"] == 100.0  # Exact match
