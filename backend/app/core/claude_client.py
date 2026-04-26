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

import time
from typing import Any

import anthropic

from app.core.circuit_breaker import claude_breaker
from app.core.config import settings


def _emit_metric(name: str, value: float, *, kind: str, tags: dict[str, str]) -> None:
    """Best-effort Sentry metric emit. No-op when sentry-sdk is unavailable
    or DSN is unset, so this can sit on hot paths without risk."""
    try:
        from sentry_sdk import metrics as _sentry_metrics

        if kind == "count":
            _sentry_metrics.count(name, int(value), tags=tags)
        elif kind == "distribution":
            _sentry_metrics.distribution(name, value, tags=tags)
    except Exception:
        pass


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

    model = str(kwargs.get("model", "unknown"))

    async def _do_call() -> Any:
        client = _build_client(timeout)
        return await client.messages.create(**kwargs)

    started = time.monotonic()
    try:
        result = await claude_breaker.call(_do_call)
    except Exception:
        _emit_metric(
            "claude.request",
            1,
            kind="count",
            tags={"model": model, "status": "error"},
        )
        raise

    elapsed_ms = (time.monotonic() - started) * 1000
    _emit_metric(
        "claude.request",
        1,
        kind="count",
        tags={"model": model, "status": "ok"},
    )
    _emit_metric(
        "claude.request.duration_ms",
        elapsed_ms,
        kind="distribution",
        tags={"model": model},
    )
    return result


def claude_breaker_status() -> dict[str, str | int]:
    """Health endpoint payload — current breaker state."""
    return {
        "name": claude_breaker.name,
        "state": claude_breaker.state,
        "failure_count": claude_breaker._failure_count,
    }
