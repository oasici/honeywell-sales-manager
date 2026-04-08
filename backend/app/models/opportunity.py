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
