"""Live chat models — real-time visitor-agent messaging."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_chat_visitor", "visitor_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 R4-TEN-19 — tenant boundary on live-chat sessions. Backfilled by alembic
    # 20260504_add_tenant_id_to_engagement_billing (PHASE 4 follow-up).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    visitor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_agent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    # open | assigned | closed
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    agent = relationship("User", lazy="selectin")
    messages = relationship("ChatMessage", back_populates="session", lazy="noload")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_cm_session", "session_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 R4-TEN-19 — tenant boundary on live-chat messages. Backfilled by alembic
    # 20260504_add_tenant_id_to_engagement_billing (PHASE 4 follow-up).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # visitor | agent | bot
    sender_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="text")
    # text | image | file
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session = relationship("ChatSession", back_populates="messages", lazy="selectin")


class AutoResponseRule(Base):
    __tablename__ = "auto_response_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 R4-TEN-19 — tenant boundary on live-chat auto-response rules.
    # Backfilled by alembic 20260504_add_tenant_id_to_engagement_billing (PHASE 4 follow-up).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    trigger_keyword: Mapped[str] = mapped_column(String(200), nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    creator = relationship("User", lazy="selectin")
