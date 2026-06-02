"""Tests for the breaker-protected Claude client wrapper.

These verify that ``claude_messages_create``:
- Forwards kwargs to ``AsyncAnthropic.messages.create``
- Routes the call through ``claude_breaker``
- Trips the breaker after enough consecutive failures, then fast-fails
"""

from __future__ import annotations

import anthropic
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.circuit_breaker import CircuitOpenError, claude_breaker


def _rate_limit_error(retry_after=None) -> anthropic.RateLimitError:
    headers = {}
    if retry_after is not None:
        headers["retry-after"] = str(retry_after)
    response = httpx.Response(
        429,
        headers=headers,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    return anthropic.RateLimitError("rate limited", response=response, body=None)


@pytest.fixture(autouse=True)
def reset_breaker():
    """Reset the singleton breaker between tests so failures don't leak."""
    claude_breaker.reset()
    yield
    claude_breaker.reset()


@pytest.mark.asyncio
async def test_wrapper_forwards_kwargs_to_anthropic():
    """All kwargs (model, messages, tool_choice, etc.) reach the SDK call."""
    from app.core.claude_client import claude_messages_create

    sentinel_response = MagicMock(name="claude-response")
    fake_messages = MagicMock()
    fake_messages.create = AsyncMock(return_value=sentinel_response)
    fake_client = MagicMock()
    fake_client.messages = fake_messages

    with patch("app.core.claude_client.anthropic.AsyncAnthropic", return_value=fake_client):
        result = await claude_messages_create(
            model="claude-test",
            max_tokens=128,
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
        )

    assert result is sentinel_response
    fake_messages.create.assert_awaited_once_with(
        model="claude-test",
        max_tokens=128,
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
    )


@pytest.mark.asyncio
async def test_wrapper_passes_timeout_to_client_construction():
    """``timeout`` kwarg is consumed by the wrapper and passed to AsyncAnthropic."""
    from app.core.claude_client import claude_messages_create

    fake_messages = MagicMock()
    fake_messages.create = AsyncMock(return_value=MagicMock())
    fake_client = MagicMock()
    fake_client.messages = fake_messages

    captured: dict = {}

    def fake_ctor(**kwargs):
        captured.update(kwargs)
        return fake_client

    with patch("app.core.claude_client.anthropic.AsyncAnthropic", side_effect=fake_ctor):
        await claude_messages_create(timeout=12.5, model="m", max_tokens=1, messages=[])

    assert captured.get("timeout") == 12.5
    # timeout must NOT leak into messages.create kwargs
    assert "timeout" not in fake_messages.create.call_args.kwargs


@pytest.mark.asyncio
async def test_wrapper_trips_breaker_after_consecutive_failures():
    """3 consecutive Claude SDK failures trip the breaker; 4th call fast-fails."""
    from app.core.claude_client import claude_messages_create

    fake_messages = MagicMock()
    fake_messages.create = AsyncMock(side_effect=RuntimeError("anthropic 5xx"))
    fake_client = MagicMock()
    fake_client.messages = fake_messages

    with patch("app.core.claude_client.anthropic.AsyncAnthropic", return_value=fake_client):
        # claude_breaker threshold is 3
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await claude_messages_create(model="m", max_tokens=1, messages=[])

        assert claude_breaker.state == "open"

        # 4th call must NOT reach the SDK — breaker fast-fails
        with pytest.raises(CircuitOpenError):
            await claude_messages_create(model="m", max_tokens=1, messages=[])

    # Exactly 3 SDK calls were attempted; 4th was short-circuited
    assert fake_messages.create.await_count == 3


@pytest.mark.asyncio
async def test_wrapper_success_keeps_breaker_closed():
    """A successful call leaves the breaker closed and resets failure count."""
    from app.core.claude_client import claude_messages_create

    fake_messages = MagicMock()
    fake_messages.create = AsyncMock(return_value=MagicMock(name="ok"))
    fake_client = MagicMock()
    fake_client.messages = fake_messages

    with patch("app.core.claude_client.anthropic.AsyncAnthropic", return_value=fake_client):
        await claude_messages_create(model="m", max_tokens=1, messages=[])

    assert claude_breaker.state == "closed"
    assert claude_breaker._failure_count == 0


@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds():
    """A 429 is retried (after backoff) and a subsequent success returns
    normally — the breaker stays closed because it never sees the 429."""
    from app.core.claude_client import claude_messages_create

    sentinel = MagicMock(name="ok-after-429")
    fake_messages = MagicMock()
    fake_messages.create = AsyncMock(side_effect=[_rate_limit_error(), sentinel])
    fake_client = MagicMock()
    fake_client.messages = fake_messages

    with patch("app.core.claude_client.anthropic.AsyncAnthropic", return_value=fake_client), \
         patch("app.core.claude_client.asyncio.sleep", new=AsyncMock()) as fake_sleep:
        result = await claude_messages_create(model="m", max_tokens=1, messages=[])

    assert result is sentinel
    assert fake_messages.create.await_count == 2
    fake_sleep.assert_awaited_once()
    assert claude_breaker.state == "closed"
    assert claude_breaker._failure_count == 0


@pytest.mark.asyncio
async def test_429_honors_retry_after_header():
    """The Retry-After header value drives the backoff delay."""
    from app.core.claude_client import claude_messages_create

    fake_messages = MagicMock()
    fake_messages.create = AsyncMock(
        side_effect=[_rate_limit_error(retry_after=5), MagicMock()]
    )
    fake_client = MagicMock()
    fake_client.messages = fake_messages

    with patch("app.core.claude_client.anthropic.AsyncAnthropic", return_value=fake_client), \
         patch("app.core.claude_client.asyncio.sleep", new=AsyncMock()) as fake_sleep:
        await claude_messages_create(model="m", max_tokens=1, messages=[])

    fake_sleep.assert_awaited_once_with(5.0)


@pytest.mark.asyncio
async def test_exhausted_429_propagates_after_max_attempts():
    """Persistent 429s exhaust the rate-limit retries and propagate as a
    single breaker failure (not one per internal attempt)."""
    from app.core.claude_client import (
        _RATE_LIMIT_MAX_ATTEMPTS,
        claude_messages_create,
    )

    fake_messages = MagicMock()
    fake_messages.create = AsyncMock(side_effect=_rate_limit_error())
    fake_client = MagicMock()
    fake_client.messages = fake_messages

    with patch("app.core.claude_client.anthropic.AsyncAnthropic", return_value=fake_client), \
         patch("app.core.claude_client.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(anthropic.RateLimitError):
            await claude_messages_create(model="m", max_tokens=1, messages=[])

    assert fake_messages.create.await_count == _RATE_LIMIT_MAX_ATTEMPTS
    # One logical call -> one breaker failure, even though it retried N times.
    assert claude_breaker._failure_count == 1


def test_retry_after_seconds_parsing():
    from app.core.claude_client import _retry_after_seconds

    assert _retry_after_seconds(_rate_limit_error(retry_after=12)) == 12.0
    assert _retry_after_seconds(_rate_limit_error()) is None


def test_breaker_status_payload_shape():
    """The status helper exposes name/state/failure_count for the health endpoint."""
    from app.core.claude_client import claude_breaker_status

    payload = claude_breaker_status()
    assert payload["name"] == "claude_api"
    assert payload["state"] in {"closed", "open", "half_open"}
    assert isinstance(payload["failure_count"], int)
