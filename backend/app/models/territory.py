"""Territory model — hierarchical sales territory management."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Territory(Base):
    __tablename__ = "territories"
    __table_args__ = (
        Index("ix_territory_parent", "parent_id"),
        # Round-4 R4-TEN-16 — tenant boundary on territories.
        # Backfilled by 20260504_phase4_tenant_id_sweep.
        Index("ix_territory_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("territories.id"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rules_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON: [{"field": "industry", "operator": "equals", "value": "Manufacturing"}]
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    children = relationship(
        "Territory",
        foreign_keys="Territory.parent_id",
        back_populates="parent_territory",
        lazy="noload",
    )
    parent_territory = relationship(
        "Territory",
        foreign_keys="Territory.parent_id",
        remote_side="Territory.id",
        lazy="selectin",
    )
    assignments = relationship("TerritoryAssignment", back_populates="territory", lazy="noload")
    creator = relationship("User", lazy="selectin")


class TerritoryAssignment(Base):
    __tablename__ = "territory_assignments"
    __table_args__ = (
        UniqueConstraint("territory_id", "user_id", name="uq_territory_user"),
        Index("ix_ta_territory", "territory_id"),
        Index("ix_ta_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    territory_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("territories.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    # owner | member | viewer
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    territory = relationship("Territory", back_populates="assignments", lazy="selectin")
    user = relationship("User", lazy="selectin")
