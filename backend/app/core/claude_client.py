"""Breaker-protected Claude client.

Single chokepoint every service should use to talk to Anthropic. Without
this, a Claude API outage cascades: every AI endpoint hangs on its 60s
timeout, the request pool drains, the entire backend stops accepting
new traffic. The breaker fast-fails the 4th call after 3 in a row throw
and stays open for 30s — the rest of the app keeps serving.

Drop-in replacement for ``client.messages.create(**kwargs)``:

    from app.core.claude_client import claude_messages_create

    response = await claude_messages_create(
        model=settings.AI_MODEL_NAME,
        max_tokens=512,
        system=...,
        messages=[...],
    )

When the breaker is open ``CircuitOpenError`` is raised. Callers should
catch it and degrade gracefully (cached fallback, queued retry, or a
user-visible "AI service temporarily unavailable" message). Don't try
to swallow the error and pretend success — that hides outages from
Sentry and breaks the SLO loop.
"""

from __future__ import annotations

from typing import Any

import anthropic

from app.core.circuit_breaker import claude_breaker
from app.core.config import settings


def _build_client(timeout: float | None) -> anthropic.AsyncAnthropic:
    kwargs: dict[str, Any] = {"api_key": settings.ANTHROPIC_API_KEY}
    if timeout is not None:
        kwargs["timeout"] = timeout
    return anthropic.AsyncAnthropic(**kwargs)


async def claude_messages_create(
    *,
    timeout: float | None = None,
    **kwargs: Any,
) -> Any:
    """Breaker-protected ``client.messages.create()``.

    All keyword arguments are forwarded to the SDK call. Pass ``timeout``
    to override the default Anthropic client timeout (e.g. claude_parser
    uses ``timeout=30.0`` for fast email triage).
    """

    async def _do_call() -> Any:
        client = _build_client(timeout)
        return await client.messages.create(**kwargs)

    return await claude_breaker.call(_do_call)


def claude_breaker_status() -> dict[str, str | int]:
    """Health endpoint payload — current breaker state."""
    return {
        "name": claude_breaker.name,
        "state": claude_breaker.state,
        "failure_count": claude_breaker._failure_count,
    }
