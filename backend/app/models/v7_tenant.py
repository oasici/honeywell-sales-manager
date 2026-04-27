"""V7 tenant model + analytics-side tenant_id column registry.

This file owns the ``Tenant`` row only. The corresponding
``tenant_id`` columns on V5/V6 analytics tables are added at the SQL
level by ``20260427_v7_tenant_boundary``; we do *not* add them as
SQLAlchemy mapped attributes on the existing models because that
would force every V5 read site to either include or explicitly defer
the new column. Single-tenant deployments keep behaving as before;
multi-tenant code paths use raw SQL via ``tenant_context.scoped()``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    region: Mapped[str | None] = mapped_column(String(60), nullable=True)
    plan_tier: Mapped[str] = mapped_column(String(40), default="standard")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
