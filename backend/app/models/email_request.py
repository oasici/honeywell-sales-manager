from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EmailRequest(Base):
    __tablename__ = "email_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # R4-TEN-23 — backfilled by alembic
    # 20260504_add_tenant_id_to_email_requests (PHASE 4 follow-up).
    # Nullable so single-tenant deployments and pre-migration rows keep
    # working; cross-tenant guards use ``assert_same_tenant`` which is a
    # no-op when either side is None.
    tenant_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True, index=True
    )
    # R7-DB-1 — UNIQUE auto-creates a btree index.
    message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    from_address: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(5), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Processing status
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    # new -> parsed -> quoted -> sent -> error
    parsed_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    # Round-17 email hardening — stores the parsed text + heuristic
    # part rows extracted from supported attachments (Excel/CSV/PDF).
    # Persisted as a JSON list of ``{filename, content_type,
    # size_bytes, text, heuristic_parts, error}`` records so the
    # Claude parse step can be re-run offline (e.g. after a system
    # prompt update) without re-downloading the original message.
    attachments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Round-17 — SPF/DKIM/DMARC verification verdict at IMAP-fetch time.
    # ``pass`` / ``fail`` / ``none`` / ``unverified``. Unverified or failing
    # senders route to the review queue rather than the auto-quote path.
    sender_auth_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Classification
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_sensitivity: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_duplicate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duplicate_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # AI Triage
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)  # urgent|high|normal|low
    triage_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Data classification
    data_classification: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # public|internal|confidential|restricted

    # Read tracking
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    last_parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # v2: Opportunity linkage (nullable — backward compatible)
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=True, index=True
    )

    # Threading
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Round-18 — RFQ thread key. Stable 16-hex SHA-256 digest over
    # (tenant_id, thread_id) or (tenant_id, sender_domain,
    # normalised_subject). Emails sharing this key belong to the
    # same logical RFQ — the quote-creation path uses it to decide
    # whether to extend an existing draft quote or open a new one.
    rfq_thread_key: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )

    # Round-19 — Phase 1 eligibility-gate hardening (F-002/F-003/F-004).
    # When the auto-quote pipeline refuses to process an email it sets
    # ``parse_skipped_reason`` and leaves the LLM call un-attempted. The
    # reason codes are stable strings so the UI can switch on them:
    #   ``auth_failed``         — SPF/DKIM/DMARC said fail
    #   ``ocr_truncated``       — PDF page count exceeded MAX_OCR_PAGES
    #   ``first_time_sender``   — sender not in customers table
    #   ``encrypted_attachment``— ZIP/PDF needed password
    parse_skipped_reason: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    parse_overridden_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    # OCR truncation marker (F-003). True if any PDF attachment had
    # more pages than the per-tenant cap.
    attachment_pages_truncated: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    ocr_skipped_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # First-contact flag (F-004). True when no Customer row matches
    # the sender's primary_email in this tenant at parse time.
    first_time_sender: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Review workflow
    review_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # pending_review -> approved -> rejected
    assigned_to: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # D-009 Phase 12 — optimistic concurrency lock (guards parsed_data edits).
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # F-007 Phase 4 — soft-delete tombstones.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    delete_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    customer = relationship("Customer", back_populates="email_requests", lazy="selectin")
