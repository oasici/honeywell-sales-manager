"""Field-level audit log (Shield-equivalent long-retention tracking).

Each row records a single attribute change on a tracked model. The
companion service (``services/field_audit.py``) installs a SQLAlchemy
``before_flush`` event listener that diff's dirty ORM objects and writes
here whenever ``FEATURE_FIELD_AUDIT`` is enabled.

Retention: ``FIELD_AUDIT_RETENTION_DAYS`` (default 3650 / 10 years) so
regulated customers can satisfy SOC 2 and KVKK evidence requirements that
the stock AuditLog table cannot.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FieldAuditLog(Base):
    __tablename__ = "field_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(96), nullable=False, index=True)

    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    # "user" | "system" | "erp" | "workflow" | "api"

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Short correlation handle: request id / job id / webhook delivery id.
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
