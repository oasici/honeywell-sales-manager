"""Tests for the Claude churn prediction JSON extractor.

Reproduces the three response shapes that historically broke the parser
in production (Sentry HONEYWELL-BACKEND-A) and asserts that each one
either yields the embedded object or returns ``None`` cleanly so the
caller falls through to the rule-based fallback.
"""

from __future__ import annotations

import pytest

from app.services.customer_health_service import _extract_json_object


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Shape 1 — already raw JSON.
        ('{"risk_level": "high"}', '{"risk_level": "high"}'),
        # Shape 1 with surrounding whitespace.
        ('   {"risk_level": "low"}   ', '{"risk_level": "low"}'),
        # Shape 2 — fenced markdown block (the most common Claude shape).
        (
            '```json\n{"risk_level": "medium", "churn_probability": 42}\n```',
            '{"risk_level": "medium", "churn_probability": 42}',
        ),
        # Shape 2 without the language tag.
        (
            '```\n{"risk_level": "high"}\n```',
            '{"risk_level": "high"}',
        ),
        # Shape 3 — prose preamble + object.
        (
            'Here is the analysis:\n{"risk_level": "high", "actions": ["a"]}',
            '{"risk_level": "high", "actions": ["a"]}',
        ),
        # Shape 3 — prose preamble + suffix after object.
        (
            'Result: {"risk_level": "low"}\nThanks!',
            '{"risk_level": "low"}',
        ),
    ],
)
def test_extract_json_object_extracts_known_shapes(raw: str, expected: str) -> None:
    assert _extract_json_object(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        # The exact failure mode from Sentry: empty completion.
        "",
        # Whitespace-only.
        "   \n  ",
        # Prose with no object boundary at all.
        "Sorry, I cannot answer this question.",
        # Open brace with no closing brace.
        "{not closed",
    ],
)
def test_extract_json_object_returns_none_for_unrecoverable(raw: str) -> None:
    """No `{...}` boundary → caller should fall through to rule-based."""
    assert _extract_json_object(raw) is None
