"""Feature-flag registry + override service tests (async SQLite)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.services import feature_flags as ff_service


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()
    ff_service._invalidate_cache()  # clear TTL cache between tests


@pytest.mark.unit
def test_enumerate_flags_covers_all_feature_fields():
    flags = ff_service.enumerate_flags()
    names = {f.name for f in flags}
    # Sanity: a handful of known flags must show up.
    assert "FEATURE_ERP_CONNECTOR" in names
    assert "FEATURE_AI_TRUST_LAYER" in names
    assert "FEATURE_MARKETPLACE" in names
    assert "FEATURE_OPERATIONS" in names
    for flag in flags:
        assert flag.name.startswith("FEATURE_")


@pytest.mark.asyncio
async def test_list_flags_reports_no_override_by_default(session):
    rows = await ff_service.list_flags(session)
    erp = next(r for r in rows if r["name"] == "FEATURE_ERP_CONNECTOR")
    assert erp["override"] is None
    assert erp["effective"] == erp["env_value"]


@pytest.mark.asyncio
async def test_set_override_enables_then_clears(session):
    await ff_service.set_override(session, name="FEATURE_OPERATIONS", enabled=True)
    await session.flush()
    flag = next(
        r for r in await ff_service.list_flags(session)
        if r["name"] == "FEATURE_OPERATIONS"
    )
    assert flag["override"] is True
    assert flag["effective"] is True

    await ff_service.set_override(session, name="FEATURE_OPERATIONS", enabled=None)
    await session.flush()
    flag = next(
        r for r in await ff_service.list_flags(session)
        if r["name"] == "FEATURE_OPERATIONS"
    )
    assert flag["override"] is None
    assert flag["effective"] == flag["env_value"]


@pytest.mark.asyncio
async def test_set_override_rejects_unknown_flag(session):
    with pytest.raises(ValueError):
        await ff_service.set_override(session, name="FEATURE_BOGUS", enabled=True)
    with pytest.raises(ValueError):
        await ff_service.set_override(session, name="NOT_A_FLAG", enabled=True)


@pytest.mark.asyncio
async def test_clear_overrides_wipes_everything(session):
    await ff_service.set_override(session, name="FEATURE_OPERATIONS", enabled=True)
    await ff_service.set_override(session, name="FEATURE_AGENTIC_SDR", enabled=True)
    await session.flush()
    await ff_service.clear_overrides(session)
    await session.flush()
    rows = await ff_service.list_flags(session)
    assert all(r["override"] is None for r in rows)


@pytest.mark.asyncio
async def test_is_enabled_returns_override_when_set(session):
    await ff_service.set_override(session, name="FEATURE_MARKETPLACE", enabled=True)
    await session.flush()
    ff_service._invalidate_cache()
    assert await ff_service.is_enabled(session, "FEATURE_MARKETPLACE") is True
    # Clear + env default (False in test config).
    await ff_service.set_override(session, name="FEATURE_MARKETPLACE", enabled=None)
    await session.flush()
    ff_service._invalidate_cache()
    assert await ff_service.is_enabled(session, "FEATURE_MARKETPLACE") is False
