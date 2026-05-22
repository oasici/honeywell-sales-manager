"""Round-18 multi-email RFQ aggregation.

A spare-parts conversation often spans several emails:

  * Mail 1 — "Please quote 5x C7061A1012."
  * Mail 2 — "Sorry, add 2x RM7895A1014 as well."
  * Mail 3 — "Actually we want 10 of the first one."

Pre-Round-18 each mail produced its own ``EmailRequest`` + its own
draft quote. The salesperson then had to merge by hand. This module
resolves "which RFQ does this email belong to" via the existing
``thread_id`` (or sender + subject fallback) and exposes a single
helper, ``link_email_to_rfq``, that the
``EmailProcessingService.process_email`` path can call after the
parse step.

Linkage shape:

  * ``EmailRequest.rfq_thread_key`` — stable hash of
    ``(tenant_id, sender_domain, normalised_subject, thread_id)``.
    Mails carrying that key + with a ``spare_part_request`` parse
    share an RFQ.
  * Quote merging is **NOT** done by this service. We surface the
    aggregation key so downstream auto-quote logic (or the manual
    quote UI) can decide whether to extend an existing draft or
    open a new one.

The service is intentionally side-effect-free except for setting
``rfq_thread_key`` on the email row. It never mutates customer or
opportunity rows — those decisions live in the quote logic.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_request import EmailRequest

logger = logging.getLogger(__name__)


_REPLY_PREFIX_RE = re.compile(
    r"^\s*(?:re|fwd|fw|yt|ynt|iletme)\s*:\s*",
    re.IGNORECASE,
)


def _normalise_subject(subject: str | None) -> str:
    """Strip ``Re:``/``Fwd:`` prefixes + lowercase + collapse whitespace."""
    if not subject:
        return ""
    out = subject
    while True:
        nxt = _REPLY_PREFIX_RE.sub("", out, count=1)
        if nxt == out:
            break
        out = nxt
    return " ".join(out.lower().split())


def _sender_domain(from_address: str | None) -> str:
    """Lowercased domain part of an email address.

    Falls back to the full address when no ``@`` is present (rare —
    happens when the IMAP server presents a bare display name).
    """
    if not from_address:
        return ""
    if "@" not in from_address:
        return from_address.lower()
    return from_address.rsplit("@", 1)[-1].lower()


def compute_rfq_thread_key(email: EmailRequest) -> str:
    """Stable hash for one logical RFQ thread.

    Inputs (priority order):

      1. ``tenant_id`` — never mix RFQs across tenants.
      2. ``thread_id`` (Gmail / Outlook header) when present —
         that's the canonical conversation grouping.
      3. ``sender_domain + normalised_subject`` fallback when the
         upstream server didn't propagate ``thread_id`` (some
         self-hosted exchange installs strip it).

    Returns the first 16 hex chars of a SHA-256 digest. 16 hex
    gives 64 bits of entropy — collision-resistant for any real
    inbox size while staying short enough to store in a VARCHAR(32).
    """
    tenant = str(getattr(email, "tenant_id", "") or "")
    if email.thread_id:
        body = f"{tenant}|tid|{email.thread_id}"
    else:
        body = f"{tenant}|fallback|{_sender_domain(email.from_address)}|{_normalise_subject(email.subject)}"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


async def link_email_to_rfq(
    db: AsyncSession,
    email: EmailRequest,
) -> str | None:
    """Compute and persist the RFQ thread key on the email row.

    Returns the key on success, ``None`` when the email lacks the
    information needed (no thread_id and no usable subject).
    Idempotent: setting the same key twice is a no-op.
    """
    if email is None:
        return None
    # No usable signal — single-shot mail, won't aggregate.
    if not email.thread_id and not (email.subject or email.from_address):
        return None
    key = compute_rfq_thread_key(email)
    if getattr(email, "rfq_thread_key", None) != key:
        email.rfq_thread_key = key
        await db.flush()
    return key


async def list_emails_in_rfq(
    db: AsyncSession,
    rfq_thread_key: str,
    *,
    tenant_id: int | None = None,
) -> list[EmailRequest]:
    """Return every email tied to the same RFQ thread key.

    Tenant-scoped: the caller always passes ``tenant_id`` so cross-
    tenant pollution is impossible even if two domains happened to
    collide on the hash (vanishingly unlikely given the 16-hex
    digest).
    """
    from sqlalchemy import select

    stmt = select(EmailRequest).where(EmailRequest.rfq_thread_key == rfq_thread_key)
    if tenant_id is not None:
        stmt = stmt.where(EmailRequest.tenant_id == tenant_id)
    stmt = stmt.order_by(EmailRequest.received_at.asc())
    return list((await db.execute(stmt)).scalars().all())


def aggregate_parts(emails: Iterable[EmailRequest]) -> list[dict]:
    """Aggregate parts across a list of emails belonging to one RFQ.

    Sums quantities by ``part_code`` (case-insensitive). The
    description from the first email wins; later mentions only
    update quantity. Entries with empty ``part_code`` are kept
    separate (they don't merge — different descriptions might mean
    different parts).
    """
    import json

    out: dict[str, dict] = {}
    descr_only: list[dict] = []
    for email in emails:
        if not email.parsed_data:
            continue
        try:
            data = json.loads(email.parsed_data)
        except (json.JSONDecodeError, TypeError):
            continue
        for entry in (data.get("parts") if isinstance(data, dict) else None) or []:
            code = (entry.get("part_code") or "").strip()
            qty = int(entry.get("quantity") or 1)
            if not code:
                descr_only.append({**entry, "source_email_id": email.id})
                continue
            key = code.upper()
            if key in out:
                out[key]["quantity"] += qty
                out[key]["source_email_ids"].append(email.id)
            else:
                out[key] = {
                    **entry,
                    "part_code": code,
                    "quantity": qty,
                    "source_email_ids": [email.id],
                }
    aggregated = list(out.values()) + descr_only
    return aggregated
