"""Tests for the Agentic SDR helper functions (pure, no network)."""

from __future__ import annotations

import pytest

from app.services.agentic_sdr import (
    _extract_tool_call,
    _normalise_priority,
    _scrub_pack,
    _unscrub,
    _walk,
)


class _ToolBlock:
    def __init__(self, name: str, input_: dict):
        self.type = "tool_use"
        self.name = name
        self.input = input_


class _TextBlock:
    type = "text"
    text = "ignored"


class _FakeResponse:
    def __init__(self, content):
        self.content = content


@pytest.mark.unit
def test_extract_tool_call_prefers_tool_use_block():
    resp = _FakeResponse([_TextBlock(), _ToolBlock("schedule_task", {"title": "X", "due_in_days": 1, "priority": "high", "rationale": "stuck"})])
    name, payload = _extract_tool_call(resp)
    assert name == "schedule_task"
    assert payload["title"] == "X"


@pytest.mark.unit
def test_extract_tool_call_returns_none_when_missing():
    name, payload = _extract_tool_call(_FakeResponse([_TextBlock()]))
    assert name is None
    assert payload == {}


@pytest.mark.unit
def test_walk_applies_fn_to_strings_only():
    pack = {"a": "hello", "b": ["x", 1, {"c": "y"}]}
    upper = _walk(pack, str.upper)
    assert upper == {"a": "HELLO", "b": ["X", 1, {"c": "Y"}]}


@pytest.mark.unit
def test_normalise_priority_translates_medium_to_normal():
    assert _normalise_priority("medium") == "normal"
    assert _normalise_priority("high") == "high"
    assert _normalise_priority("bogus") == "normal"
    assert _normalise_priority(None) == "normal"


@pytest.mark.unit
def test_scrub_pack_is_noop_when_flag_disabled(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "FEATURE_AI_TRUST_LAYER", False)
    pack = {"email": "x@y.com"}
    scrubbed, ctx = _scrub_pack(pack)
    assert scrubbed == pack
    assert ctx is None


@pytest.mark.unit
def test_scrub_and_unscrub_roundtrip(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "FEATURE_AI_TRUST_LAYER", True)
    pack = {"email": "x@y.com", "note": "vkn 1234567890"}
    scrubbed, ctx = _scrub_pack(pack)
    assert ctx is not None and ctx.is_dirty()
    assert "x@y.com" not in str(scrubbed)
    restored = _unscrub(scrubbed, ctx)
    assert restored["email"] == "x@y.com"
