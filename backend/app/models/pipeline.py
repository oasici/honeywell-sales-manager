"""Pipeline model — configurable sales pipelines.

Round-5 R5-TEN-26 added ``tenant_id`` (alembic ``20260505_pipeline_tenant``).
Pipelines are configuration rows, but managers from one tenant must
not see / edit / delete other tenants' pipelines. The column is
backfilled from ``users.tenant_id`` of ``created_by``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Pipeline(Base):
    __tablename__ = "pipelines"
    __table_args__ = (
        Index("ix_pipeline_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    stages_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON array: [{"key": "prospecting", "label": "Prospecting", "order": 1, "probability": 10}]
    # R6-DB-5 — explicit ``nullable=False`` so the model survives a
    # future flip of the type annotation. Migrations declare these
    # columns as NOT NULL; relying on ``Mapped[bool]`` to imply that is
    # brittle — see audit R6-DB-4/5.
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # R6-DB-4 — explicit ``nullable=False`` on timestamps.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    creator = relationship("User", lazy="selectin")
