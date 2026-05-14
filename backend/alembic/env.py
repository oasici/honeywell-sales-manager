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
_db_url = (settings.DATABASE_URL or "").strip()
if not _db_url:
    # Local/dev: allow `alembic upgrade head` without .env (matches test default driver)
    _db_url = "sqlite+aiosqlite:///./alembic_local.db"
elif _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _db_url.startswith("sqlite"):
    pass  # e.g. sqlite+aiosqlite:///./local.db
elif not _db_url.startswith("postgresql+asyncpg://"):
    _db_url = f"postgresql+asyncpg://{_db_url}"
# ConfigParser treats "%" as interpolation; URL-encoded passwords must survive round-trip.
_ini_url = _db_url.replace("%", "%%")
config.set_main_option("sqlalchemy.url", _ini_url)

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


def _widen_alembic_version_column(sync_conn) -> None:
    """Round-11 R11-DB-ENV — widen ``alembic_version.version_num`` on
    legacy Postgres databases.

    The alembic_version table that ships on older alembic-bootstrapped
    databases (Render's prod-shaped instance among them) defaults to
    ``VARCHAR(32)``. Round-10 introduced
    ``20260513_phase10_currency_numeric`` (33 chars), but the deploy
    never got past it because alembic's per-migration UPDATE blows up
    with ``value too long for type character varying(32)`` BEFORE the
    new revision id can be persisted.

    Symptom on Render::

        StringDataRightTruncationError: value too long for type
        character varying(32)
        [SQL: UPDATE alembic_version SET version_num=
              '20260513_phase10_currency_numeric'
              WHERE alembic_version.version_num=
                    '20260512_phase9_tenant_sweep']

    Fix: bump the column to ``VARCHAR(128)`` BEFORE alembic runs any
    migration. ``ALTER COLUMN ... TYPE`` is idempotent — re-running on a
    DB that's already at 128 (or larger) is a no-op. We also guard with
    ``information_schema.columns`` so an environment that doesn't have
    the alembic_version table yet (first-ever bootstrap) is unaffected.

    This widening lives in env.py instead of a migration because the
    column has to be wide enough BEFORE the very first multi-segment
    revision tries to write itself into version_num — chicken-and-egg
    if we tried to do it inside a migration that would itself try to
    persist a >32-char revision id.

    The widening runs in its own committed transaction so it persists
    even when alembic later rolls back (e.g. transactional_ddl=False
    deployments, or a downstream migration error).
    """
    # ``commit()`` is needed because run_sync hands us a connection that
    # the async wrapper auto-commits only at the top-level transaction
    # boundary. Issuing an explicit commit here makes the widening
    # durable even if a downstream migration aborts the outer txn.
    sync_conn.exec_driver_sql(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'alembic_version'
                  AND column_name = 'version_num'
                  AND character_maximum_length IS NOT NULL
                  AND character_maximum_length < 128
            ) THEN
                ALTER TABLE alembic_version
                ALTER COLUMN version_num TYPE VARCHAR(128);
            END IF;
        END $$;
        """
    )
    sync_conn.commit()


def _pre_create_alembic_version_table(sync_conn) -> None:
    """Round-15 R15-DB-ENV — pre-create alembic_version with VARCHAR(128).

    Why this exists. ``_widen_alembic_version_column`` (above) only
    widens an EXISTING column. On a freshly-provisioned Postgres
    database (Render's first deploy onto an empty DB) the
    ``alembic_version`` table does not yet exist, so the widener
    no-ops. Alembic then creates the table inside
    ``context.run_migrations()`` with its hardcoded default
    ``VARCHAR(32)`` (alembic does not expose a public API to override
    the width). The very next INSERT of a >32-char revision id raises
    ``StringDataRightTruncationError`` — the post-revert symptom on
    Render.

    Pre-creating the table here, with the same primary-key shape
    alembic would have created but at VARCHAR(128), makes the
    chicken-and-egg disappear. Alembic's ``CREATE TABLE IF NOT
    EXISTS`` guard later sees the table already exists and uses it
    as-is. ``ON CONFLICT DO NOTHING`` is not needed — the CREATE is
    itself idempotent via ``IF NOT EXISTS``.
    """
    sync_conn.exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS alembic_version (
            version_num VARCHAR(128) NOT NULL,
            CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
        )
        """
    )
    sync_conn.commit()


def do_run_migrations(connection):
    # Round-11 R11-DB-ENV — widen alembic_version.version_num on legacy
    # Postgres databases so multi-segment revision IDs (>32 chars) can
    # be persisted by alembic's own bookkeeping UPDATE.
    #
    # Round-15 R15-DB-ENV — also pre-create the table with VARCHAR(128)
    # so fresh Postgres databases don't fall through to alembic's own
    # CREATE TABLE (which hardcodes VARCHAR(32)). The widener handles
    # legacy DBs that already have the column at 32; the pre-create
    # handles brand-new DBs.
    dialect_name = getattr(connection.dialect, "name", "")
    if dialect_name == "postgresql":
        _pre_create_alembic_version_table(connection)
        _widen_alembic_version_column(connection)
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


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
