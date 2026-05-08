"""PII redaction utilities.

Round-8 R8-SEC-1 — extracted from ``summary_service.py`` so multiple AI
surfaces (summary, AI attributes, future tools) share one source of truth
for redaction logic.

The patterns are deliberately conservative: emails + phone-shaped strings.
The intent is "best effort defense in depth" before the prompt reaches an
external LLM, not a full DLP gate.
"""

from __future__ import annotations

import re
from typing import Any


_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")


def redact_pii(text: str) -> str:
    """Best-effort PII redaction (email + phone-like patterns).

    Returns ``text`` with email addresses replaced by ``[REDACTED_EMAIL]``
    and phone-shaped substrings replaced by ``[REDACTED_PHONE]``.
    """
    if not text:
        return text
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text


def redact_context(context: dict[str, Any]) -> dict[str, Any]:
    """Apply ``redact_pii`` to every string value in a flat context dict.

    Non-string values are coerced via ``str()`` then redacted, so callers
    don't have to pre-serialize structured payloads.
    """
    return {k: redact_pii(str(v)) if v is not None else None for k, v in context.items()}
