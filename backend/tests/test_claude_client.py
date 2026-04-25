"""Tests for the breaker-protected Claude client wrapper.

These verify that ``claude_messages_create``:
- Forwards kwargs to ``AsyncAnthropic.messages.create``
- Routes the call through ``claude_breaker``
- Trips the breaker after enough consecutive failures, then fast-fails
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.circuit_breaker import CircuitOpenError, claude_breaker


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


def test_breaker_status_payload_shape():
    """The status helper exposes name/state/failure_count for the health endpoint."""
    from app.core.claude_client import claude_breaker_status

    payload = claude_breaker_status()
    assert payload["name"] == "claude_api"
    assert payload["state"] in {"closed", "open", "half_open"}
    assert isinstance(payload["failure_count"], int)
