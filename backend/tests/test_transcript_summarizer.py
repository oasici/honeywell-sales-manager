"""Unit tests for the upgraded transcript summariser (v3).

The AI path is not exercised here (requires network); we cover the pure
helpers that would otherwise silently drift.
"""

from __future__ import annotations

import pytest

from app.services.transcript_summarizer import (
    _chunk_content,
    _coerce_action_items,
    _merge_partials,
    _normalise_partial,
)


@pytest.mark.unit
def test_chunk_short_content_returns_single():
    assert _chunk_content("hello", window=100, overlap=10) == ["hello"]


@pytest.mark.unit
def test_chunk_long_content_overlaps():
    text = "abcdefghij" * 50  # 500 chars
    chunks = _chunk_content(text, window=200, overlap=50)
    assert len(chunks) >= 3
    # Overlap must preserve the last 50 chars of chunk N at the start of chunk N+1.
    assert chunks[0][-50:] == chunks[1][:50]


@pytest.mark.unit
def test_coerce_action_items_normalises_shapes():
    raw = [
        "Pazartesi arayacagiz",
        {"description": "Teklif hazirla", "owner": "Ayse", "due_hint": "3 gun"},
        {"description": ""},  # dropped
        42,  # dropped
    ]
    out = _coerce_action_items(raw)
    assert len(out) == 2
    assert out[0]["description"] == "Pazartesi arayacagiz"
    assert out[0]["owner"] == "ekip"
    assert out[1]["owner"] == "Ayse"


@pytest.mark.unit
def test_normalise_partial_clamps_sentiment_and_topics():
    payload = {
        "summary": "ozet",
        "sentiment": "mixed",  # invalid -> neutral
        "key_topics": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
        "competitor_mentions": [
            {"name": "Siemens", "snippet": "daha ucuz", "sentiment": "negative"},
            {"snippet": "name yok"},  # dropped
        ],
        "action_items": ["arayalim"],
    }
    result = _normalise_partial(payload)
    assert result["sentiment"] == "neutral"
    assert len(result["key_topics"]) == 8
    assert result["competitor_mentions"][0]["name"] == "Siemens"
    assert len(result["competitor_mentions"]) == 1


@pytest.mark.unit
def test_merge_partials_dedupes_and_collapses_sentiment():
    partials = [
        {
            "summary": "Bolum 1 ozet.",
            "action_items": [{"description": "X", "owner": "ekip", "due_hint": ""}],
            "sentiment": "positive",
            "key_topics": ["pricing", "SLA"],
            "competitor_mentions": [{"name": "Siemens", "snippet": "...", "sentiment": "negative"}],
            "objections": ["çok pahalı"],
            "pricing_concerns": [],
            "positive_signals": ["imzaya hazırız"],
            "next_meeting_proposed": None,
        },
        {
            "summary": "Bolum 2 ozet.",
            "action_items": [{"description": "X", "owner": "ekip", "due_hint": ""}],  # duplicate
            "sentiment": "negative",
            "key_topics": ["SLA", "rakip"],
            "competitor_mentions": [{"name": "Siemens", "snippet": "...", "sentiment": "negative"}],
            "objections": ["bütçe sıkı"],
            "pricing_concerns": ["indirim şart"],
            "positive_signals": [],
            "next_meeting_proposed": "haftaya",
        },
    ]
    merged = _merge_partials(partials)
    assert "Bolum 1 ozet." in merged["summary"]
    assert "Bolum 2 ozet." in merged["summary"]
    assert merged["sentiment"] == "neutral"  # tied
    assert len(merged["action_items"]) == 1
    assert merged["key_topics"][:2] == ["pricing", "SLA"]
    assert merged["next_meeting_proposed"] == "haftaya"
    assert len(merged["competitor_mentions"]) == 1
