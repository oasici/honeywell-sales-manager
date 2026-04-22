from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

_raw_db_url = (settings.DATABASE_URL or "").strip()

# Test/dev convenience: allow sqlite URLs and avoid creating an invalid asyncpg engine
# when DATABASE_URL is missing (tests override get_db anyway).
if settings.ENV == "test" or _raw_db_url.startswith("sqlite"):
    _db_url = _raw_db_url or "sqlite+aiosqlite:///./test.db"
    engine = create_async_engine(_db_url, echo=False)
else:
    # Railway Postgres gives postgresql://, asyncpg needs postgresql+asyncpg://
    _db_url = _raw_db_url
    if _db_url.startswith("postgresql://"):
        _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif not _db_url.startswith("postgresql+asyncpg://"):
        _db_url = f"postgresql+asyncpg://{_db_url}"

    # Pool size per worker — conservative for multi-worker (gunicorn -w 4)
    # Total connections: 4 workers x (5+10) = 60 max
    # With PgBouncer: multiplexed, safe for PostgreSQL default max_connections=100
    engine = create_async_engine(
        _db_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"server_settings": {"client_encoding": "utf8"}},
    )

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
