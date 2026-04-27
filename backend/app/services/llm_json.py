"""Shared helpers for parsing JSON out of Claude completions.

Claude returns the structured payload in three shapes we've actually
seen in production. Each individual service handling a Claude
response used to do its own ``json.loads(text.strip())`` call, which
crashed with ``Expecting value: line 1 column 1 (char 0)`` whenever
the model wrapped the JSON in prose or markdown — see Sentry issues
HONEYWELL-BACKEND-2/3/4/8/9 and the customer-health and deal-risk
services.

Centralising the extraction here means a) one place to fix when
Claude introduces a new response shape, and b) zero risk of forgetting
to wrap the call in defensive code at the call site.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


_FENCED_JSON_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE
)


def extract_json_object(text: str | None) -> str | None:
    """Best-effort extract a single JSON object string from a Claude reply.

    Handles:

    1. Raw JSON: ``{"k": "v"}`` — return as-is.
    2. Markdown-fenced: ``\\`\\`\\`json\\n{...}\\n\\`\\`\\``` — strip the fence.
    3. Prose-prefixed: ``"Here is the JSON: {...}"`` — slice from the
       first ``{`` to the matching closing ``}``.

    Returns ``None`` when no plausible object boundary is found, so
    callers can fall back to a rule-based path instead of raising.
    """
    if not text:
        return None
    cleaned = text.strip()

    m = _FENCED_JSON_RE.search(cleaned)
    if m:
        return m.group(1).strip()

    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        return cleaned[start : end + 1]

    return None


def parse_claude_json(text: str | None) -> dict[str, Any] | None:
    """Extract + parse a JSON object dict from a Claude completion.

    Returns the parsed dict on success, ``None`` on any failure
    (empty response, no JSON object found, malformed JSON, or the
    parsed value isn't a dict).
    """
    candidate = extract_json_object(text)
    if candidate is None:
        return None
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Claude JSON parse failed: %s", exc)
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed
