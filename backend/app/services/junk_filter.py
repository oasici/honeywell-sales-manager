"""Cheap junk / bulk sender filter (pre-LLM).

Newsletters, receipts, order confirmations, and promotions are not parts
RFQs — and per **RFC 3834** an automated responder (we auto-quote) must
not act on bulk / auto-generated mail. Detecting them by sender + bulk
headers lets us drop them BEFORE the Claude call: zero LLM cost, and they
never clutter the RFQ review queue.

Conservative by design — a human writing an RFQ:
  * never sends from a ``no-reply`` / ``mailer-daemon`` address, and
  * never carries ``List-Unsubscribe`` / ``List-Id`` / ``Precedence: bulk``
    / ``Auto-Submitted`` headers.
So legitimate requests pass through untouched. Operators can extend the
match list via ``EMAIL_JUNK_SENDER_PATTERNS`` or disable the filter with
``EMAIL_JUNK_FILTER_ENABLED=false``.
"""

from __future__ import annotations

import re

from app.core.config import settings

# Automated / no-reply localparts. These are never used by a person
# sending a quote request, so finding one anywhere in the localpart (e.g.
# ``testflight_no_reply``) is a safe "junk" signal. Kept tight + specific
# to avoid matching real names; broader bulk mail is caught by headers.
_NOREPLY_LOCALPART = re.compile(
    r"(no[-_.]?reply|do[-_.]?not[-_.]?reply|mailer[-_.]?daemon|mdaemon|postmaster)",
    re.IGNORECASE,
)


def _localpart(addr: str) -> str:
    addr = (addr or "").strip().lower()
    return addr.split("@", 1)[0] if "@" in addr else addr


def is_bulk_headers(
    *,
    list_unsubscribe: str | None = None,
    list_id: str | None = None,
    precedence: str | None = None,
    auto_submitted: str | None = None,
) -> bool:
    """RFC 3834 / RFC 2919 bulk-mail detection from raw header values."""
    if list_unsubscribe or list_id:
        return True
    if (precedence or "").strip().lower() in {"bulk", "list", "junk"}:
        return True
    auto = (auto_submitted or "").strip().lower()
    if auto and auto not in {"no", "none"}:
        return True
    return False


def is_junk_email(from_addr: str, *, is_bulk: bool = False) -> tuple[bool, str | None]:
    """Classify a fetched message. Returns ``(is_junk, reason)``.

    ``reason`` is a stable short code for logging / audit:
    ``bulk_mail`` | ``noreply_sender`` | ``junk_sender``.
    """
    if not settings.EMAIL_JUNK_FILTER_ENABLED:
        return False, None

    if is_bulk:
        return True, "bulk_mail"

    if _NOREPLY_LOCALPART.search(_localpart(from_addr)):
        return True, "noreply_sender"

    addr = (from_addr or "").lower()
    for pattern in settings.junk_sender_patterns:
        if pattern and pattern in addr:
            return True, "junk_sender"

    return False, None
