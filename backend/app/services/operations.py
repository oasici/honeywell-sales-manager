"""Operations / MRP service layer.

Primary responsibilities:

    - ``record_movement`` - atomic stock change with append-only ledger.
    - ``transfer_stock``  - paired movement across warehouses.
    - ``explode_bom``     - walk a Bill of Materials tree N levels deep.
    - ``reserve_for_quote`` / ``release_reservation`` - soft-reserve qty
      when a quote is approved; released when it becomes an ERP invoice.

All callers must pass an active ``AsyncSession`` and commit at the end.
Movements never mutate history; every qty change appends a row so audit
evidence survives re-sync from ERPs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import (
    BillOfMaterials,
    BOMComponent,
    StockLevel,
    StockMovement,
    Warehouse,
)
from app.models.spare_part import SparePart
from app.services.domain_events import emit_domain_event

logger = logging.getLogger(__name__)


class OperationsError(Exception):
    """Base class for operations-layer domain errors."""


class InsufficientStockError(OperationsError):
    pass


class UnknownWarehouseError(OperationsError):
    pass


VALID_MOVEMENT_TYPES = {"in", "out", "adjust", "transfer"}


# ── Warehouse helpers ───────────────────────────────────────────────────────


async def ensure_default_warehouse(db: AsyncSession) -> Warehouse:
    """Return (creating if needed) the single default warehouse.

    Keeps the happy path simple for single-location customers while still
    leaving multi-location open.
    """
    row = (
        await db.execute(select(Warehouse).where(Warehouse.is_default.is_(True)))
    ).scalars().first()
    if row:
        return row
    row = Warehouse(code="MAIN", name="Merkez Depo", is_default=True, is_active=True)
    db.add(row)
    await db.flush()
    return row


async def get_warehouse(db: AsyncSession, warehouse_id: int) -> Warehouse:
    wh = await db.get(Warehouse, warehouse_id)
    if not wh:
        raise UnknownWarehouseError(f"Warehouse {warehouse_id} not found")
    return wh


# ── Stock level helpers ─────────────────────────────────────────────────────


async def _get_or_create_level(
    db: AsyncSession, *, spare_part_id: int, warehouse_id: int
) -> StockLevel:
    stmt = select(StockLevel).where(
        StockLevel.spare_part_id == spare_part_id,
        StockLevel.warehouse_id == warehouse_id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row:
        return row
    row = StockLevel(
        spare_part_id=spare_part_id,
        warehouse_id=warehouse_id,
        qty=0.0,
        reserved_qty=0.0,
    )
    db.add(row)
    await db.flush()
    return row


async def _refresh_spare_part_total(db: AsyncSession, spare_part_id: int) -> float:
    total = (
        await db.execute(
            select(func.coalesce(func.sum(StockLevel.qty), 0.0)).where(
                StockLevel.spare_part_id == spare_part_id
            )
        )
    ).scalar() or 0.0
    part = await db.get(SparePart, spare_part_id)
    if part:
        part.current_stock_qty = float(total)
        part.last_stock_sync_at = datetime.now(timezone.utc)
    return float(total)


# ── Movements ───────────────────────────────────────────────────────────────


@dataclass
class MovementResult:
    movement_id: int
    qty_after: float
    total_across_warehouses: float


async def record_movement(
    db: AsyncSession,
    *,
    spare_part_id: int,
    warehouse_id: int,
    movement_type: str,
    qty_delta: float,
    unit_cost: float | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    note: str | None = None,
    actor_id: int | None = None,
) -> MovementResult:
    """Apply a stock movement + append to the ledger.

    ``qty_delta`` semantics:
        in      -> positive.
        out     -> negative (caller may pass either sign; we take abs and
                   negate so the ledger stays consistent).
        adjust  -> signed.
        transfer -> caller must record TWO movements (one neg, one pos).
    """
    if movement_type not in VALID_MOVEMENT_TYPES:
        raise OperationsError(f"Invalid movement_type: {movement_type}")

    # Normalise sign so callers cannot accidentally inflate stock.
    if movement_type == "in":
        delta = abs(qty_delta)
    elif movement_type == "out":
        delta = -abs(qty_delta)
    else:
        delta = qty_delta

    level = await _get_or_create_level(
        db, spare_part_id=spare_part_id, warehouse_id=warehouse_id
    )

    new_qty = level.qty + delta
    if new_qty < 0 and movement_type != "adjust":
        raise InsufficientStockError(
            f"Stock would go negative ({new_qty:g}) for part {spare_part_id} "
            f"at warehouse {warehouse_id}"
        )

    level.qty = new_qty
    movement = StockMovement(
        spare_part_id=spare_part_id,
        warehouse_id=warehouse_id,
        movement_type=movement_type,
        qty_delta=delta,
        qty_after=new_qty,
        unit_cost=unit_cost,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
        actor_id=actor_id,
    )
    db.add(movement)
    await db.flush()

    total = await _refresh_spare_part_total(db, spare_part_id)

    await emit_domain_event(
        db,
        "operations.stock_moved",
        {
            "spare_part_id": spare_part_id,
            "warehouse_id": warehouse_id,
            "movement_type": movement_type,
            "qty_delta": delta,
            "qty_after": new_qty,
            "total_across_warehouses": total,
            "reference_type": reference_type,
            "reference_id": reference_id,
        },
        entity_type="spare_part",
        entity_id=spare_part_id,
        persist=False,
    )

    return MovementResult(
        movement_id=movement.id, qty_after=new_qty, total_across_warehouses=total
    )


async def transfer_stock(
    db: AsyncSession,
    *,
    spare_part_id: int,
    from_warehouse_id: int,
    to_warehouse_id: int,
    qty: float,
    actor_id: int | None = None,
    note: str | None = None,
) -> dict[str, MovementResult]:
    """Emit a paired OUT / IN movement pair. Same-warehouse is rejected."""
    if from_warehouse_id == to_warehouse_id:
        raise OperationsError("Source and destination warehouses must differ")
    if qty <= 0:
        raise OperationsError("Transfer qty must be positive")

    out_result = await record_movement(
        db,
        spare_part_id=spare_part_id,
        warehouse_id=from_warehouse_id,
        movement_type="transfer",
        qty_delta=-abs(qty),
        reference_type="transfer_pair",
        actor_id=actor_id,
        note=f"Transfer out -> warehouse {to_warehouse_id}. {note or ''}".strip(),
    )
    in_result = await record_movement(
        db,
        spare_part_id=spare_part_id,
        warehouse_id=to_warehouse_id,
        movement_type="transfer",
        qty_delta=abs(qty),
        reference_type="transfer_pair",
        reference_id=out_result.movement_id,
        actor_id=actor_id,
        note=f"Transfer in <- warehouse {from_warehouse_id}. {note or ''}".strip(),
    )
    return {"out": out_result, "in": in_result}


# ── Reservations ────────────────────────────────────────────────────────────


async def reserve_for_quote(
    db: AsyncSession,
    *,
    spare_part_id: int,
    warehouse_id: int,
    qty: float,
    quote_id: int,
    actor_id: int | None = None,
) -> float:
    """Soft-reserve qty for a quote (doesn't move stock out, just earmarks)."""
    if qty <= 0:
        raise OperationsError("Reserve qty must be positive")
    level = await _get_or_create_level(
        db, spare_part_id=spare_part_id, warehouse_id=warehouse_id
    )
    available = level.qty - level.reserved_qty
    if qty > available:
        raise InsufficientStockError(
            f"Only {available:g} units available to reserve (requested {qty:g})"
        )
    level.reserved_qty += qty

    await emit_domain_event(
        db,
        "operations.stock_reserved",
        {
            "spare_part_id": spare_part_id,
            "warehouse_id": warehouse_id,
            "qty": qty,
            "quote_id": quote_id,
            "actor_id": actor_id,
        },
        entity_type="quote",
        entity_id=quote_id,
        persist=False,
    )
    return level.reserved_qty


async def release_reservation(
    db: AsyncSession,
    *,
    spare_part_id: int,
    warehouse_id: int,
    qty: float,
    quote_id: int,
) -> float:
    """Release a previously earmarked quantity (fulfilment / cancellation)."""
    level = await _get_or_create_level(
        db, spare_part_id=spare_part_id, warehouse_id=warehouse_id
    )
    level.reserved_qty = max(0.0, level.reserved_qty - qty)

    await emit_domain_event(
        db,
        "operations.stock_released",
        {
            "spare_part_id": spare_part_id,
            "warehouse_id": warehouse_id,
            "qty": qty,
            "quote_id": quote_id,
        },
        entity_type="quote",
        entity_id=quote_id,
        persist=False,
    )
    return level.reserved_qty


# ── BOM explosion ───────────────────────────────────────────────────────────


@dataclass
class BOMNode:
    spare_part_id: int
    qty_per_parent: float
    level: int
    children: list["BOMNode"] = field(default_factory=list)


async def explode_bom(
    db: AsyncSession,
    *,
    parent_spare_part_id: int,
    max_depth: int = 4,
) -> BOMNode:
    """Walk a BOM tree up to ``max_depth`` levels to return a flat tree.

    Guards against cycles via a ``visited`` set; a cycle aborts the branch
    rather than the whole call so multi-root traversals stay useful.
    """

    async def _walk(spare_part_id: int, qty: float, depth: int, visited: set[int]) -> BOMNode:
        node = BOMNode(spare_part_id=spare_part_id, qty_per_parent=qty, level=depth)
        if depth >= max_depth or spare_part_id in visited:
            return node
        visited = visited | {spare_part_id}

        active_bom = (
            await db.execute(
                select(BillOfMaterials).where(
                    BillOfMaterials.parent_spare_part_id == spare_part_id,
                    BillOfMaterials.is_active.is_(True),
                )
            )
        ).scalars().first()
        if not active_bom:
            return node

        components = (
            await db.execute(
                select(BOMComponent).where(BOMComponent.bom_id == active_bom.id)
            )
        ).scalars().all()

        for child in components:
            subtree = await _walk(
                child.component_spare_part_id,
                child.qty_per_parent,
                depth + 1,
                visited,
            )
            node.children.append(subtree)
        return node

    return await _walk(parent_spare_part_id, 1.0, 0, set())
