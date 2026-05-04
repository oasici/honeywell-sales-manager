"""Engagement models — transcripts, sequences, segments, keyword packs.

All tables are additive (non-breaking). Free-tier compatible:
- Transcripts: plain text upload (no Whisper dependency)
- Sequences: step-based follow-up (DB + scheduler)
- Segments: rule-based customer grouping
- Keyword packs: configurable signal detection keywords
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Transcript(Base):
    """Call/meeting transcript — text uploaded or pasted."""
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="upload")  # upload | paste | teams | zoom
    content: Mapped[str] = mapped_column(Text, nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    participants: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated
    # Full-text search vector populated by trigger/app
    keywords_found: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_items_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class KeywordPack(Base):
    """Configurable keyword packs for signal detection in transcripts/emails."""
    __tablename__ = "keyword_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    # pricing | competitor | objection | positive | technical | custom
    keywords_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # JSON array of strings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Sequence(Base):
    """Automated follow-up sequence definition."""
    __tablename__ = "sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 R4-TEN-13 — tenant boundary on sequences. Backfilled by alembic
    # 20260504_add_tenant_id_to_engagement_billing (PHASE 4 follow-up).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # JSON array: [{"step":1,"action":"email","delay_days":0,"template":"..."},
    #              {"step":2,"action":"task","delay_days":3,"template":"Follow up call"}]
    auto_enroll_rules_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_criteria_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SequenceEnrollment(Base):
    """An opportunity/customer enrolled in a sequence."""
    __tablename__ = "sequence_enrollments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 R4-TEN-13 — tenant boundary on sequence enrollments. Backfilled by alembic
    # 20260504_add_tenant_id_to_engagement_billing (PHASE 4 follow-up).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sequence_id: Mapped[int] = mapped_column(Integer, ForeignKey("sequences.id"), nullable=False, index=True)
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True
    )
    lead_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("leads.id"), nullable=True, index=True
    )
    current_step: Mapped[int] = mapped_column(Integer, default=1)
    # Legacy rows in some deployments can have NULL; keep nullable for safety.
    is_paused: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | paused | completed | exited | cancelled
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # V2 additive fields (FEATURE_SEQUENCES_V2)
    exit_reason: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # all_steps_completed | lead_converted | opp_closed | email_bounced | dnc | manual | global_exit
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enrolled_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Segment(Base):
    """Rule-based customer/territory segment."""
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 R4-TEN-13 — tenant boundary on segments. Backfilled by alembic
    # 20260504_add_tenant_id_to_engagement_billing (PHASE 4 follow-up).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # JSON array: [{"field":"company","op":"contains","value":"sanayi"},
    #              {"field":"total_quote_value","op":"gte","value":10000}]
    customer_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
