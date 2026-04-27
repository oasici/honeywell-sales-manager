"""Tests for the shared Claude-JSON parser.

Each shape below corresponds to a real production Claude response we've
seen — the regression these tests guard against is the Sentry crash
``Expecting value: line 1 column 1 (char 0)`` from raw ``json.loads``
on prose-wrapped output.
"""

from __future__ import annotations

import pytest

from app.services.llm_json import extract_json_object, parse_claude_json


@pytest.mark.parametrize(
    "raw,expected_subset",
    [
        ('{"risk_level": "high"}', {"risk_level": "high"}),
        ('  {"risk_level": "high"}  \n', {"risk_level": "high"}),
        ('```json\n{"risk_level": "high"}\n```', {"risk_level": "high"}),
        ('```\n{"risk_level": "high"}\n```', {"risk_level": "high"}),
        (
            'Here is the JSON you requested: {"risk_level": "high"}',
            {"risk_level": "high"},
        ),
        (
            'Sure! {"risk_level": "high", "factors": []} — anything else?',
            {"risk_level": "high"},
        ),
    ],
)
def test_parse_claude_json_handles_real_world_shapes(raw, expected_subset):
    parsed = parse_claude_json(raw)
    assert parsed is not None
    for k, v in expected_subset.items():
        assert parsed[k] == v


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   \n",
        "no JSON here at all",
        "{ this is not valid json",
        "[1, 2, 3]",  # arrays aren't accepted — caller wants a dict
    ],
)
def test_parse_claude_json_returns_none_for_unrecoverable_input(raw):
    assert parse_claude_json(raw) is None


def test_extract_json_object_returns_none_for_empty():
    assert extract_json_object(None) is None
    assert extract_json_object("") is None
