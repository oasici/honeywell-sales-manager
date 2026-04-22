"""ERP integration data models.

Tables:
    erp_connections        - Tenant-specific ERP credentials + config.
    erp_entity_mappings    - Internal <-> external ID crosswalk (idempotency).
    erp_sync_jobs          - Job state + metrics for every sync run.
    erp_sync_conflicts     - Pending conflicts awaiting human resolution.

Design notes:
    * Credentials are stored encrypted (Fernet) in `credentials_encrypted`.
    * `(connection_id, entity_type, internal_id)` is unique per mapping row so
      the same domain entity (e.g. customers.id=42) can map to one external id
      per connection; multiple ERPs are supported by stacking mappings.
    * `erp_sync_jobs` rows are append-only; `status` updates during the run.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ── ERPConnection ────────────────────────────────────────────────────────────

class ERPConnection(Base):
    """One ERP tenant credential set + runtime state."""

    __tablename__ = "erp_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # "logo" | "parasut" | "sap_b1" | "netsis" | "mikro" | "webhook"
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)

    # Fernet-encrypted JSON: {"api_key":"...","username":"...","password":"..."}
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Cron-style sync schedule (optional); empty string disables the scheduled job.
    # Examples: "0 * * * *" (hourly), "*/15 * * * *" (every 15 min)
    sync_cron: Mapped[str | None] = mapped_column(String(64), nullable=True)

    last_customer_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_product_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_invoice_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Free-form config (charset, pagination size, etc.) stored as JSON text.
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ── ERPEntityMapping ─────────────────────────────────────────────────────────

class ERPEntityMapping(Base):
    """Crosswalk between internal PK and external ERP id.

    Ensures idempotent upserts: re-running a sync for the same external record
    updates rather than inserts.
    """

    __tablename__ = "erp_entity_mappings"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "entity_type", "internal_id",
            name="uq_erp_mapping_internal",
        ),
        UniqueConstraint(
            "connection_id", "entity_type", "external_id",
            name="uq_erp_mapping_external",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_connections.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # "customer" | "product" | "invoice" | "order" | "price"
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    internal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # "hss" (we wrote last) | "erp" (ERP wrote last)
    last_source: Mapped[str] = mapped_column(String(8), nullable=False, default="erp")

    # Hash of the last synced payload - cheap diff check for "changed" detection.
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


# ── ERPSyncJob ───────────────────────────────────────────────────────────────

class ERPSyncJob(Base):
    """Single sync attempt; rows are append-only audit/metrics."""

    __tablename__ = "erp_sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_connections.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # "customer" | "product" | "invoice" | "order" | "all"
    entity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="delta")  # "full" | "delta"
    # "queued" | "running" | "success" | "failed" | "partial"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", index=True)

    triggered_by: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    actor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    records_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cursor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── ERPSyncConflict ──────────────────────────────────────────────────────────

class ERPSyncConflict(Base):
    """Detected when the same entity was modified on both sides after last sync."""

    __tablename__ = "erp_sync_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("erp_connections.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    internal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)

    hss_snapshot: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    erp_snapshot: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    field_diffs: Mapped[str] = mapped_column(Text, nullable=False)   # JSON list of {field, hss, erp}

    # "pending" | "resolved_hss" | "resolved_erp" | "resolved_merge" | "dismissed"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
