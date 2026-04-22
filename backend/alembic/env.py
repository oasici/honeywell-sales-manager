import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.core.config import settings
from app.core.database import Base
from app.models import *  # noqa: F401, F403 - import all models for autogenerate

config = context.config

# Normalize URL: Railway gives postgresql://, alembic needs postgresql+asyncpg://
# SQLite URLs (used in local migration chain tests) pass through unchanged.
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _db_url.startswith("sqlite://"):
    # Keep as-is so tests can verify the migration chain without Postgres.
    pass
elif _db_url and not _db_url.startswith("postgresql+asyncpg://"):
    _db_url = f"postgresql+asyncpg://{_db_url}"
config.set_main_option("sqlalchemy.url", _db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_sync_migrations() -> None:
    """Sync path used by SQLite local chain tests."""
    from sqlalchemy import create_engine

    url = config.get_main_option("sqlalchemy.url")
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        do_run_migrations(connection)
    engine.dispose()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url") or ""
    if url.startswith("sqlite"):
        run_sync_migrations()
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
