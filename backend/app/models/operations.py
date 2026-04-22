"""Operations / Light MRP data models (v3).

Scope we cover in v1:
    - Warehouses (multi-location stock).
    - StockLevel: per-(spare_part, warehouse) current quantity.
    - StockMovement: append-only ledger (in / out / adjust / transfer).
    - Bill of Materials: parent SKU composed of child SKUs.

Scope we defer:
    - MRP run / production scheduling Gantt.
    - Supplier purchase orders (handled by external ERP via push).
    - Serial-number / batch tracking.

``SparePart.current_stock_qty`` stays as the "total across warehouses"
cache so the existing stock-signal pipeline keeps working; the
authoritative per-warehouse figure lives in ``StockLevel.qty``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Warehouse ───────────────────────────────────────────────────────────────

class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── StockLevel ──────────────────────────────────────────────────────────────

class StockLevel(Base):
    __tablename__ = "stock_levels"
    __table_args__ = (
        UniqueConstraint(
            "spare_part_id", "warehouse_id", name="uq_stock_level_part_warehouse"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spare_part_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("spare_parts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    qty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reserved_qty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reorder_point: Mapped[float | None] = mapped_column(Float, nullable=True)

    last_counted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ── StockMovement ───────────────────────────────────────────────────────────

class StockMovement(Base):
    """Append-only ledger of stock changes.

    ``movement_type``:
        in       - goods-in (PO receipt, ERP import, manual adjust up).
        out      - goods-out (shipment, consumption, quote accepted).
        adjust   - manual delta (count correction, breakage).
        transfer - paired with a sibling row in the other warehouse.
    """

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spare_part_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("spare_parts.id"), nullable=False, index=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("warehouses.id"), nullable=False, index=True
    )
    movement_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    qty_delta: Mapped[float] = mapped_column(Float, nullable=False)
    qty_after: Mapped[float] = mapped_column(Float, nullable=False)
    unit_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )


# ── Bill of Materials ───────────────────────────────────────────────────────

class BillOfMaterials(Base):
    """A parent SKU composed of N children. Many BOMs per parent are allowed
    via ``version`` (e.g. revision upgrades)."""

    __tablename__ = "bills_of_materials"
    __table_args__ = (
        UniqueConstraint("parent_spare_part_id", "version", name="uq_bom_parent_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_spare_part_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("spare_parts.id"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    components = relationship(
        "BOMComponent",
        back_populates="bom",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class BOMComponent(Base):
    __tablename__ = "bom_components"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bom_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bills_of_materials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_spare_part_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("spare_parts.id"), nullable=False
    )
    qty_per_parent: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    bom = relationship("BillOfMaterials", back_populates="components", lazy="noload")
