import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Ensure tests are deterministic even if a `.env` is present for docker runs.
#
# Test DB resolution order (so CI / local / Docker all work):
# 1. Explicit ``TEST_DATABASE_URL`` env var — CI overrides everything.
# 2. Default: PostgreSQL 16 container exposed on localhost:5434
#    (``docker-compose.override.yml`` ships ``db-test``). Matches prod
#    semantics (jsonb, ``to_char``, real transaction isolation, etc.).
# 3. Fallback: SQLite — kept for fully offline boxes; some PG-specific
#    features will silently degrade. Set ``TEST_DATABASE_URL=sqlite+aiosqlite:///./test.db``
#    to opt-in.
os.environ["ENV"] = "test"
_default_pg_test_url = (
    "postgresql+asyncpg://honeywell:honeywell_test_2026@"
    "localhost:5434/honeywell_sales_test"
)
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", _default_pg_test_url)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["REDIS_URL"] = ""
for _flag in (
    "FEATURE_DEAL_HEALTH",
    "FEATURE_SEQUENCES_V2",
    "FEATURE_V2_BOARD",
    "FEATURE_TASKS",
    "FEATURE_RAG",
    "FEATURE_SESSION_MANAGEMENT",
):
    os.environ[_flag] = "false"
# Round-4 R4-FLAG-3 gated /compliance/* behind FEATURE_BREACH_WORKFLOW
# and /invoices/* behind FEATURE_INVOICING. The compliance + invoice
# tests need the modules turned on so the routes don't 404.
for _flag in (
    "FEATURE_BREACH_WORKFLOW",
    "FEATURE_INVOICING",
    "FEATURE_REV_REC",
    "FEATURE_INVOICE_PAID_EVENT",
    # Round-5 R5-FLAG-15 — contract / subscription routers ship gated
    # off by default; enable for tests so existing fixtures + endpoints
    # don't 404. Operator decision separately at deploy-time.
    "FEATURE_CONTRACTS",
    "FEATURE_SUBSCRIPTIONS",
):
    os.environ[_flag] = "true"

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.user import User


_is_postgres = TEST_DATABASE_URL.startswith("postgresql")

# Postgres connections live for the test session; SQLite uses a fresh
# in-process file (legacy fallback path).
_engine_kwargs: dict = {"echo": False, "future": True}
if _is_postgres:
    # ``NullPool`` opens + closes a fresh asyncpg connection per
    # checkout. asyncpg objects are bound to their event loop, and
    # pytest-asyncio creates a new loop per test (function-scoped),
    # so any pooled connection becomes "Future attached to a
    # different loop" on the next test. NullPool sidesteps this by
    # never persisting connections across the loop boundary.
    _engine_kwargs.update({"poolclass": NullPool})

engine = create_async_engine(TEST_DATABASE_URL, **_engine_kwargs)
TestSession = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _dispose_engine_after_tests():
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limit_buckets():
    """Clear all in-memory rate-limit buckets between tests.

    Round-4 v1.9.10 added several module-level sliding-window buckets
    (login, login-username, AI, upload, bulk-action, KVKK export). The
    state accumulates across tests in a single pytest session, so the
    Nth test in a class would otherwise hit 429 once N exceeds the
    per-window count. Clearing the buckets is cheap and makes test
    runs deterministic.
    """
    from app.core import rate_limit as _rl

    for name in (
        "_login_attempts",
        "_login_username_attempts",
        "_ai_attempts",
        "_upload_attempts",
        "_tenant_ai_attempts",
        "_tenant_upload_attempts",
        "_bulk_attempts",
        "_kvkk_export_attempts",
        # Round-5 R5-RL-7
        "_signing_attempts",
    ):
        bucket = getattr(_rl, name, None)
        if bucket is not None:
            bucket.clear()
    yield


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Per-test schema reset.

    On PostgreSQL we DROP + CREATE the schema to avoid leftover
    constraints from a previous run interfering with FK ordering.
    Doing this with raw SQL instead of ``metadata.drop_all`` is much
    faster on PG since the latter walks every table individually.

    On SQLite we keep the legacy create_all/drop_all path because
    schema=public DDL is not a concept there.
    """
    if _is_postgres:
        async with engine.begin() as conn:
            # ``CASCADE`` so ALL FK dependencies dissolve at once.
            await conn.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
            await conn.exec_driver_sql("CREATE SCHEMA public")
            await conn.run_sync(Base.metadata.create_all)
        yield
        # Don't bother dropping on teardown — next test's setup wipes
        # the schema again, and skipping the drop trims a few seconds
        # off long suites.
    else:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(
        email="admin@test.com",
        full_name="Test Admin",
        hashed_password=hash_password("admin123"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user: User) -> str:
    from app.core.security import create_access_token

    return create_access_token({"sub": str(admin_user.id)})


@pytest_asyncio.fixture
async def auth_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}
