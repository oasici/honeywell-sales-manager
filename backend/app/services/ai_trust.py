"""AI Trust Layer - PII scrubbing + audit for outbound LLM calls.

Minimum viable equivalent of Salesforce's "Einstein Trust Layer":

1. Mask PII (TC kimlik, vergi numarası, IBAN, kredi kartı, telefon, e-mail)
   before any prompt leaves the process.
2. Keep a reversible map so responses referencing a masked token can be
   re-hydrated on the way back.
3. Emit a lightweight audit record (prompt hash + masked-token counts)
   so admins can prove to auditors that PII never hit the vendor API.

Intentionally dependency-free: pure regex + in-memory dict. The caller
passes the context in ``AITrustContext`` so the same map survives the
request/response roundtrip.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Mapping

logger = logging.getLogger(__name__)


# ── Regex patterns ───────────────────────────────────────────────────────────
# Ordered by specificity — longer patterns first so we don't double-mask.

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "EMAIL",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    (
        "IBAN",
        re.compile(r"\bTR\d{2}\s?(?:\d{4}\s?){5}\d{2}\b"),
    ),
    (
        "CREDIT_CARD",
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    ),
    (
        # Turkish mobile & landline: +90/0 followed by 10 digits, with optional spaces/dashes.
        "PHONE",
        re.compile(r"(?:\+90|0)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}"),
    ),
    (
        "TCKN",
        re.compile(r"\b[1-9]\d{10}\b"),  # TC Kimlik: 11 digits, starts != 0
    ),
    (
        "VKN",
        re.compile(r"\b\d{10}\b"),  # Vergi Kimlik: exactly 10 digits
    ),
]


@dataclass
class AITrustContext:
    """State shared between masking on the way out and un-masking on the way in."""

    token_map: dict[str, str] = field(default_factory=dict)
    reverse_map: dict[str, str] = field(default_factory=dict)
    hit_counts: dict[str, int] = field(default_factory=dict)

    def totals(self) -> dict[str, int]:
        return dict(self.hit_counts)

    def is_dirty(self) -> bool:
        return bool(self.token_map)


def _mint_token(prefix: str) -> str:
    return f"<<{prefix}_{uuid.uuid4().hex[:8].upper()}>>"


# ── Public API ──────────────────────────────────────────────────────────────

def scrub(text: str, *, ctx: AITrustContext | None = None) -> tuple[str, AITrustContext]:
    """Replace PII in ``text`` with deterministic placeholders.

    The same raw value within one context always maps to the same token so
    downstream references stay consistent. Pass the returned ``ctx`` to
    :func:`unscrub` to restore the original strings in the LLM response.
    """
    if ctx is None:
        ctx = AITrustContext()
    if not text:
        return text, ctx

    output = text
    for label, pattern in _PII_PATTERNS:
        def replace(match: re.Match[str]) -> str:
            raw = match.group(0)
            if raw in ctx.token_map:
                return ctx.token_map[raw]
            token = _mint_token(label)
            ctx.token_map[raw] = token
            ctx.reverse_map[token] = raw
            ctx.hit_counts[label] = ctx.hit_counts.get(label, 0) + 1
            return token

        output = pattern.sub(replace, output)
    return output, ctx


def scrub_many(
    payloads: Mapping[str, str], *, ctx: AITrustContext | None = None
) -> tuple[dict[str, str], AITrustContext]:
    """Scrub a mapping (e.g. prompt slots) while reusing one context."""
    ctx = ctx or AITrustContext()
    cleaned: dict[str, str] = {}
    for key, value in payloads.items():
        cleaned[key], ctx = scrub(value or "", ctx=ctx)
    return cleaned, ctx


def unscrub(text: str, ctx: AITrustContext) -> str:
    """Reverse :func:`scrub` on the LLM response."""
    if not text or not ctx.reverse_map:
        return text
    output = text
    for token, raw in ctx.reverse_map.items():
        output = output.replace(token, raw)
    return output


def audit_record(ctx: AITrustContext, *, prompt: str, model: str) -> dict:
    """Build a safe audit row (no raw PII) for persistence/logging."""
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt else ""
    return {
        "prompt_sha256": digest,
        "model": model,
        "pii_hits": ctx.totals(),
        "token_count": len(ctx.token_map),
    }
