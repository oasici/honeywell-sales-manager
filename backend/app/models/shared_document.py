from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SharedDocument(Base):
    __tablename__ = "shared_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-12 R12-AUTH-2 — tenant boundary. Pre-fix the only filter on
    # list/analytics was ``created_by``; since user_id is globally unique
    # the leak is theoretical today, but adding tenant_id is defense in
    # depth and lines up with the project-wide convention. Backfilled
    # from users.tenant_id by 20260518_phase12_tenant_columns.
    # Round-15 Sprint 15n cohort 4 — promoted to NOT NULL.
    # created_by is NOT NULL on this row and ``users.tenant_id`` is
    # NOT NULL since R11; the FK chain is clean.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quote_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("quotes.id"), nullable=True, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    shared_with_email: Mapped[str] = mapped_column(String(255), nullable=False)
    # R7-DB-1 — UNIQUE auto-creates a btree index.
    tracking_token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    first_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_view_seconds: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
