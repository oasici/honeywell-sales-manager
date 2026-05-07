"""Additive shadow projection of canonical sales_events (no writer to this table from CRM paths)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SalesEventShadow(Base):
    """Idempotent nightly materialization: activity_logs ∪ opportunity_events ∪ revenue_signals."""

    __tablename__ = "v4_sales_events_shadow"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Dedupe key across sources, e.g. shadow:activity_logs:42
    # R7-DB-1 — UNIQUE auto-creates a btree index.
    source_ref: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    provenance: Mapped[str] = mapped_column(String(40), nullable=False)

    account_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    opportunity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    contact_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    event_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)

    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_v4_sales_shadow_opp_ts", "opportunity_id", "event_ts"),)
