"""TDD tests for Claude email parser service."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.claude_parser import (
    ClaudeApiError,
    parse_email,
    clear_cache,
    _empty_result,
)


# ── Cycle 1: Empty result when no API key ──

@pytest.mark.asyncio
async def test_should_return_empty_result_when_api_key_not_set():
    """RED: parse_email should return empty result when ANTHROPIC_API_KEY is empty."""
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
    """RED: parse_email should extract structured data from Claude tool_use block."""
    clear_cache()

    mock_tool_result = {
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

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "extract_email_data"
    mock_block.input = mock_tool_result

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.stop_reason = "tool_use"

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"
        result = await parse_email(
            "C7061A1012 UV Sensor 5 adet acil, ST7800A1054 Purge Timer 2 adet. Ahmet Yilmaz, Turkcell",
            subject="Yedek Parca Talebi"
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
    """RED: Same email body should return cached result without calling Claude API."""
    clear_cache()

    mock_tool_result = {
        "language": "en",
        "customer_name": "John",
        "customer_company": "Acme",
        "parts": [{"part_code": "ABC123", "part_description": "Sensor", "quantity": 1, "urgency": "normal"}],
        "is_spare_part_request": True,
        "category": "spare_part_request",
        "confidence": 0.9,
    }

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "extract_email_data"
    mock_block.input = mock_tool_result

    mock_response = MagicMock()
    mock_response.content = [mock_block]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    email_body = "I need ABC123 sensor 1 piece. John from Acme."

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"

        # First call - should call Claude
        result1 = await parse_email(email_body)
        assert mock_client.messages.create.call_count == 1

        # Second call - should return cache, NOT call Claude again
        result2 = await parse_email(email_body)
        assert mock_client.messages.create.call_count == 1  # Still 1, not 2

    assert result1 == result2
    assert result2["customer_name"] == "John"


# ── Cycle 4: Retry on API failure ──

@pytest.mark.asyncio
async def test_should_retry_on_api_failure_and_succeed():
    """RED: parse_email should retry up to 3 times on failure, succeeding on retry."""
    clear_cache()

    mock_tool_result = {
        "language": "tr",
        "customer_name": "Test",
        "customer_company": "",
        "parts": [{"part_code": "X1", "part_description": "Part", "quantity": 1, "urgency": "normal"}],
        "is_spare_part_request": True,
        "category": "spare_part_request",
        "confidence": 0.8,
    }

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "extract_email_data"
    mock_block.input = mock_tool_result

    mock_response = MagicMock()
    mock_response.content = [mock_block]

    mock_client = AsyncMock()
    # Fail first 2 attempts, succeed on 3rd
    mock_client.messages.create = AsyncMock(
        side_effect=[
            Exception("API timeout"),
            Exception("Rate limited"),
            mock_response,
        ]
    )

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.AsyncAnthropic", return_value=mock_client), \
         patch("asyncio.sleep", new_callable=AsyncMock):  # Skip actual sleep
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"
        result = await parse_email("Need part X1 urgently")

    assert result["parts"][0]["part_code"] == "X1"
    assert mock_client.messages.create.call_count == 3


# ── Cycle 5: All retries exhausted raises ClaudeApiError ──

@pytest.mark.asyncio
async def test_should_raise_error_when_all_retries_fail():
    """RED: parse_email should raise ClaudeApiError when all 3 retries fail."""
    clear_cache()

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(
        side_effect=Exception("Persistent failure")
    )

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.AsyncAnthropic", return_value=mock_client), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"
        with pytest.raises(ClaudeApiError):
            await parse_email("Some email content")

    assert mock_client.messages.create.call_count == 3


# ── Cycle 6: Empty parts should NOT be cached ──

@pytest.mark.asyncio
async def test_should_not_cache_results_with_no_parts():
    """RED: Results with empty parts list should not be cached."""
    clear_cache()

    empty_tool_result = {
        "language": "tr",
        "customer_name": "",
        "customer_company": "",
        "parts": [],  # Empty!
        "is_spare_part_request": False,
        "category": "general_inquiry",
        "confidence": 0.3,
    }

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "extract_email_data"
    mock_block.input = empty_tool_result

    mock_response = MagicMock()
    mock_response.content = [mock_block]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    email_body = "Just a general question about services"

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"

        # First call
        await parse_email(email_body)
        # Second call - should call Claude again (not cached)
        await parse_email(email_body)

    assert mock_client.messages.create.call_count == 2  # Called twice, not cached


# ── Cycle 7: Subject included in API call ──

@pytest.mark.asyncio
async def test_should_include_subject_in_api_call():
    """RED: When subject is provided, it should be prepended to the message."""
    clear_cache()

    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "extract_email_data"
    mock_block.input = _empty_result() | {"parts": [{"part_code": "A", "part_description": "B", "quantity": 1, "urgency": "normal"}]}

    mock_response = MagicMock()
    mock_response.content = [mock_block]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch("app.services.claude_parser.settings") as mock_settings, \
         patch("app.services.claude_parser.AsyncAnthropic", return_value=mock_client):
        mock_settings.ANTHROPIC_API_KEY = "sk-test-key"
        await parse_email("Body text here", subject="Urgent Parts Request")

    call_args = mock_client.messages.create.call_args
    user_message = call_args.kwargs["messages"][0]["content"]
    assert "Subject: Urgent Parts Request" in user_message
    assert "Body text here" in user_message
