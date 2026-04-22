from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Railway Postgres gives postgresql://, asyncpg needs postgresql+asyncpg://
# SQLite URLs pass through unchanged for local migration-chain tests.
_db_url = settings.DATABASE_URL
_is_sqlite = _db_url.startswith("sqlite://") or _db_url.startswith("sqlite+aiosqlite://")
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _is_sqlite:
    if _db_url.startswith("sqlite://") and not _db_url.startswith("sqlite+aiosqlite://"):
        _db_url = _db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
elif _db_url and not _db_url.startswith("postgresql+asyncpg://"):
    _db_url = f"postgresql+asyncpg://{_db_url}"

# Pool size per worker — conservative for multi-worker (gunicorn -w 4)
# Total connections: 4 workers x (5+10) = 60 max
# With PgBouncer: multiplexed, safe for PostgreSQL default max_connections=100
_engine_kwargs: dict = {"echo": False, "pool_pre_ping": True, "pool_recycle": 300}
if _is_sqlite:
    # SQLite doesn't need the Postgres-specific connect_args and the pool
    # options below don't translate cleanly to an in-memory file.
    pass
else:
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10
    _engine_kwargs["connect_args"] = {"server_settings": {"client_encoding": "utf8"}}

# Fallback to an in-memory SQLite URL when DATABASE_URL is blank so importing
# this module never raises at collection time in tooling contexts
# (pytest, alembic verifier, scripts). Real workloads always set the URL.
if not _db_url:
    _db_url = "sqlite+aiosqlite:///:memory:"
    _is_sqlite = True
    _engine_kwargs = {"echo": False}

engine = create_async_engine(_db_url, **_engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
