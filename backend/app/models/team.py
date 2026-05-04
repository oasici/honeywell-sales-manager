"""Team-based access control models."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AccountTeam(Base):
    __tablename__ = "account_teams"
    __table_args__ = (
        UniqueConstraint("customer_id", "user_id", name="uq_account_team_customer_user"),
        # Round-4 R4-TEN-16 — tenant boundary on per-customer team rosters.
        # TODO: backfill in alembic 20260504_add_tenant_id_to_territories_teams.
        Index("ix_account_team_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(30), nullable=False)  # owner, member, viewer
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    customer = relationship("Customer", lazy="selectin")
    user = relationship("User", lazy="selectin")


class SharingRule(Base):
    __tablename__ = "sharing_rules"
    __table_args__ = (
        # Round-4 R4-TEN-16 — tenant boundary on sharing rules.
        # TODO: backfill in alembic 20260504_add_tenant_id_to_territories_teams.
        Index("ix_sharing_rule_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # customer, opportunity, quote
    criteria_json: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON: {"field": "company", "operator": "contains", "value": "Sanayi"}
    share_with_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    share_with_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    access_level: Mapped[str] = mapped_column(
        String(20), default="read"
    )  # read, read_write
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
