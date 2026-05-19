"""Report folder model — hierarchical report organization.

Round-5 R5-TEN-28: ``tenant_id`` added (alembic ``20260505_breach_folder_tenant``).
Pre-R5 a folder created with ``is_shared=True`` was visible from any
tenant — now visibility is bounded by tenant_id even when shared.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReportFolder(Base):
    __tablename__ = "report_folders"
    __table_args__ = (
        Index("ix_report_folder_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-15 Sprint 15o cohort 5 — promoted to NOT NULL.
    # owner_id is NOT NULL and ``users.tenant_id`` is NOT NULL since R11.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("report_folders.id"), nullable=True
    )
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # R6-DB-5 — explicit nullable=False so the model survives a future
    # type-annotation flip; matches the migration shape.
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # R6-DB-4 — explicit nullable=False on the timestamp.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
