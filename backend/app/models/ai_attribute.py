"""AI Attributes (plan adoption — Phase 2 Sprint 8).

Persistent AI-generated fields attached to CRM entities. Distinct from
human-edited ``custom_fields`` — these are populated by an LLM-backed
generator, carry a confidence score, model version, and a trace ID for
audit. Reuses the audit + rate-limit plumbing from ``ai_audit.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# Entity types AI attributes can attach to. Tight enum so generation
# pipelines and field permissions stay aligned with the canonical 9-entity
# field-permission registry.
AI_ATTR_ENTITIES = (
    "opportunity",
    "customer",
    "lead",
    "account",
    "quote",
    "contract",
)

# Field shape the LLM is asked to return. Keep narrow on day one; expand
# only when a UI surface needs it.
AI_ATTR_DATA_TYPES = ("text", "number", "boolean", "list_text")


class AiAttributeDefinition(Base):
    """The schema of an AI-populated attribute (defined by an admin)."""

    __tablename__ = "ai_attribute_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    refresh_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", "key", name="uq_ai_attr_def_key"),
        Index("ix_ai_attr_def_entity_active", "entity_type", "is_active"),
    )


class AiAttributeValue(Base):
    """The generated value for one (definition, entity row)."""

    __tablename__ = "ai_attribute_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    definition_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_attribute_definitions.id"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_list_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint(
            "definition_id", "entity_type", "entity_id", name="uq_ai_attr_value_target"
        ),
        Index("ix_ai_attr_value_entity", "entity_type", "entity_id"),
    )
