"""Campaign management models — campaign tracking with ROI."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        Index("ix_campaign_status", "status"),
        Index("ix_campaign_created_by", "created_by"),
        # R6-API-1 — tenant_id index added in 20260506_campaign_tenant.
        Index("ix_campaign_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # R6-API-1 — Round-4 added ``tenant_id`` to every CRM table; the
    # campaign module never received the treatment, leaving every
    # ``GET /campaigns`` cross-tenant readable. Backfilled from the
    # creator's tenant by the 20260506 migration.
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False, default="email")
    # email | event | webinar | direct_mail | social | other
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # draft | active | paused | completed | cancelled
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_cost: Mapped[float] = mapped_column(Float, default=0.0)
    expected_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    members = relationship("CampaignMember", back_populates="campaign", lazy="noload")
    creator = relationship("User", lazy="selectin")


class CampaignMember(Base):
    __tablename__ = "campaign_members"
    __table_args__ = (
        UniqueConstraint("campaign_id", "lead_id", name="uq_campaign_lead"),
        UniqueConstraint("campaign_id", "customer_id", name="uq_campaign_customer"),
        Index("ix_campaign_member_campaign", "campaign_id"),
        # R6-API-1 — tenant_id mirrors parent campaign; backfilled by
        # the 20260506 migration via ``UPDATE … FROM campaigns``.
        Index("ix_campaign_member_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("campaigns.id"), nullable=False)
    lead_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("leads.id"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="sent")
    # sent | opened | clicked | responded | converted | unsubscribed
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    campaign = relationship("Campaign", back_populates="members", lazy="selectin")
    lead = relationship("Lead", lazy="selectin")
    customer = relationship("Customer", lazy="selectin")
