"""Tests for competitive intelligence service."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.competitive_intel_service import (
    KNOWN_COMPETITORS,
    _keyword_scan,
    scan_for_competitors,
)


@pytest.mark.asyncio
async def test_keyword_scan_finds_siemens():
    """Keyword scan should detect Siemens mention in text."""
    text = "Musteri Siemens ile de gorusuyor, fiyat karsilastirmasi yapiyor."
    mentions = _keyword_scan(text, "email", 1, None)

    assert len(mentions) == 1
    assert mentions[0]["competitor_name"] == "Siemens"
    assert mentions[0]["detected_by"] == "keyword"
    assert "Siemens" in mentions[0]["context_snippet"]


@pytest.mark.asyncio
async def test_keyword_scan_finds_multiple_competitors():
    """Keyword scan should detect multiple competitor mentions."""
    text = (
        "Proje icin ABB ve Schneider teklifleri de degerlendiriliyor. "
        "Yokogawa da bir teklif sunmus."
    )
    mentions = _keyword_scan(text, "transcript", 5, 10)

    competitor_names = {m["competitor_name"] for m in mentions}
    assert "ABB" in competitor_names
    assert "Schneider" in competitor_names
    assert "Yokogawa" in competitor_names
    assert len(mentions) == 3


@pytest.mark.asyncio
async def test_keyword_scan_no_matches():
    """Keyword scan should return empty list when no competitors found."""
    text = "Honeywell urunleri ile ilgili fiyat teklifi istiyorum."
    mentions = _keyword_scan(text, "email", 2, None)

    assert len(mentions) == 0
