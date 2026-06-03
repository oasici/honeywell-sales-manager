"""Service layer for email parsing and processing workflows."""

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.models.email_request import EmailRequest
from app.models.enums import EmailStatus, ReviewStatus
from app.services.parse_metrics import (
    ESTIMATED_COST_PER_CALL,
    elapsed_ms,
    log_parse_metrics,
)
from app.services.regex_fallback_parser import (
    pre_filter_email,
    regex_fallback_parse,
)

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.75
ERROR_MESSAGE_MAX_LENGTH = 500


def _auto_quote_eligible(
    email: EmailRequest,
    parsed: dict,
    tenant_config=None,
) -> tuple[bool, str | None]:
    """Round-19 gate for the auto-quote happy path.

    Returns ``(eligible, block_reason)``. ``block_reason`` is a stable
    short code so callers/audit logs can branch on it:

      * ``auth_not_pass``       — F-002. SPF/DKIM/DMARC didn't return pass.
      * ``ocr_truncated``       — F-003. A PDF attachment had more pages
                                   than ``MAX_OCR_PAGES``; the parse saw
                                   only the head.
      * ``first_time_sender``   — F-004. The sender's address isn't in
                                   the customers table for this tenant.
                                   Trust-on-first-use → manual review.
      * ``value_above_threshold`` — F-029. Sum of line items exceeds the
                                   per-tenant ``auto_quote_max_amount``.
                                   Big deals always require a human.
      * ``fuzzy_or_unknown``    — Round-17 rule. A part landed at fuzzy
                                   / unknown catalog status. Sending a
                                   fuzzy SKU bound to the customer's
                                   account is a real-money mistake.

    Pre-Round-19 this was a bare bool and two callers invoked it as
    ``self._auto_quote_eligible(...)`` — an attribute error that
    silently failed-closed. The new shape forces callers to pass through
    a stable reason for audit + UI.

    ``tenant_config`` is an optional ``TenantConfig`` snapshot. When
    omitted (legacy unit tests), the F-029 amount check is skipped.
    """
    # E2 — an attachment that scanned ``infected`` at ingest time
    # (``parse_skipped_reason == "av_infected"``) never auto-quotes; the
    # infected file's text was already stripped, but the whole email
    # still routes to a human.
    if getattr(email, "parse_skipped_reason", None) == "av_infected":
        return False, "av_infected"
    auth = getattr(email, "sender_auth_status", None)
    if auth and auth != "pass":
        return False, "auth_not_pass"
    if getattr(email, "attachment_pages_truncated", False):
        return False, "ocr_truncated"
    if getattr(email, "first_time_sender", False):
        return False, "first_time_sender"
    # F-029 — per-tenant max-amount cap. ``estimate_quote_total`` is
    # best-effort (the parser may not surface prices yet); only enforce
    # when both a cap and a positive estimate are available.
    if tenant_config is not None and tenant_config.auto_quote_max_amount is not None:
        from app.services.tenant_settings_service import estimate_quote_total

        est = estimate_quote_total(parsed)
        if est > 0 and est > tenant_config.auto_quote_max_amount:
            return False, "value_above_threshold"
    for p in parsed.get("parts") or []:
        # R1 — a quantity we couldn't pin down (out-of-range, unparseable,
        # or body↔attachment conflict) must never auto-quote. The flags are
        # set by extract_rows_as_parts / _merge_heuristic_parts upstream.
        if p.get("quantity_conflict") or p.get("quantity_suspect"):
            return False, "quantity_uncertain"
        status = p.get("catalog_status")
        # ``no_code`` means the LLM emitted a description-only entry.
        # That can't auto-quote either.
        if status not in {"exact", "normalized"}:
            return False, "fuzzy_or_unknown"
    return True, None


def _bound_llm_input(current_blob: str, threaded: str, max_input: int) -> str:
    """R3 — assemble the LLM prompt under ``max_input`` chars without ever
    sacrificing the current email.

    ``threaded`` is ``[older thread history] + [current email]`` (thread
    first). A naive ``[:max_input]`` would keep the stale history and drop
    the current email's tail (its attachments). Instead keep the current
    email intact and trim the older history to whatever budget remains.
    """
    if not max_input or len(threaded) <= max_input:
        return threaded
    budget = max_input - len(current_blob)
    if budget > 0:
        return (
            threaded[:budget]
            + "\n\n[...earlier thread truncated...]\n\n"
            + current_blob
        )
    return current_blob


def _as_int_qty(value) -> int | None:
    """Best-effort int coercion for a quantity field; None if not numeric."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _merge_heuristic_parts(parsed: dict, heuristic_rows: list[dict]) -> dict:
    """Merge attachment-derived heuristic part rows into the LLM result.

    Phase-4 (spare-parts audit Q3/Q4):

      * Dedup is by **normalized** code (reusing the catalog resolver's
        normalizer) so ``C7061A1012`` (LLM/body) and ``C7061-A1012``
        (spreadsheet) collapse to one physical part instead of two lines.
      * When the same part appears in both the body and an attachment with
        **different** quantities, neither value is silently discarded:
        the line is flagged ``quantity_suspect`` and both values are
        surfaced under ``quantity_conflict`` for the operator to resolve.

    Also flips ``is_spare_part_request`` to True when the attachment
    contributed part rows the LLM missed entirely.
    """
    if not heuristic_rows:
        return parsed

    from app.services.part_catalog_resolver import _normalize

    parsed = dict(parsed or {})
    parts = list(parsed.get("parts") or [])

    # Map normalized code -> index of the existing (body/LLM) part.
    index: dict[str, int] = {}
    for idx, p in enumerate(parts):
        code = p.get("part_code")
        if code:
            index[_normalize(code)] = idx

    appended = 0
    for hp in heuristic_rows:
        code = (hp.get("part_code") or "").strip()
        if not code:
            continue
        norm = _normalize(code)
        if norm in index:
            # Q4 — same physical part already present. Don't append a
            # duplicate (Q3); instead reconcile the quantity.
            existing = parts[index[norm]]
            body_qty = _as_int_qty(existing.get("quantity"))
            attach_qty = _as_int_qty(hp.get("quantity"))
            if (
                body_qty is not None
                and attach_qty is not None
                and body_qty != attach_qty
            ):
                existing["quantity_conflict"] = {
                    "body": body_qty,
                    "attachment": attach_qty,
                }
                existing["quantity_suspect"] = True
            continue

        new_part = {
            "part_code": code,
            "part_description": hp.get("part_description", ""),
            "quantity": hp.get("quantity") or 1,
            "urgency": "normal",
        }
        if hp.get("quantity_suspect"):
            new_part["quantity_suspect"] = True
        parts.append(new_part)
        index[norm] = len(parts) - 1
        appended += 1

    # Persist mutations (conflict flags) regardless of whether new rows
    # were appended.
    parsed["parts"] = parts
    if appended:
        parsed["is_spare_part_request"] = True
        # Don't artificially raise confidence — the LLM's own score
        # remains; the operator sees "N parts via attachment" in the
        # parsed_data review surface.
    return parsed


class EmailProcessingService:
    """Encapsulates email parsing, classification, and review workflows."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def process_email(self, email_id: int) -> EmailRequest:
        """Full pipeline: pre-filter, parse, classify, set review status."""
        email = await self._get_email_or_raise(email_id)

        email.status = EmailStatus.NEW.value
        email.parsed_data = None
        email.error_message = None
        await self._db.flush()

        # F-002 — auth=fail short-circuit. Skip the LLM entirely. We
        # still create the EmailRequest row (so the operator can see it
        # in the review queue with the red banner), but the spoof gets
        # no Anthropic spend and no parsed parts. A manager may later
        # force-parse via the override path.
        if (email.sender_auth_status or "").lower() == "fail":
            email.parse_skipped_reason = "auth_failed"
            email.status = EmailStatus.NEW.value
            email.review_status = ReviewStatus.PENDING_REVIEW.value
            await self._db.flush()
            await self._db.refresh(email)
            return email

        # F-004 — first-time-sender detection. We compute this *before*
        # the parse so the gate (and any future per-sender policies)
        # have it. Tenant-scoped lookup; a sender already a customer
        # in another tenant doesn't count.
        await self._mark_first_time_sender(email)

        try:
            parsed = await self._parse_email_with_fallback(email)
            if parsed:
                # Round-17 — annotate every part with catalog verdict
                # BEFORE persistence + auto-quote. Unknown / fuzzy
                # rows route to review even when the LLM was confident.
                if parsed.get("parts"):
                    from app.services.part_catalog_resolver import (
                        dedupe_parsed_parts,
                        resolve_parsed_parts,
                    )

                    parsed["parts"] = await resolve_parsed_parts(
                        self._db,
                        parsed["parts"],
                        tenant_id=getattr(email, "tenant_id", None),
                    )
                    # T2 — collapse same-SKU duplicates (summed qty, flagged
                    # for review) before the gate so R1 catches the merge.
                    parsed["parts"] = dedupe_parsed_parts(parsed["parts"])
                    # R2 — stamp catalog sell prices so the auto-quote
                    # value cap (estimate_quote_total) reflects real money.
                    await self._annotate_catalog_sell_prices(parsed)
                self._apply_parsed_data(email, parsed)
                self._classify_with_consolidation(email, parsed)
                await self._set_review_status(email, parsed)

                # Round-18 — link this email to its RFQ thread. Best-
                # effort: the helper returns None when the email
                # lacks both ``thread_id`` and a usable subject.
                try:
                    from app.services.email_rfq_aggregator import link_email_to_rfq

                    await link_email_to_rfq(self._db, email)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "RFQ thread linking failed for email %d (non-fatal): %s",
                        email.id,
                        exc,
                    )

                # Round-17 — gate auto-quote on:
                #  1. review_status APPROVED (existing rule)
                #  2. sender_auth_status == pass (SPF/DKIM/DMARC)
                #  3. every parsed part resolved to a real catalog row
                # Failure on any axis routes to review queue.
                if email.review_status == ReviewStatus.APPROVED.value:
                    from app.services.tenant_settings_service import (
                        get_tenant_settings,
                    )

                    tenant_cfg = await get_tenant_settings(
                        self._db, getattr(email, "tenant_id", None)
                    )
                    eligible, reason = _auto_quote_eligible(
                        email, parsed, tenant_config=tenant_cfg
                    )
                    if not eligible:
                        email.review_status = ReviewStatus.PENDING_REVIEW.value
                        # Stash the reason on the row so the operator
                        # UI can show a precise "blocked because X"
                        # banner instead of a generic "needs review".
                        email.parse_skipped_reason = reason
                    else:
                        await self._auto_create_customer(email, parsed)
                        if parsed.get("parts") and parsed.get("confidence", 0) >= 0.7:
                            await self._auto_create_draft_quote(email, parsed)
            else:
                email.status = EmailStatus.ERROR.value
                email.error_message = "Parse returned empty"
        except Exception as exc:
            logger.exception("Failed to process email %d", email_id)
            email.status = EmailStatus.ERROR.value
            error_str = str(exc)
            if len(error_str) > ERROR_MESSAGE_MAX_LENGTH:
                email.error_message = error_str[:ERROR_MESSAGE_MAX_LENGTH] + "..."
            else:
                email.error_message = error_str
            # D-028 — route exhausted-retry failures to the DLQ so
            # Operations can triage from /admin/dlq instead of having
            # to grep `email.status=error` rows by hand. Best-effort;
            # never block the email row update on a DLQ insert glitch.
            await self._write_email_failure_to_dlq(email, exc)

        await self._db.flush()
        await self._db.refresh(email)

        return email

    async def create_manual_email(
        self,
        from_address: str,
        subject: str | None,
        body_text: str,
        assigned_to: int | None = None,
    ) -> EmailRequest:
        """Create a manual email entry and trigger parsing."""
        email = EmailRequest(
            message_id=f"manual-{uuid.uuid4().hex}",
            from_address=from_address,
            subject=subject or "(No Subject)",
            body_text=body_text,
            status=EmailStatus.NEW.value,
            received_at=datetime.now(timezone.utc),
            assigned_to=assigned_to,
        )
        self._db.add(email)
        await self._db.flush()
        await self._db.refresh(email)

        try:
            parsed = await self._parse_email_with_fallback(email)
            if parsed:
                if parsed.get("parts"):
                    from app.services.part_catalog_resolver import (
                        dedupe_parsed_parts,
                        resolve_parsed_parts,
                    )

                    parsed["parts"] = await resolve_parsed_parts(
                        self._db,
                        parsed["parts"],
                        tenant_id=getattr(email, "tenant_id", None),
                    )
                    parsed["parts"] = dedupe_parsed_parts(parsed["parts"])
                    await self._annotate_catalog_sell_prices(parsed)
                self._apply_parsed_data(email, parsed)
                self._classify_with_consolidation(email, parsed)
                await self._set_review_status(email, parsed)

                # Round-17 — same eligibility gate as ``process_email``.
                if email.review_status == ReviewStatus.APPROVED.value:
                    from app.services.tenant_settings_service import (
                        get_tenant_settings,
                    )

                    tenant_cfg = await get_tenant_settings(
                        self._db, getattr(email, "tenant_id", None)
                    )
                    eligible, reason = _auto_quote_eligible(
                        email, parsed, tenant_config=tenant_cfg
                    )
                    if not eligible:
                        email.review_status = ReviewStatus.PENDING_REVIEW.value
                        # Stash the reason on the row so the operator
                        # UI can show a precise "blocked because X"
                        # banner instead of a generic "needs review".
                        email.parse_skipped_reason = reason
                    else:
                        await self._auto_create_customer(email, parsed)
                        if parsed.get("parts") and parsed.get("confidence", 0) >= 0.7:
                            await self._auto_create_draft_quote(email, parsed)

                await self._db.flush()
                await self._db.refresh(email)
        except Exception as exc:
            logger.exception("Failed to parse manual email %d", email.id)
            email.status = EmailStatus.ERROR.value
            error_str = str(exc)
            if len(error_str) > ERROR_MESSAGE_MAX_LENGTH:
                email.error_message = error_str[:ERROR_MESSAGE_MAX_LENGTH] + "..."
            else:
                email.error_message = error_str
            # D-028 — same DLQ routing as process_email so manual-entry
            # failures are visible to Operations alongside IMAP failures.
            await self._write_email_failure_to_dlq(email, exc)
            await self._db.flush()
            await self._db.refresh(email)

        return email

    # ---- Private helpers ----

    async def _write_email_failure_to_dlq(
        self, email: EmailRequest, exc: Exception
    ) -> None:
        """D-028 — best-effort DLQ writer for email pipeline failures.

        Uses a separate AsyncSession so a DLQ-write blip cannot taint
        the original transaction that is updating the email row. If
        DLQ writing itself fails, swallow the error — we already logged
        the original exception above; losing the DLQ entry is a
        visibility regression, not a correctness one.
        """
        try:
            from app.core.database import async_session
            from app.services.dlq_service import write_to_dlq

            payload = {
                "email_id": getattr(email, "id", None),
                "tenant_id": getattr(email, "tenant_id", None),
                "from_address": getattr(email, "from_address", None),
                "subject": (getattr(email, "subject", None) or "")[:200],
                "message_id": getattr(email, "message_id", None),
            }
            async with async_session() as dlq_db:
                await write_to_dlq(
                    dlq_db,
                    job_name="email_parser_pipeline",
                    error=str(exc),
                    payload=payload,
                )
                await dlq_db.commit()
        except Exception as dlq_exc:  # noqa: BLE001
            logger.warning(
                "DLQ write failed for email %s (non-fatal): %s",
                getattr(email, "id", "?"),
                dlq_exc,
            )

    async def _mark_first_time_sender(self, email: EmailRequest) -> None:
        """F-004 — set ``first_time_sender`` based on Customer lookup.

        Tenant-scoped: a sender already known to another tenant doesn't
        count as "known" for this tenant. Address comparison is
        case-insensitive on the local-part and host. Idempotent — safe
        to call multiple times.
        """
        sender = (email.from_address or "").strip().lower()
        if not sender:
            email.first_time_sender = True
            return

        from app.models.customer import Customer

        stmt = select(Customer.id).where(
            Customer.email.ilike(sender),
        )
        tenant_id = getattr(email, "tenant_id", None)
        if tenant_id is not None:
            stmt = stmt.where(Customer.tenant_id == tenant_id)
        stmt = stmt.limit(1)
        result = await self._db.execute(stmt)
        match = result.scalar_one_or_none()
        email.first_time_sender = match is None

    async def _get_email_or_raise(self, email_id: int) -> EmailRequest:
        result = await self._db.execute(
            select(EmailRequest).where(EmailRequest.id == email_id)
        )
        email = result.scalar_one_or_none()
        if not email:
            raise NotFoundException(f"{email_id} numarali e-posta bulunamadi")
        return email

    async def _annotate_catalog_sell_prices(self, parsed: dict) -> None:
        """R2 — stamp each resolved part's catalog sell price onto the
        parsed dict so the auto-quote value cap reflects real money.

        Prices are taken from the spare-parts catalog (``PriceEntry`` /
        cost+margin via ``resolve_unit_price``), never from the email —
        customer RFQs don't contain prices, so without this the F-029
        per-tenant max-amount cap saw a total of 0 and never fired.

        Best-effort: parts without a resolved ``catalog_part_id`` or with
        no safe price are left unpriced and simply don't contribute to the
        estimate. ``create_quote_from_email`` re-prices independently, so
        this annotation only feeds the gate's estimate.
        """
        from app.models.spare_part import SparePart
        from app.services.part_pricing import resolve_unit_price_with_currency

        # T5 — email-derived quotes use the Quote default currency (TRY), so
        # convert each catalog price into that currency before stamping.
        # Otherwise a USD catalog estimate compared against a TRY cap
        # under-counts ~30× and a big order slips the value gate. Best-
        # effort: if FX is unavailable we keep the raw price (the estimate
        # is advisory; the line price is reconciled separately in R4).
        target_ccy = "TRY"
        for part_req in parsed.get("parts") or []:
            part_id = part_req.get("catalog_part_id")
            if not part_id:
                continue
            part = (
                await self._db.execute(
                    select(SparePart).where(SparePart.id == part_id)
                )
            ).scalar_one_or_none()
            if part is None:
                continue
            price, _source, src_ccy = resolve_unit_price_with_currency(part)
            if price <= 0:
                continue
            if src_ccy and src_ccy.upper() != target_ccy:
                try:
                    from app.services.currency_service import convert_currency

                    price = await convert_currency(price, src_ccy, target_ccy)
                except Exception:  # noqa: BLE001 — estimate is best-effort
                    pass
            part_req["unit_price"] = price

    async def _scan_for_catalog_codes(self, text: str) -> list[dict]:
        """F-A — recover catalog codes present in ``text`` that pattern-based
        extraction (and a Claude outage's regex fallback) would miss. Matches
        against the active catalog, so only real SKUs are added."""
        if not text:
            return []
        from app.models.spare_part import SparePart
        from app.services.catalog_code_scanner import scan_text_for_catalog_codes
        from app.services.part_catalog_resolver import _normalize

        rows = (
            await self._db.execute(
                select(SparePart.honeywell_code).where(SparePart.is_active.is_(True))
            )
        ).all()
        norm_to_code = {
            _normalize(r[0]): r[0] for r in rows if r and r[0]
        }
        return scan_text_for_catalog_codes(text, norm_to_code)

    async def _parse_email_with_fallback(
        self,
        email: EmailRequest,
    ) -> dict | None:
        """Parse with pre-filtering, Claude API, and regex fallback.

        Round-17 — attachments parsed at IMAP-fetch time
        (``attachments_json`` column) are merged into the LLM
        prompt via ``email_attachment_parser.merge_for_llm`` so
        Excel / CSV / PDF part lists land in the same Claude call
        as the body text. The heuristic_parts captured per
        attachment are appended to the regex-fallback result so a
        Claude outage doesn't lose the structured rows.
        """
        body = email.body_text or email.body_html or ""
        subject = email.subject or ""
        start_time = time.monotonic()

        # Merge attachment text into the LLM prompt body.
        attachment_payloads: list[dict] = []
        attachment_text_blob = ""
        heuristic_rows: list[dict] = []
        attachments_raw = getattr(email, "attachments_json", None)
        if attachments_raw:
            try:
                attachment_payloads = json.loads(attachments_raw) or []
            except Exception:
                attachment_payloads = []
        if attachment_payloads:
            from app.services.email_attachment_parser import (
                ParsedAttachment,
                merge_for_llm,
            )

            recon: list[ParsedAttachment] = []
            for entry in attachment_payloads:
                recon.append(
                    ParsedAttachment(
                        filename=entry.get("filename", ""),
                        content_type=entry.get("content_type", ""),
                        size_bytes=entry.get("size_bytes", 0),
                        text=entry.get("text", ""),
                        rows=[],  # not persisted; heuristic_parts is what we need
                        sheet_count=entry.get("sheet_count", 0) or 0,
                        page_count=entry.get("page_count", 0) or 0,
                        error=entry.get("error"),
                    )
                )
                for hp in entry.get("heuristic_parts") or []:
                    heuristic_rows.append(hp)
            attachment_text_blob = merge_for_llm(
                body, recon, max_attachment_chars=settings.AI_MAX_ATTACHMENT_CHARS
            )

        max_input = settings.AI_MAX_INPUT_CHARS

        # The current email (body + attachments) is what we're quoting, so
        # it must survive the token cap. Per-attachment caps already bound
        # it; truncate here only in the pathological case where the current
        # email alone exceeds the ceiling.
        current_blob = attachment_text_blob or body

        # F-A — catalog-aware code recovery on the current email text. Codes
        # the LLM misses (or that a Claude outage hands to the pattern-blind
        # regex fallback) are merged in via the same heuristic-merge path
        # (deduped by normalized code). Scans the current email only, never
        # the prepended thread history.
        catalog_rows = await self._scan_for_catalog_codes(current_blob)
        if catalog_rows:
            heuristic_rows = list(heuristic_rows) + catalog_rows

        if max_input and len(current_blob) > max_input:
            logger.info(
                "Email %d current-email LLM input truncated %d->%d chars",
                email.id,
                len(current_blob),
                max_input,
            )
            current_blob = current_blob[:max_input] + "\n\n[...truncated for length...]"

        # Round-18 — prepend thread history when this email belongs to an
        # ongoing conversation (pronoun resolution / dedupe). R3 — thread
        # history is prepended at the FRONT, so a naive tail-truncation
        # would discard the current email and keep stale history. Instead
        # keep the current email intact and trim the OLDER thread history
        # to whatever budget remains under the cap.
        llm_input_body = current_blob
        try:
            from app.services.email_thread_context import prepend_thread_context

            threaded = await prepend_thread_context(self._db, email, current_blob)
            llm_input_body = _bound_llm_input(current_blob, threaded, max_input)
            if max_input and len(threaded) > max_input:
                logger.info(
                    "Email %d thread context trimmed to fit %d-char cap",
                    email.id,
                    max_input,
                )
        except Exception as exc:  # noqa: BLE001 — thread context is best-effort
            logger.warning(
                "Thread-context lookup failed for email %d (continuing without): %s",
                email.id,
                exc,
            )
            llm_input_body = current_blob

        filter_result = pre_filter_email(llm_input_body, subject)

        if filter_result == "skip":
            log_parse_metrics(
                email_id=email.id,
                duration_ms=0,
                parts_count=0,
                confidence=0.0,
                category="general_inquiry",
                is_fallback=False,
                is_skipped=True,
                api_cost=0.0,
            )
            return _empty_parse_result()

        try:
            from app.services.claude_parser import parse_email

            parsed = await parse_email(llm_input_body, subject)

            # Round-17 — merge heuristic_parts from attachments into the
            # LLM result. Keeps the structured rows we already extracted
            # even when the LLM misses them; deduplicates by part_code
            # so we never double-count.
            parsed = _merge_heuristic_parts(parsed, heuristic_rows)

            log_parse_metrics(
                email_id=email.id,
                duration_ms=elapsed_ms(start_time),
                parts_count=len(parsed.get("parts", [])),
                confidence=parsed.get("confidence", 0.0),
                category=parsed.get("category", "unknown"),
                is_fallback=False,
                is_skipped=False,
                api_cost=ESTIMATED_COST_PER_CALL,
            )
            return parsed

        except Exception as exc:
            logger.warning(
                "Claude API failed for email %d, using regex fallback: %s",
                email.id,
                exc,
            )
            parsed = regex_fallback_parse(llm_input_body, subject)
            # In the fallback path the heuristic rows are doubly
            # important — they are often the only structured signal we
            # have when Claude is down.
            parsed = _merge_heuristic_parts(parsed, heuristic_rows)

            log_parse_metrics(
                email_id=email.id,
                duration_ms=elapsed_ms(start_time),
                parts_count=len(parsed.get("parts", [])),
                confidence=parsed.get("confidence", 0.0),
                category=parsed.get("category", "unknown"),
                is_fallback=True,
                is_skipped=False,
                api_cost=0.0,
            )
            return parsed

    @staticmethod
    def _classify_with_consolidation(
        email: EmailRequest,
        parsed: dict,
    ) -> None:
        """Use Claude classification as primary, keyword as validation."""
        from app.services.email_classifier import classify_email

        claude_category = parsed.get("category", "general_inquiry")
        claude_confidence = parsed.get("confidence", 0.0)

        body = email.body_text or email.body_html or ""
        keyword_result = classify_email(email.subject or "", body)
        keyword_category = keyword_result.get("category", "general_inquiry")
        keyword_confidence = keyword_result.get("confidence", 0.0)

        email.price_sensitivity = keyword_result.get("price_sensitivity")

        if claude_category == keyword_category:
            email.category = claude_category
            email.category_confidence = max(
                claude_confidence,
                keyword_confidence,
            )
        elif claude_confidence >= CONFIDENCE_THRESHOLD:
            email.category = claude_category
            email.category_confidence = claude_confidence
            logger.info(
                "Classification mismatch for email %d: "
                "claude=%s(%.2f) vs keyword=%s(%.2f). Using Claude.",
                email.id,
                claude_category,
                claude_confidence,
                keyword_category,
                keyword_confidence,
            )
        else:
            email.category = keyword_category
            email.category_confidence = keyword_confidence
            logger.info(
                "Low-confidence Claude classification for email %d: "
                "claude=%s(%.2f). Falling back to keyword=%s(%.2f).",
                email.id,
                claude_category,
                claude_confidence,
                keyword_category,
                keyword_confidence,
            )

    @staticmethod
    def _apply_parsed_data(email: EmailRequest, parsed: dict) -> None:
        """Write parsed results onto the email record."""
        email.parsed_data = json.dumps(parsed)
        email.language = parsed.get("language")
        email.status = EmailStatus.PARSED.value

    async def _set_review_status(self, email: EmailRequest, parsed: dict) -> None:
        """Set review status based on whether parts were found in catalog.

        Approved = spare part request with at least one part matched in DB.
        Pending = spare part request but no parts matched, or low confidence.
        Rejected = not a spare part request (general inquiry, etc).
        """
        is_spare_part = parsed.get("is_spare_part_request", False)
        parts = parsed.get("parts", [])
        confidence = email.category_confidence or 0.0

        if not is_spare_part or not parts:
            # Not a parts request → reject (general inquiry)
            if email.category in ("spare_part_request", "price_inquiry"):
                email.review_status = ReviewStatus.PENDING_REVIEW.value
            else:
                email.review_status = ReviewStatus.REJECTED.value
            return

        # Check if any parsed part codes exist in the catalog
        from app.models.spare_part import SparePart
        from sqlalchemy import select as sa_select, func as sa_func

        part_codes = [p.get("part_code", "") for p in parts if p.get("part_code")]
        matched_count = 0
        if part_codes:
            result = await self._db.execute(
                sa_select(sa_func.count(SparePart.id)).where(
                    SparePart.honeywell_code.in_(part_codes)
                )
            )
            matched_count = result.scalar() or 0

        if matched_count > 0 and confidence >= CONFIDENCE_THRESHOLD:
            email.review_status = ReviewStatus.APPROVED.value
        elif matched_count > 0:
            email.review_status = ReviewStatus.PENDING_REVIEW.value
        else:
            email.review_status = ReviewStatus.PENDING_REVIEW.value

    async def _auto_create_customer(
        self,
        email: EmailRequest,
        parsed: dict,
    ) -> None:
        """Auto-create customer from parsed email data if not exists."""
        from app.models.customer import Customer

        customer_name = parsed.get("customer_name", "")
        customer_company = parsed.get("customer_company", "")
        from_address = email.from_address

        if not from_address:
            return

        result = await self._db.execute(
            select(Customer).where(Customer.email == from_address)
        )
        existing = result.scalar_one_or_none()

        if existing:
            email.customer_id = existing.id
            if customer_name and not existing.name:
                existing.name = customer_name
            if customer_company and not existing.company:
                existing.company = customer_company
        else:
            name = customer_name or from_address.split("@")[0]
            # Round-15 Sprint 15k cohort 1 — Customer.tenant_id NOT
            # NULL. Inherit from the email (parser sets it from the
            # owning user).
            customer = Customer(
                tenant_id=getattr(email, "tenant_id", None),
                name=name,
                email=from_address,
                company=customer_company or None,
            )
            self._db.add(customer)
            await self._db.flush()
            email.customer_id = customer.id
            logger.info(
                "Auto-created customer: %s <%s>",
                name,
                from_address,
            )

    async def _auto_create_draft_quote(
        self,
        email: EmailRequest,
        parsed: dict,
    ) -> None:
        """Auto-create a draft quote from parsed email parts (idempotent).

        Uses SELECT ... FOR UPDATE to prevent TOCTOU race conditions.
        If a concurrent worker already created the quote, IntegrityError
        is caught and the existing quote is used instead.
        """
        from sqlalchemy.exc import IntegrityError
        from app.models.quote import Quote
        from app.services.quote_service import QuoteService

        # Lock-based guard: prevents concurrent creation for the same email
        existing = await self._db.execute(
            select(Quote)
            .where(Quote.email_request_id == email.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if existing.scalar_one_or_none():
            logger.info("Quote already exists for email %d", email.id)
            return

        if not email.customer_id:
            logger.debug(
                "Skipping auto-quote for email %d: no customer_id",
                email.id,
            )
            return

        try:
            service = QuoteService(self._db)
            quote = await service.create_quote_from_email(
                email_id=email.id,
                created_by=None,
            )
            email.status = EmailStatus.QUOTED.value
            logger.info(
                "Auto-created draft quote %s from email %d",
                quote.quote_number,
                email.id,
            )
        except IntegrityError:
            await self._db.rollback()
            logger.info(
                "Duplicate quote prevented by DB constraint for email %d",
                email.id,
            )
        except Exception as exc:
            logger.warning(
                "Auto-quote creation failed for email %d: %s",
                email.id,
                exc,
            )


def _empty_parse_result() -> dict:
    return {
        "language": "tr",
        "customer_name": "",
        "customer_company": "",
        "parts": [],
        "is_spare_part_request": False,
        "category": "general_inquiry",
        "confidence": 0.0,
    }
