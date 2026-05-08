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

    # Render Postgres enforces SSL/TLS — connecting without it raises
    # ``InvalidAuthorizationSpecificationError: SSL/TLS required``. The
    # libpq-style ``?sslmode=require`` parameter is silently dropped by
    # the asyncpg dialect, so we pass ``ssl="require"`` directly through
    # ``connect_args`` (asyncpg interprets the string as "use TLS, skip
    # cert verification" — appropriate for Render's managed certs).
    # Localhost dev/test paths skip this so SQLite + local Postgres
    # without TLS keep working.
    _connect_args: dict = {"server_settings": {"client_encoding": "utf8"}}
    _is_local = (
        "localhost" in _db_url
        or "127.0.0.1" in _db_url
        # Round-9 — match every docker-compose db service variant
        # (db, db-sandbox, db-test, etc.). Pre-fix only ``@db:`` was
        # detected, so sandbox + test compose runs were being forced
        # into TLS against an alpine Postgres with no cert.
        or "@db:" in _db_url
        or "@db-" in _db_url
    )
    if not _is_local:
        _connect_args["ssl"] = "require"

    # Pool size per worker — env-driven so we can tune without redeploys.
    # Total ceiling = workers * (DB_POOL_SIZE + DB_MAX_OVERFLOW).
    # Defaults assume 4 workers + Postgres max_connections >= 150. Drop the
    # values for free/tiny tiers (see config.py for Render-free guidance).
    # pool_pre_ping=True catches stale connections after Render's idle drops;
    # pool_recycle bounds connection age to dodge proxy-side TCP timeouts.
    engine = create_async_engine(
        _db_url,
        echo=False,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True,
        pool_recycle=settings.DB_POOL_RECYCLE,
        connect_args=_connect_args,
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
