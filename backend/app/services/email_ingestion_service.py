"""Shared inbound-email ingestion (email hardening audit E1/E2/E6/E7).

Both the manual ``POST /emails/poll`` endpoint and the scheduled IMAP
cron poll turn messages fetched by ``_fetch_emails_via_imap`` into
``EmailRequest`` rows. Before this module they each built the row
independently, and the **scheduled** path silently dropped
``sender_auth_status``, ``tenant_id``, and parsed ``attachments_json``
— letting spoofed senders reach the auto-quote gate (the
``if auth and auth != "pass"`` guard is a no-op on a NULL verdict),
losing spreadsheet/PDF RFQ rows, and leaving rows tenant-unattributed.

This is now the single row-construction path so the two callers can't
drift. It also:
  * runs OCR enrichment for image / scanned-PDF attachments (E-existing),
  * runs the AV scan hook on raw bytes and neutralizes infected
    attachments before their text can reach the LLM (E2),
  * applies the internal-domain skip on both paths (E6),
  * guards the INSERT with a SAVEPOINT so a concurrent-poll
    ``message_id`` race drops only that one row, not its siblings (E7).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.email_request import EmailRequest

logger = logging.getLogger(__name__)


def _is_internal(from_addr: str) -> bool:
    domain = (
        from_addr.rsplit("@", 1)[-1].lower() if "@" in (from_addr or "") else ""
    )
    return domain in settings.internal_domains_list


async def _is_duplicate(db: AsyncSession, message_id: str) -> bool:
    existing = await db.execute(
        select(EmailRequest.id).where(EmailRequest.message_id == message_id)
    )
    return existing.scalar_one_or_none() is not None


async def _enrich_ocr(item: dict, attachments_payload: list[dict]) -> list[dict]:
    """Run Claude Vision OCR on image / scanned-PDF attachments.

    Moved verbatim from the manual poll so both ingestion paths benefit.
    No-op without raw bytes, an API key, or an attachment that needs OCR.
    """
    raw_attachments = item.get("raw_attachments") or []
    if not (attachments_payload and raw_attachments and settings.ANTHROPIC_API_KEY):
        return attachments_payload

    needs_ocr = any(
        (a.get("error") == "requires_ocr")
        or (a.get("content_type") == "application/pdf" and not a.get("text"))
        for a in attachments_payload
    )
    if not needs_ocr:
        return attachments_payload

    from app.services.email_attachment_parser import (
        ParsedAttachment,
        enrich_with_ocr,
        extract_rows_as_parts,
    )

    placeholders = [
        ParsedAttachment(
            filename=a.get("filename", ""),
            content_type=a.get("content_type", ""),
            size_bytes=a.get("size_bytes", 0),
            text=a.get("text", ""),
            rows=[],
            sheet_count=a.get("sheet_count", 0) or 0,
            page_count=a.get("page_count", 0) or 0,
            error=a.get("error"),
        )
        for a in attachments_payload
    ]
    enriched = await enrich_with_ocr(raw_attachments, placeholders)
    return [
        {
            "filename": pa.filename,
            "content_type": pa.content_type,
            "size_bytes": pa.size_bytes,
            "sheet_count": pa.sheet_count,
            "page_count": pa.page_count,
            "total_pages": pa.total_pages,
            "truncated": pa.truncated,
            "text": pa.text,
            "heuristic_parts": extract_rows_as_parts(pa.rows) if pa.rows else [],
            "error": pa.error,
        }
        for pa in enriched
    ]


def _apply_av_scan(item: dict, attachments_payload: list[dict]) -> bool:
    """Scan raw attachment bytes; annotate verdicts; neutralize infected.

    Returns ``True`` if any attachment scanned ``infected``. Infected
    attachments have their ``text`` + ``heuristic_parts`` cleared so the
    malicious content never reaches the LLM prompt or the quote. With
    the default ``_NoopScanner`` every verdict is ``unscanned`` → no
    behavioural change until ops sets ``AV_SCAN_BACKEND``.
    """
    raw_attachments = item.get("raw_attachments") or []
    if not raw_attachments or not attachments_payload:
        return False

    from app.services.email_av_scanner import scan_attachments

    verdicts = {v.filename: v for v in scan_attachments(raw_attachments)}
    any_infected = False
    for a in attachments_payload:
        verdict = verdicts.get(a.get("filename"))
        if verdict is None:
            continue
        a["av_status"] = verdict.status
        a["av_backend"] = verdict.backend
        if verdict.status == "infected":
            any_infected = True
            a["av_details"] = verdict.details
            a["text"] = ""
            a["heuristic_parts"] = []
    return any_infected


def _compute_truncation(attachments_payload: list[dict]) -> tuple[bool, int | None]:
    any_truncated = any(bool(a.get("truncated")) for a in attachments_payload)
    if not any_truncated:
        return False, None
    total = sum(
        int(a.get("total_pages") or 0)
        for a in attachments_payload
        if a.get("truncated")
    )
    rendered = sum(
        int(a.get("page_count") or 0)
        for a in attachments_payload
        if a.get("truncated")
    )
    return True, total - rendered


async def ingest_fetched_email(
    db: AsyncSession,
    item: dict,
    *,
    tenant_id: int | None,
    assigned_to: int | None,
    enrich_ocr: bool = True,
) -> EmailRequest | None:
    """Build + persist one ``EmailRequest`` from a fetched IMAP message.

    Returns the flushed row, or ``None`` when the message is skipped
    (internal domain, junk/bulk sender, duplicate, or concurrent-insert race).
    """
    from_addr = item.get("from_addr", "")
    if _is_internal(from_addr):
        return None

    # Junk / bulk pre-LLM filter (RFC 3834): newsletters, receipts, promos,
    # and no-reply senders are dropped here — zero Claude cost, no queue
    # clutter. A real RFQ never trips these signals.
    from app.services.junk_filter import is_junk_email

    is_junk, junk_reason = is_junk_email(from_addr, is_bulk=bool(item.get("is_bulk")))
    if is_junk:
        logger.info(
            "Skipping junk email from %s (%s): %s",
            from_addr,
            junk_reason,
            (item.get("subject") or "")[:80],
        )
        return None

    message_id = item.get("message_id")
    if not message_id or await _is_duplicate(db, message_id):
        return None

    attachments_payload = list(item.get("attachments") or [])
    if enrich_ocr:
        attachments_payload = await _enrich_ocr(item, attachments_payload)
    av_infected = _apply_av_scan(item, attachments_payload)

    attachments_json = None
    if attachments_payload:
        try:
            attachments_json = json.dumps(attachments_payload, ensure_ascii=False)
        except Exception:
            attachments_json = None

    any_truncated, ocr_skipped = _compute_truncation(attachments_payload)
    sender_auth = item.get("sender_auth_status") or "none"
    # Untrusted sender OR an infected attachment forces the human queue.
    review_status = (
        None if (sender_auth == "pass" and not av_infected) else "pending_review"
    )

    email = EmailRequest(
        message_id=message_id,
        from_address=from_addr,
        subject=item.get("subject") or "(Konu yok)",
        body_text=item.get("body", ""),
        body_html=item.get("html_body") or None,
        status="new",
        is_read=item.get("is_read", False),
        received_at=datetime.now(timezone.utc),
        assigned_to=assigned_to,
        tenant_id=tenant_id,
        attachments_json=attachments_json,
        sender_auth_status=sender_auth,
        review_status=review_status,
        attachment_pages_truncated=any_truncated,
        ocr_skipped_pages=ocr_skipped,
        parse_skipped_reason="av_infected" if av_infected else None,
    )

    # SAVEPOINT so a concurrent-poll message_id collision rolls back only
    # this row, not the sibling inserts already flushed in this txn (E7).
    try:
        async with db.begin_nested():
            db.add(email)
            await db.flush()
    except IntegrityError:
        logger.info(
            "Idempotency: message_id %s already inserted (concurrent fetch). Skipping.",
            message_id,
        )
        return None

    await db.refresh(email)
    return email
