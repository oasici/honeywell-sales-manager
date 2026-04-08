"""Opportunity (deal/pipeline) model — v2 Sales Board foundation."""

from datetime import datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opp_owner_stage", "owner_id", "stage"),
        Index("ix_opp_customer", "customer_id"),
        Index("ix_opp_close_date", "close_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False, default="prospecting")
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="TRY")
    close_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | closed
    forecast_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # commit | best_case | pipeline | omitted

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    customer = relationship("Customer", lazy="selectin")
    owner = relationship("User", lazy="selectin")
    events = relationship("OpportunityEvent", back_populates="opportunity", lazy="noload")
    quotes = relationship(
        "Quote",
        back_populates="opportunity",
        lazy="noload",
        foreign_keys="Quote.opportunity_id",
    )


class OpportunityEvent(Base):
    __tablename__ = "opportunity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # email | quote | call | meeting | note | task | stage_change
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    opportunity = relationship("Opportunity", back_populates="events")


class OpportunitySignal(Base):
    """Risk/insight signals extracted from emails, quotes, or AI analysis."""
    __tablename__ = "opportunity_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False, index=True
    )
    signal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # pricing_concern | competitor | no_touch | discount_risk | sla_breach | objection | positive
    severity: Mapped[str] = mapped_column(String(10), default="med")  # low | med | high
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # snippet + source
    source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # email | quote | ai
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_resolved: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    opportunity = relationship("Opportunity", backref="signals")


class Task(Base):
    """Next-best-action tasks for opportunities."""
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | done | dismissed
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | rule | ai
    priority: Mapped[str] = mapped_column(String(10), default="normal")  # low | normal | high | urgent
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    owner = relationship("User", lazy="selectin")
    opportunity = relationship("Opportunity", lazy="selectin")
