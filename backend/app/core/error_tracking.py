"""Sentry error tracking integration.

Wires up sentry-sdk with:
- FastAPI + SQLAlchemy + stdlib logging integrations
- Environment + release (git SHA) tagging
- Conservative sample rates (prod 10% traces, dev 100%)
- PII scrubber covering Turkish identifiers (TCKN, VKN, IBAN), credit
  cards, phones, emails before events leave the process.

Called from main.py lifespan. Safe no-op when SENTRY_DSN is unset or
sentry-sdk fails to import (logs a notice and keeps the app running).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


# ── PII scrub patterns ────────────────────────────────────────────────
# These fire on any string Sentry is about to ship (message, breadcrumb
# message, extra, tags). We replace matches in-place with a placeholder
# so the event still has enough context to debug without leaking data.

_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Email
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[email]"),
    # Turkish IBAN (TR + 24 digits, tolerant of spaces)
    (re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.IGNORECASE), "[iban]"),
    # Credit card (13-19 digits, often space/dash separated)
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[card]"),
    # TCKN (11 digits, first digit non-zero; conservative — may match other 11-digit numbers)
    (re.compile(r"\b[1-9]\d{10}\b"), "[tckn]"),
    # VKN (10 digits) — after TCKN so 11-digit matches take priority
    (re.compile(r"\b\d{10}\b"), "[vkn]"),
    # Turkish phone (+90, 0 5xx xxx xxxx)
    (re.compile(r"(?:\+90|0)\s?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}"), "[phone]"),
]


def _scrub_string(value: str) -> str:
    for pattern, replacement in _PII_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, dict):
        return {k: _scrub_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    return value


def _before_send(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    """Scrub PII from event payload before it leaves the process."""
    try:
        if "message" in event:
            event["message"] = _scrub_value(event["message"])
        if "logentry" in event and isinstance(event["logentry"], dict):
            event["logentry"] = _scrub_value(event["logentry"])
        if "breadcrumbs" in event and isinstance(event["breadcrumbs"], dict):
            for crumb in event["breadcrumbs"].get("values", []):
                if isinstance(crumb, dict):
                    if "message" in crumb:
                        crumb["message"] = _scrub_value(crumb["message"])
                    if "data" in crumb:
                        crumb["data"] = _scrub_value(crumb["data"])
        if "exception" in event and isinstance(event["exception"], dict):
            for exc in event["exception"].get("values", []):
                if isinstance(exc, dict) and "value" in exc:
                    exc["value"] = _scrub_value(exc["value"])
        if "extra" in event:
            event["extra"] = _scrub_value(event["extra"])
        if "tags" in event:
            event["tags"] = _scrub_value(event["tags"])
        if "request" in event and isinstance(event["request"], dict):
            req = event["request"]
            if "query_string" in req:
                req["query_string"] = _scrub_value(req["query_string"])
            if "data" in req:
                req["data"] = _scrub_value(req["data"])
            headers = req.get("headers")
            if isinstance(headers, dict):
                for key in list(headers.keys()):
                    if key.lower() in {"authorization", "cookie", "x-csrf-token"}:
                        headers[key] = "[redacted]"
    except Exception:
        logger.exception("sentry_scrubber_error")
    return event


def _resolve_release() -> str:
    # Render exposes RENDER_GIT_COMMIT; GitHub Actions exposes GITHUB_SHA.
    # Fall back to a static marker so dev builds can still be filtered.
    return (
        os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GITHUB_SHA")
        or os.getenv("GIT_COMMIT")
        or "dev"
    )


def init_sentry(dsn: str | None = None, env: str = "development") -> None:
    """Initialize Sentry SDK if DSN is provided."""
    if not dsn:
        logger.info("Sentry DSN not configured — error tracking disabled")
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        is_prod = env in {"production", "sandbox"}

        sentry_sdk.init(
            dsn=dsn,
            environment=env,
            release=_resolve_release(),
            traces_sample_rate=0.1 if is_prod else 1.0,
            profiles_sample_rate=0.0,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
            send_default_pii=False,
            attach_stacktrace=True,
            max_breadcrumbs=50,
            before_send=_before_send,
        )
        logger.info("sentry_initialized env=%s release=%s", env, _resolve_release())
    except ImportError:
        logger.info("sentry-sdk not installed — error tracking disabled")
    except Exception as exc:
        logger.warning("sentry_init_failed: %s", exc)
