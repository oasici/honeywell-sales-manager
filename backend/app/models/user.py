from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # R6-DB-1 — UNIQUE auto-creates a btree index; the explicit
    # ``index=True`` was producing a duplicate. Same R5-DB-2/3 sweep,
    # missed family. Drop migration: 20260506_drop_dup_unique_indexes.
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="sales_rep")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_setup_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    password_change_required: Mapped[bool] = mapped_column(Boolean, default=False)
    manager_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True,
    )
    # V8: multi-tenant boundary. NULL → "default tenant" so single-
    # tenant deployments keep working without backfill.
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
