"""Service layer for email parsing and processing workflows."""

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.email_request import EmailRequest
from app.models.enums import EmailStatus, ReviewStatus

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.75
ERROR_MESSAGE_MAX_LENGTH = 500


class EmailProcessingService:
    """Encapsulates email parsing, classification, and review workflows."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def process_email(self, email_id: int) -> EmailRequest:
        """Full pipeline: parse with Claude, classify, set review status."""
        email = await self._get_email_or_raise(email_id)

        email.status = EmailStatus.NEW.value
        email.parsed_data = None
        email.error_message = None
        await self._db.flush()

        try:
            parsed = await self._parse_with_claude(email)
            if parsed:
                self._apply_parsed_data(email, parsed)
                self._classify_email(email)
                self._set_review_status(email)
            else:
                email.status = EmailStatus.ERROR.value
                email.error_message = "Claude parse returned empty"
        except Exception as exc:
            logger.exception("Failed to process email %d", email_id)
            email.status = EmailStatus.ERROR.value
            email.error_message = str(exc)[:ERROR_MESSAGE_MAX_LENGTH]

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
            parsed = await self._parse_with_claude(email)
            if parsed:
                self._apply_parsed_data(email, parsed)
                self._classify_email(email)
                self._set_review_status(email)
                await self._db.flush()
                await self._db.refresh(email)
        except Exception as exc:
            logger.exception("Failed to parse manual email %d", email.id)
            email.status = EmailStatus.ERROR.value
            email.error_message = str(exc)[:ERROR_MESSAGE_MAX_LENGTH]
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
            raise NotFoundException(f"Email with id {email_id} not found")
        return email

    @staticmethod
    async def _parse_with_claude(email: EmailRequest) -> dict | None:
        """Call Claude parser on the email body."""
        from app.services.claude_parser import parse_email

        body = email.body_text or email.body_html or ""
        return await parse_email(body)

    @staticmethod
    def _apply_parsed_data(email: EmailRequest, parsed: dict) -> None:
        """Write parsed results onto the email record."""
        email.parsed_data = json.dumps(parsed)
        email.language = parsed.get("language")
        email.status = EmailStatus.PARSED.value

    @staticmethod
    def _classify_email(email: EmailRequest) -> None:
        """Run the keyword/ML classifier on the email."""
        from app.services.email_classifier import classify_email

        body = email.body_text or email.body_html or ""
        classification = classify_email(email.subject or "", body)
        email.category = classification.get("category")
        email.category_confidence = classification.get("confidence")
        email.price_sensitivity = classification.get("price_sensitivity")

    @staticmethod
    def _set_review_status(email: EmailRequest) -> None:
        """Gate low-confidence classifications for manual review."""
        if email.category_confidence and email.category_confidence < CONFIDENCE_THRESHOLD:
            email.review_status = ReviewStatus.PENDING_REVIEW.value
        else:
            email.review_status = ReviewStatus.APPROVED.value
