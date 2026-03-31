"""Service layer for email parsing and processing workflows."""

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

        try:
            parsed = await self._parse_email_with_fallback(email)
            if parsed:
                self._apply_parsed_data(email, parsed)
                self._classify_with_consolidation(email, parsed)
                await self._set_review_status(email, parsed)
                await self._auto_create_customer(email, parsed)

                # Auto-create draft quote if parts found with sufficient confidence
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
                self._apply_parsed_data(email, parsed)
                self._classify_with_consolidation(email, parsed)
                await self._set_review_status(email, parsed)
                await self._auto_create_customer(email, parsed)

                # Auto-create draft quote if parts found with sufficient confidence
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
            await self._db.flush()
            await self._db.refresh(email)

        return email

    # ---- Private helpers ----

    async def _get_email_or_raise(self, email_id: int) -> EmailRequest:
        result = await self._db.execute(
            select(EmailRequest).where(EmailRequest.id == email_id)
        )
        email = result.scalar_one_or_none()
        if not email:
            raise NotFoundException(f"{email_id} numarali e-posta bulunamadi")
        return email

    async def _parse_email_with_fallback(
        self,
        email: EmailRequest,
    ) -> dict | None:
        """Parse with pre-filtering, Claude API, and regex fallback."""
        body = email.body_text or email.body_html or ""
        subject = email.subject or ""
        start_time = time.monotonic()

        filter_result = pre_filter_email(body, subject)

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

            parsed = await parse_email(body, subject)

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
            parsed = regex_fallback_parse(body, subject)

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
            customer = Customer(
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
        """Auto-create a draft quote from parsed email parts."""
        from app.models.quote import Quote
        from app.services.quote_service import QuoteService

        # Guard against duplicate quote creation for the same email
        existing = await self._db.execute(
            select(Quote).where(Quote.email_request_id == email.id).limit(1)
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
