"""Operations / MRP REST endpoints.

Warehouses, stock levels, stock movements, BOM CRUD + explosion.
All routes are gated behind ``FEATURE_OPERATIONS``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.enums import UserRole
from app.models.operations import (
    BillOfMaterials,
    BOMComponent,
    StockLevel,
    StockMovement,
    Warehouse,
)
from app.models.user import User
from app.services.operations import (
    InsufficientStockError,
    OperationsError,
    UnknownWarehouseError,
    explode_bom,
    record_movement,
    reserve_for_quote,
    transfer_stock,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/operations", tags=["Operations"])


def _require_flag() -> None:
    if not settings.FEATURE_OPERATIONS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operations disabled")


# ── Warehouse CRUD ──────────────────────────────────────────────────────────


class WarehouseCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=120)
    address: str | None = None
    is_default: bool = False


class WarehouseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    address: str | None
    is_default: bool
    is_active: bool
    created_at: datetime


@router.get("/warehouses", response_model=list[WarehouseOut])
async def list_warehouses(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS, UserRole.SALES_REP))],
    db: AsyncSession = Depends(get_db),
) -> list[Warehouse]:
    _require_flag()
    rows = (
        await db.execute(select(Warehouse).order_by(Warehouse.is_default.desc(), Warehouse.code))
    ).scalars().all()
    return list(rows)


@router.post("/warehouses", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    body: WarehouseCreate,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    db: AsyncSession = Depends(get_db),
) -> Warehouse:
    _require_flag()
    existing = (
        await db.execute(select(Warehouse).where(Warehouse.code == body.code))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, f"Warehouse code already exists: {body.code}")

    if body.is_default:
        await db.execute(
            Warehouse.__table__.update().values(is_default=False).where(Warehouse.is_default.is_(True))
        )

    row = Warehouse(**body.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


# ── Stock levels ────────────────────────────────────────────────────────────


class StockLevelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    spare_part_id: int
    warehouse_id: int
    qty: float
    reserved_qty: float
    reorder_point: float | None
    updated_at: datetime


@router.get("/stock-levels", response_model=list[StockLevelOut])
async def list_stock_levels(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS, UserRole.SALES_REP))],
    spare_part_id: int | None = None,
    warehouse_id: int | None = None,
    below_reorder: bool = False,
    limit: int = Query(200, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
) -> list[StockLevel]:
    _require_flag()
    stmt = select(StockLevel)
    if spare_part_id is not None:
        stmt = stmt.where(StockLevel.spare_part_id == spare_part_id)
    if warehouse_id is not None:
        stmt = stmt.where(StockLevel.warehouse_id == warehouse_id)
    if below_reorder:
        stmt = stmt.where(StockLevel.reorder_point.isnot(None), StockLevel.qty < StockLevel.reorder_point)
    stmt = stmt.order_by(desc(StockLevel.updated_at)).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


# ── Stock movements ─────────────────────────────────────────────────────────


class MovementCreate(BaseModel):
    spare_part_id: int
    warehouse_id: int
    movement_type: str = Field(..., pattern="^(in|out|adjust)$")
    qty: float = Field(..., description="Always positive; sign comes from movement_type")
    unit_cost: float | None = None
    reference_type: str | None = None
    reference_id: int | None = None
    note: str | None = None


class TransferCreate(BaseModel):
    spare_part_id: int
    from_warehouse_id: int
    to_warehouse_id: int
    qty: float = Field(..., gt=0)
    note: str | None = None


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    spare_part_id: int
    warehouse_id: int
    movement_type: str
    qty_delta: float
    qty_after: float
    unit_cost: float | None
    reference_type: str | None
    reference_id: int | None
    note: str | None
    actor_id: int | None
    created_at: datetime


@router.post("/movements", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
async def create_movement(
    body: MovementCreate,
    current_user: Annotated[User, Depends(require_role(UserRole.OPERATIONS, UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
) -> StockMovement:
    _require_flag()
    try:
        result = await record_movement(
            db,
            spare_part_id=body.spare_part_id,
            warehouse_id=body.warehouse_id,
            movement_type=body.movement_type,
            qty_delta=body.qty,
            unit_cost=body.unit_cost,
            reference_type=body.reference_type,
            reference_id=body.reference_id,
            note=body.note,
            actor_id=current_user.id,
        )
    except InsufficientStockError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (OperationsError, UnknownWarehouseError) as exc:
        raise HTTPException(400, str(exc)) from exc

    movement = await db.get(StockMovement, result.movement_id)
    await db.commit()
    return movement  # type: ignore[return-value]


@router.post("/movements/transfer", response_model=dict)
async def create_transfer(
    body: TransferCreate,
    current_user: Annotated[User, Depends(require_role(UserRole.OPERATIONS, UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_flag()
    try:
        result = await transfer_stock(
            db,
            spare_part_id=body.spare_part_id,
            from_warehouse_id=body.from_warehouse_id,
            to_warehouse_id=body.to_warehouse_id,
            qty=body.qty,
            actor_id=current_user.id,
            note=body.note,
        )
    except (InsufficientStockError, OperationsError) as exc:
        raise HTTPException(400, str(exc)) from exc

    await db.commit()
    return {
        "out_movement_id": result["out"].movement_id,
        "in_movement_id": result["in"].movement_id,
    }


@router.get("/movements", response_model=list[MovementOut])
async def list_movements(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS, UserRole.SALES_REP))],
    spare_part_id: int | None = None,
    warehouse_id: int | None = None,
    movement_type: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[StockMovement]:
    _require_flag()
    stmt = select(StockMovement)
    if spare_part_id is not None:
        stmt = stmt.where(StockMovement.spare_part_id == spare_part_id)
    if warehouse_id is not None:
        stmt = stmt.where(StockMovement.warehouse_id == warehouse_id)
    if movement_type:
        stmt = stmt.where(StockMovement.movement_type == movement_type)
    stmt = stmt.order_by(desc(StockMovement.created_at)).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


# ── BOM ─────────────────────────────────────────────────────────────────────


class BOMComponentIn(BaseModel):
    component_spare_part_id: int
    qty_per_parent: float = Field(default=1.0, gt=0)
    unit: str | None = None
    note: str | None = None


class BOMCreate(BaseModel):
    parent_spare_part_id: int
    version: str = "v1"
    description: str | None = None
    is_active: bool = True
    components: list[BOMComponentIn]


class BOMComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    component_spare_part_id: int
    qty_per_parent: float
    unit: str | None
    note: str | None


class BOMOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_spare_part_id: int
    version: str
    description: str | None
    is_active: bool
    components: list[BOMComponentOut]


@router.get("/bom", response_model=list[BOMOut])
async def list_boms(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS, UserRole.SALES_REP))],
    parent_spare_part_id: int | None = None,
    only_active: bool = True,
    db: AsyncSession = Depends(get_db),
) -> list[BillOfMaterials]:
    _require_flag()
    stmt = select(BillOfMaterials)
    if parent_spare_part_id is not None:
        stmt = stmt.where(BillOfMaterials.parent_spare_part_id == parent_spare_part_id)
    if only_active:
        stmt = stmt.where(BillOfMaterials.is_active.is_(True))
    stmt = stmt.order_by(BillOfMaterials.parent_spare_part_id, BillOfMaterials.version)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


@router.post("/bom", response_model=BOMOut, status_code=status.HTTP_201_CREATED)
async def create_bom(
    body: BOMCreate,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    db: AsyncSession = Depends(get_db),
) -> BillOfMaterials:
    _require_flag()
    if not body.components:
        raise HTTPException(400, "BOM requires at least one component")
    if any(
        comp.component_spare_part_id == body.parent_spare_part_id for comp in body.components
    ):
        raise HTTPException(400, "Component cannot be the parent itself")

    existing = (
        await db.execute(
            select(BillOfMaterials).where(
                BillOfMaterials.parent_spare_part_id == body.parent_spare_part_id,
                BillOfMaterials.version == body.version,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            409, f"BOM {body.version} already exists for parent {body.parent_spare_part_id}"
        )

    bom = BillOfMaterials(
        parent_spare_part_id=body.parent_spare_part_id,
        version=body.version,
        description=body.description,
        is_active=body.is_active,
        created_by=current_user.id,
    )
    db.add(bom)
    await db.flush()
    for comp in body.components:
        db.add(
            BOMComponent(
                bom_id=bom.id,
                component_spare_part_id=comp.component_spare_part_id,
                qty_per_parent=comp.qty_per_parent,
                unit=comp.unit,
                note=comp.note,
            )
        )
    await db.commit()
    await db.refresh(bom)
    return bom


class BOMExplosionNode(BaseModel):
    spare_part_id: int
    qty_per_parent: float
    level: int
    children: list["BOMExplosionNode"] = Field(default_factory=list)


BOMExplosionNode.model_rebuild()


@router.get("/bom/explode/{parent_spare_part_id}", response_model=BOMExplosionNode)
async def explode(
    parent_spare_part_id: int,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS, UserRole.SALES_REP))],
    max_depth: int = Query(4, ge=1, le=8),
    db: AsyncSession = Depends(get_db),
) -> BOMExplosionNode:
    _require_flag()
    tree = await explode_bom(db, parent_spare_part_id=parent_spare_part_id, max_depth=max_depth)

    def _to_schema(node) -> BOMExplosionNode:
        return BOMExplosionNode(
            spare_part_id=node.spare_part_id,
            qty_per_parent=node.qty_per_parent,
            level=node.level,
            children=[_to_schema(child) for child in node.children],
        )

    return _to_schema(tree)


# ── Reservations ────────────────────────────────────────────────────────────


class ReservationCreate(BaseModel):
    spare_part_id: int
    warehouse_id: int
    qty: float = Field(..., gt=0)
    quote_id: int


@router.post("/reservations", response_model=dict)
async def create_reservation(
    body: ReservationCreate,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS, UserRole.SALES_REP))],
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_flag()
    try:
        reserved = await reserve_for_quote(
            db,
            spare_part_id=body.spare_part_id,
            warehouse_id=body.warehouse_id,
            qty=body.qty,
            quote_id=body.quote_id,
            actor_id=current_user.id,
        )
    except InsufficientStockError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OperationsError as exc:
        raise HTTPException(400, str(exc)) from exc

    await db.commit()
    return {"reserved_total": reserved, "quote_id": body.quote_id}
