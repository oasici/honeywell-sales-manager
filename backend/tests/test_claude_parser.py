"""TDD tests for Claude email parser service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.circuit_breaker import CircuitOpenError
from app.services.claude_parser import (
    ClaudeApiError,
    parse_email,
    clear_cache,
    _empty_result,
)


def _make_mock_response(tool_input: dict, stop_reason: str = "tool_use") -> MagicMock:
    """Build a Claude SDK-shaped response with a single tool_use block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extract_email_data"
    block.input = tool_input

    response = MagicMock()
    response.content = [block]
    response.stop_reason = stop_reason
    return response


# ── Cycle 1: Empty result when no API key ──

@pytest.mark.asyncio
async def test_should_return_empty_result_when_api_key_not_set():
    """parse_email returns empty result when ANTHROPIC_API_KEY is empty."""
    clear_cache()
    with patch("app.services.claude_parser.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = ""
        result = await parse_email("Hello, I need parts")

    assert result["parts"] == []
    assert result["is_spare_part_request"] is False
    assert result["category"] == "general_inquiry"
    assert result["confidence"] == 0.0
    assert result["language"] == "tr"


# ── Cycle 2: Successful parse with tool_use response ──

@pytest.mark.asyncio
async def test_should_extract_parts_from_claude_tool_use_response():
    """parse_email extracts structured data from Claude tool_use block."""
    clear_cache()

    tool_result = {
        "language": "tr",
        "customer_name": "Ahmet Yilmaz",
        "customer_company": "Turkcell A.S.",
        "parts": [
            {"part_code": "C7061A1012", "part_description": "UV Sensor", "quantity": 5, "urgency": "critical"},
            {"part_code": "ST7800A1054", "part_description": "Purge Timer", "quantity": 2, "urgency": "high"},
        ],
        "is_spare_part_request": True,
        "category": "spare_part_request",
        "confidence": 0.95,
    }

    mock_create = AsyncMock(return_value=_make_mock_response(tool_result))

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.claude_messages_create", new=mock_create):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"
        mock_settings.AI_MODEL_NAME = "claude-test"
        mock_settings.AI_MAX_TOKENS = 1024
        result = await parse_email(
            "C7061A1012 UV Sensor 5 adet acil, ST7800A1054 Purge Timer 2 adet. Ahmet Yilmaz, Turkcell",
            subject="Yedek Parca Talebi",
        )

    assert result["customer_name"] == "Ahmet Yilmaz"
    assert result["customer_company"] == "Turkcell A.S."
    assert result["is_spare_part_request"] is True
    assert result["category"] == "spare_part_request"
    assert result["confidence"] == 0.95
    assert len(result["parts"]) == 2
    assert result["parts"][0]["part_code"] == "C7061A1012"
    assert result["parts"][0]["quantity"] == 5
    assert result["parts"][0]["urgency"] == "critical"
    assert result["parts"][1]["part_code"] == "ST7800A1054"


# ── Cycle 3: Cache hit returns cached result ──

@pytest.mark.asyncio
async def test_should_return_cached_result_on_second_call():
    """Same email body returns cached result without calling Claude API."""
    clear_cache()

    tool_result = {
        "language": "en",
        "customer_name": "John",
        "customer_company": "Acme",
        "parts": [{"part_code": "ABC123", "part_description": "Sensor", "quantity": 1, "urgency": "normal"}],
        "is_spare_part_request": True,
        "category": "spare_part_request",
        "confidence": 0.9,
    }

    mock_create = AsyncMock(return_value=_make_mock_response(tool_result))
    email_body = "I need ABC123 sensor 1 piece. John from Acme."

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.claude_messages_create", new=mock_create):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"
        mock_settings.AI_MODEL_NAME = "claude-test"
        mock_settings.AI_MAX_TOKENS = 1024

        result1 = await parse_email(email_body)
        assert mock_create.call_count == 1

        result2 = await parse_email(email_body)
        assert mock_create.call_count == 1  # Still 1, cache hit

    assert result1 == result2
    assert result2["customer_name"] == "John"


# ── Cycle 4: Retry on API failure ──

@pytest.mark.asyncio
async def test_should_retry_on_api_failure_and_succeed():
    """parse_email retries up to 3 times on transient failure."""
    clear_cache()

    tool_result = {
        "language": "tr",
        "customer_name": "Test",
        "customer_company": "",
        "parts": [{"part_code": "X1", "part_description": "Part", "quantity": 1, "urgency": "normal"}],
        "is_spare_part_request": True,
        "category": "spare_part_request",
        "confidence": 0.8,
    }

    mock_create = AsyncMock(side_effect=[
        Exception("API timeout"),
        Exception("Rate limited"),
        _make_mock_response(tool_result),
    ])

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.claude_messages_create", new=mock_create), \
         patch("app.services.claude_parser.asyncio.sleep", new_callable=AsyncMock):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"
        mock_settings.AI_MODEL_NAME = "claude-test"
        mock_settings.AI_MAX_TOKENS = 1024
        result = await parse_email("Need part X1 urgently")

    assert result["parts"][0]["part_code"] == "X1"
    assert mock_create.call_count == 3


# ── Cycle 5: All retries exhausted raises ClaudeApiError ──

@pytest.mark.asyncio
async def test_should_raise_error_when_all_retries_fail():
    """parse_email raises ClaudeApiError when all 3 retries fail."""
    clear_cache()

    mock_create = AsyncMock(side_effect=Exception("Persistent failure"))

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.claude_messages_create", new=mock_create), \
         patch("app.services.claude_parser.asyncio.sleep", new_callable=AsyncMock):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"
        mock_settings.AI_MODEL_NAME = "claude-test"
        mock_settings.AI_MAX_TOKENS = 1024
        with pytest.raises(ClaudeApiError):
            await parse_email("Some email content")

    assert mock_create.call_count == 3


# ── Cycle 6: Empty parts should NOT be cached ──

@pytest.mark.asyncio
async def test_should_not_cache_results_with_no_parts():
    """Results with empty parts list are not cached (cheap to recompute, often wrong)."""
    clear_cache()

    empty_tool_result = {
        "language": "tr",
        "customer_name": "",
        "customer_company": "",
        "parts": [],
        "is_spare_part_request": False,
        "category": "general_inquiry",
        "confidence": 0.3,
    }

    mock_create = AsyncMock(return_value=_make_mock_response(empty_tool_result))
    email_body = "Just a general question about services"

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.claude_messages_create", new=mock_create):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"
        mock_settings.AI_MODEL_NAME = "claude-test"
        mock_settings.AI_MAX_TOKENS = 1024

        await parse_email(email_body)
        await parse_email(email_body)

    assert mock_create.call_count == 2  # Both calls hit the API


# ── Cycle 7: Subject included in API call ──

@pytest.mark.asyncio
async def test_should_include_subject_in_api_call():
    """When subject is provided, it is prepended to the user message."""
    clear_cache()

    tool_result = _empty_result() | {
        "parts": [{"part_code": "A", "part_description": "B", "quantity": 1, "urgency": "normal"}],
    }
    mock_create = AsyncMock(return_value=_make_mock_response(tool_result))

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.claude_messages_create", new=mock_create):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"
        mock_settings.AI_MODEL_NAME = "claude-test"
        mock_settings.AI_MAX_TOKENS = 1024
        await parse_email("Body text here", subject="Urgent Parts Request")

    call_args = mock_create.call_args
    user_message = call_args.kwargs["messages"][0]["content"]
    assert "Subject: Urgent Parts Request" in user_message
    assert "Body text here" in user_message


# ── Cycle 8: CircuitOpenError fast-fails without retries ──

@pytest.mark.asyncio
async def test_should_fast_fail_when_breaker_open():
    """When breaker raises CircuitOpenError, parse_email fast-fails (no retries).

    Without this short-circuit the function would burn 3 retry slots returning
    the same error, defeating the breaker's purpose.
    """
    clear_cache()

    sleep_mock = AsyncMock()
    mock_create = AsyncMock(side_effect=CircuitOpenError("Circuit breaker 'claude_api' acik durumda"))

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.claude_messages_create", new=mock_create), \
         patch("app.services.claude_parser.asyncio.sleep", new=sleep_mock):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"
        mock_settings.AI_MODEL_NAME = "claude-test"
        mock_settings.AI_MAX_TOKENS = 1024
        with pytest.raises(ClaudeApiError, match="breaker open"):
            await parse_email("Some email content")

    # Single attempt, no retries — breaker open should not waste retry budget
    assert mock_create.call_count == 1
    assert sleep_mock.call_count == 0


# ── Cycle 9: Wrapper receives expected kwargs ──

@pytest.mark.asyncio
async def test_should_pass_timeout_and_model_kwargs_to_wrapper():
    """The wrapper call must include timeout=30.0 and the configured model."""
    clear_cache()

    tool_result = _empty_result() | {
        "parts": [{"part_code": "X", "part_description": "Y", "quantity": 1, "urgency": "normal"}],
    }
    mock_create = AsyncMock(return_value=_make_mock_response(tool_result))

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.claude_messages_create", new=mock_create):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"
        mock_settings.AI_MODEL_NAME = "claude-fast-triage"
        mock_settings.AI_MAX_TOKENS = 512
        await parse_email("Body text")

    kwargs = mock_create.call_args.kwargs
    assert kwargs["timeout"] == 30.0
    assert kwargs["model"] == "claude-fast-triage"
    assert kwargs["max_tokens"] == 512
    assert kwargs["tool_choice"] == {"type": "tool", "name": "extract_email_data"}
