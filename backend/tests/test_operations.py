"""Core operations service tests (async, SQLite in-memory)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.spare_part import SparePart
from app.models.operations import Warehouse
from app.services.operations import (
    InsufficientStockError,
    OperationsError,
    ensure_default_warehouse,
    explode_bom,
    record_movement,
    reserve_for_quote,
    transfer_stock,
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        part = SparePart(honeywell_code="HW-1", name_tr="Filter")
        session.add(part)
        await session.flush()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_record_movement_in_and_out(session: AsyncSession):
    part = (await session.execute(
        SparePart.__table__.select().where(SparePart.honeywell_code == "HW-1")
    )).first()
    part_id = part.id

    wh = await ensure_default_warehouse(session)

    result_in = await record_movement(
        session,
        spare_part_id=part_id,
        warehouse_id=wh.id,
        movement_type="in",
        qty_delta=25,
    )
    assert result_in.qty_after == 25
    assert result_in.total_across_warehouses == 25

    result_out = await record_movement(
        session,
        spare_part_id=part_id,
        warehouse_id=wh.id,
        movement_type="out",
        qty_delta=7,
    )
    assert result_out.qty_after == 18


@pytest.mark.asyncio
async def test_out_rejected_when_insufficient(session: AsyncSession):
    part = (await session.execute(
        SparePart.__table__.select().where(SparePart.honeywell_code == "HW-1")
    )).first()
    wh = await ensure_default_warehouse(session)

    with pytest.raises(InsufficientStockError):
        await record_movement(
            session,
            spare_part_id=part.id,
            warehouse_id=wh.id,
            movement_type="out",
            qty_delta=5,
        )


@pytest.mark.asyncio
async def test_transfer_moves_stock_between_warehouses(session: AsyncSession):
    part = (await session.execute(
        SparePart.__table__.select().where(SparePart.honeywell_code == "HW-1")
    )).first()

    source = Warehouse(code="A", name="Depo A", is_default=True)
    dest = Warehouse(code="B", name="Depo B")
    session.add_all([source, dest])
    await session.flush()

    await record_movement(
        session,
        spare_part_id=part.id,
        warehouse_id=source.id,
        movement_type="in",
        qty_delta=10,
    )

    result = await transfer_stock(
        session,
        spare_part_id=part.id,
        from_warehouse_id=source.id,
        to_warehouse_id=dest.id,
        qty=4,
    )
    assert result["out"].qty_after == 6
    assert result["in"].qty_after == 4
    assert result["in"].total_across_warehouses == 10


@pytest.mark.asyncio
async def test_transfer_rejects_same_source_and_dest(session: AsyncSession):
    part = (await session.execute(
        SparePart.__table__.select().where(SparePart.honeywell_code == "HW-1")
    )).first()
    wh = await ensure_default_warehouse(session)
    with pytest.raises(OperationsError):
        await transfer_stock(
            session,
            spare_part_id=part.id,
            from_warehouse_id=wh.id,
            to_warehouse_id=wh.id,
            qty=1,
        )


@pytest.mark.asyncio
async def test_reservation_blocks_when_qty_exceeds(session: AsyncSession):
    part = (await session.execute(
        SparePart.__table__.select().where(SparePart.honeywell_code == "HW-1")
    )).first()
    wh = await ensure_default_warehouse(session)
    await record_movement(
        session, spare_part_id=part.id, warehouse_id=wh.id, movement_type="in", qty_delta=3
    )
    await reserve_for_quote(
        session, spare_part_id=part.id, warehouse_id=wh.id, qty=3, quote_id=1
    )
    with pytest.raises(InsufficientStockError):
        await reserve_for_quote(
            session, spare_part_id=part.id, warehouse_id=wh.id, qty=1, quote_id=2
        )


@pytest.mark.asyncio
async def test_bom_explode_two_levels(session: AsyncSession):
    from app.models.operations import BillOfMaterials, BOMComponent

    parent = SparePart(honeywell_code="HW-PARENT", name_tr="Assembly")
    child_a = SparePart(honeywell_code="HW-A", name_tr="Gear")
    child_b = SparePart(honeywell_code="HW-B", name_tr="Screw")
    session.add_all([parent, child_a, child_b])
    await session.flush()

    bom = BillOfMaterials(parent_spare_part_id=parent.id, version="v1", is_active=True)
    session.add(bom)
    await session.flush()
    session.add_all([
        BOMComponent(bom_id=bom.id, component_spare_part_id=child_a.id, qty_per_parent=2),
        BOMComponent(bom_id=bom.id, component_spare_part_id=child_b.id, qty_per_parent=4),
    ])
    await session.flush()

    tree = await explode_bom(session, parent_spare_part_id=parent.id)
    assert tree.spare_part_id == parent.id
    assert len(tree.children) == 2
    ids = sorted(node.spare_part_id for node in tree.children)
    assert ids == sorted([child_a.id, child_b.id])
