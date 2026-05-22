"""Round-18 thread-aware context for Claude email parsing.

Closes the "previous-email context" gap from the coverage audit.
Pre-Round-18, every email was parsed in isolation:

  > Customer Mail 1: "Hi, please quote 5x C7061A1012"
  > Customer Mail 2: "Add 2 more of the same, please."

The second mail produces an empty parse because Claude has no idea
what "the same" refers to. With thread context, mail 2's prompt
includes mail 1's body + parsed parts as "Previous correspondence
in this thread" so Claude can resolve the pronoun.

Lookup strategy (cheap, no LLM cost):

  * Same ``thread_id`` (Gmail / Outlook / generic IMAP threading header).
  * Same sender + recipient + similar subject (Re:/Fwd: stripped),
    within ``THREAD_LOOKBACK_DAYS``, when ``thread_id`` is NULL.
  * Cap at ``MAX_THREAD_HISTORY`` messages; prefer most recent.

The previous-email block is built as markdown sections so Claude
sees the structure rather than a wall of text:

  ## Previous email · 2026-05-21
  **Subject:** RFQ for boiler retrofit
  **Parts already known:** C7061A1012 (×5)
  **Body excerpt:**
  Hi, please quote 5x C7061A1012 for the Karşıyaka boiler...

The block is *prepended* to the current message, with a clear
separator. Token cost is bounded by the lookback cap + per-mail
body truncation (``MAX_BODY_EXCERPT_CHARS``).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_request import EmailRequest

logger = logging.getLogger(__name__)


THREAD_LOOKBACK_DAYS = 14
MAX_THREAD_HISTORY = 5
MAX_BODY_EXCERPT_CHARS = 600


# ── Subject normalisation for thread fallback ─────────────────────


_REPLY_PREFIX_RE = re.compile(
    r"^\s*(?:re|fwd|fw|yt|ynt|iletme)\s*:\s*",
    re.IGNORECASE,
)


def _strip_reply_prefix(subject: str) -> str:
    """Iteratively strip ``Re:`` / ``Fwd:`` / ``YT:`` (Türkçe) /
    ``İletme:`` prefixes so two threads with the same conversation
    base collapse to the same key."""
    out = subject or ""
    while True:
        nxt = _REPLY_PREFIX_RE.sub("", out, count=1)
        if nxt == out:
            break
        out = nxt
    return out.strip()


# ── Lookup ────────────────────────────────────────────────────────


async def fetch_thread_history(
    db: AsyncSession,
    email: EmailRequest,
    *,
    lookback_days: int = THREAD_LOOKBACK_DAYS,
    max_results: int = MAX_THREAD_HISTORY,
) -> list[EmailRequest]:
    """Return previous EmailRequest rows in this thread, newest first.

    Excludes the current email (``email.id``) so the caller doesn't
    re-feed its own body into the prompt.
    """
    if email is None or not email.id:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    base = select(EmailRequest).where(EmailRequest.id != email.id)
    # Tenant guard — never pull cross-tenant history.
    if getattr(email, "tenant_id", None) is not None:
        base = base.where(EmailRequest.tenant_id == email.tenant_id)
    if email.received_at is not None:
        base = base.where(EmailRequest.received_at >= cutoff)
        base = base.where(EmailRequest.received_at <= email.received_at)

    if email.thread_id:
        stmt = base.where(EmailRequest.thread_id == email.thread_id)
    else:
        # Fallback: same sender + similar normalized subject.
        if not email.from_address:
            return []
        normalized = _strip_reply_prefix(email.subject or "").lower()
        if not normalized:
            return []
        stmt = base.where(
            and_(
                EmailRequest.from_address == email.from_address,
                or_(
                    EmailRequest.subject.ilike(normalized),
                    EmailRequest.subject.ilike(f"%{normalized}%"),
                ),
            )
        )

    stmt = stmt.order_by(EmailRequest.received_at.desc()).limit(max_results)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


# ── Context block builder ────────────────────────────────────────


def build_thread_prompt_block(history: list[EmailRequest]) -> str:
    """Render the history as a markdown block for the LLM prompt.

    Returns an empty string when ``history`` is empty so the caller
    can concatenate without worrying about extra separators.
    """
    if not history:
        return ""
    sections: list[str] = ["# Previous correspondence in this thread"]
    # Walk newest-first → oldest so the LLM reads in reverse-chrono;
    # the immediately-prior email is closest to the current prompt.
    for prior in history:
        sections.append(_format_prior(prior))
    return "\n\n".join(sections)


def _format_prior(email: EmailRequest) -> str:
    when = ""
    if email.received_at:
        when = email.received_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts_known = _parts_summary(email)
    excerpt = (email.body_text or "")[:MAX_BODY_EXCERPT_CHARS]
    if email.body_text and len(email.body_text) > MAX_BODY_EXCERPT_CHARS:
        excerpt = excerpt.rstrip() + " …"
    lines: list[str] = [
        f"## Previous email · {when or '(time unknown)'}",
        f"**From:** {email.from_address}",
        f"**Subject:** {email.subject or '(no subject)'}",
    ]
    if parts_known:
        lines.append(f"**Parts already known:** {parts_known}")
    lines.append("")
    lines.append("**Body excerpt:**")
    lines.append(excerpt or "_(empty body)_")
    return "\n".join(lines)


def _parts_summary(email: EmailRequest) -> str:
    """One-line summary of the previously-parsed parts on an email."""
    raw = email.parsed_data
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ""
    parts = data.get("parts") if isinstance(data, dict) else None
    if not parts:
        return ""
    bits: list[str] = []
    for p in parts[:8]:
        code = (p.get("part_code") or "").strip() or "?"
        qty = p.get("quantity") or 1
        desc = (p.get("part_description") or "").strip()
        if desc and code == "?":
            bits.append(f"{desc[:40]} (×{qty})")
        else:
            bits.append(f"{code} (×{qty})")
    if len(parts) > 8:
        bits.append(f"+{len(parts) - 8} more")
    return ", ".join(bits)


async def prepend_thread_context(
    db: AsyncSession,
    email: EmailRequest,
    body: str,
) -> str:
    """Convenience helper for ``EmailProcessingService``: returns the
    body augmented with the thread block (or the body unchanged
    when there's no history).
    """
    history = await fetch_thread_history(db, email)
    if not history:
        return body
    block = build_thread_prompt_block(history)
    if not block:
        return body
    return f"{block}\n\n---\n\n# Current email\n\n{body}"
