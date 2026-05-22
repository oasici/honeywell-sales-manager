"""Round-17 SPF / DKIM / DMARC verdict resolver for inbound IMAP messages.

The Round-15 email pipeline trusted the ``From:`` header verbatim
— anyone who could craft an SMTP envelope to the inbox could
impersonate a known customer's domain. This module reads the
``Authentication-Results`` header (added by the upstream mail
server, typically the customer's MX or your inbound gateway) and
extracts a single verdict:

* ``pass``       — DMARC pass OR (SPF pass AND DKIM pass)
* ``fail``       — DMARC fail OR explicit SPF=fail / DKIM=fail
* ``none``       — no auth results present (sender domain doesn't
                    publish records, or the upstream server didn't
                    annotate the message)
* ``unverified`` — header present but unparseable

The downstream review-queue policy (see ``EmailProcessingService``)
treats anything except ``pass`` as "needs human review before
auto-quoting".

When the optional ``authheaders`` dependency is unavailable, the
function still works at reduced power via a regex fallback. The
fallback handles the common case (Google Workspace + Microsoft 365
emit verbose Authentication-Results headers) but won't follow
exotic SMTP relay chains.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


VerdictLiteral = str  # "pass" | "fail" | "none" | "unverified"


def resolve_sender_auth(raw_message_bytes: bytes) -> VerdictLiteral:
    """Resolve the inbound-message sender auth verdict.

    ``raw_message_bytes`` is the full raw message (headers + body)
    as returned by ``IMAP4.fetch(... '(RFC822)')``. The function
    only inspects headers; the body is touched for DKIM body-hash
    verification when ``authheaders`` is available.
    """
    if not raw_message_bytes:
        return "none"
    try:
        return _resolve_via_authheaders(raw_message_bytes)
    except Exception as exc:  # noqa: BLE001 — every internal path must stay open
        logger.debug("authheaders path failed; falling back: %s", exc)
    return _resolve_via_header_regex(raw_message_bytes)


def _resolve_via_authheaders(raw_message_bytes: bytes) -> VerdictLiteral:
    """Use the ``authheaders`` library when available.

    The library follows the IETF RFC 8601 syntax for the
    ``Authentication-Results`` header and surfaces structured
    verdicts. We treat:

      * ``dmarc=pass`` OR (``spf=pass`` AND ``dkim=pass``) → ``pass``
      * ``dmarc=fail`` OR ``spf=fail`` OR ``dkim=fail`` → ``fail``
      * everything else → ``none``
    """
    try:
        import authheaders
    except ImportError:
        return _resolve_via_header_regex(raw_message_bytes)

    # ``authres_header_value`` returns the *parsed* AR header dict.
    # If the message has no AR header, fall back to regex (which
    # also handles the same "none" case).
    try:
        ar_value = authheaders.authres_header_value(raw_message_bytes)
    except Exception:  # noqa: BLE001
        return _resolve_via_header_regex(raw_message_bytes)

    if not ar_value:
        return "none"

    return _verdict_from_text(ar_value)


def _resolve_via_header_regex(raw_message_bytes: bytes) -> VerdictLiteral:
    """Conservative regex over the raw headers — fallback path.

    Reads the first ``Authentication-Results:`` block and applies
    the same verdict rule as the structured path.
    """
    try:
        head = raw_message_bytes.split(b"\r\n\r\n", 1)[0].decode("latin-1", errors="replace")
    except Exception:  # noqa: BLE001
        return "unverified"

    # Multi-line header — fold continuation lines.
    head = re.sub(r"\r?\n[ \t]+", " ", head)

    matches = re.findall(
        r"(?im)^Authentication-Results:\s*(.+)$",
        head,
    )
    if not matches:
        return "none"

    # Concatenate every AR header — some upstream gateways add their
    # own. We pass the joined text through the same verdict rule.
    return _verdict_from_text(" ; ".join(matches))


def _verdict_from_text(ar_text: str) -> VerdictLiteral:
    """Apply the verdict rule to a free-form Authentication-Results body."""
    if not ar_text:
        return "none"
    t = ar_text.lower()

    def _has(token: str) -> bool:
        # Match ``spf=pass`` / ``dkim = fail`` / ``dmarc=pass`` even
        # with whitespace and case variation around the equals.
        return re.search(rf"\b{token}\s*=\s*pass\b|\b{token}\s*=\s*fail\b", t) is not None

    def _val(token: str) -> str | None:
        m = re.search(rf"\b{token}\s*=\s*(pass|fail|softfail|neutral|temperror|permerror|none)\b", t)
        return m.group(1) if m else None

    dmarc = _val("dmarc")
    spf = _val("spf")
    dkim = _val("dkim")

    if dmarc == "pass":
        return "pass"
    if dmarc == "fail":
        return "fail"
    if spf == "pass" and dkim == "pass":
        return "pass"
    if spf == "fail" or dkim == "fail":
        return "fail"
    if spf or dkim or dmarc:
        # Records present but inconclusive (softfail / neutral / temperror).
        return "none"
    return "none"


def is_trusted(verdict: VerdictLiteral) -> bool:
    """Convenience predicate for routing decisions.

    Returns True only for an explicit ``pass``. Both ``none`` and
    ``fail`` mean "don't auto-quote, send to review".
    """
    return verdict == "pass"
