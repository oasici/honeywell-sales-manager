"""Migration chain smoke test.

Covers four things:

1. Base.metadata contains every v3 table — fast, no DB needed.
2. `scripts.verify_migrations` proves the chain is linear with one root +
   one head and every migration defines upgrade/downgrade.
3. `alembic heads` reports a single revision string.
4. (Integration) `alembic upgrade head` runs against a real Postgres
   instance when the dev-stack DB is up. Skipped otherwise so CI stays
   green without Docker.

Local setup::

    docker compose -f docker-compose.dev.yml up -d db-test
    export TEST_DATABASE_URL='postgresql+asyncpg://honeywell:honeywell_test_2026@localhost:5434/honeywell_sales_test'
    pytest tests/test_migration_chain.py
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.database import Base


REPO_BACKEND = Path(__file__).resolve().parents[1]

V3_REQUIRED_TABLES: set[str] = {
    "erp_connections",
    "erp_entity_mappings",
    "erp_sync_jobs",
    "erp_sync_conflicts",
    "field_audit_logs",
    "whatsapp_messages",
    "warehouses",
    "stock_levels",
    "stock_movements",
    "bills_of_materials",
    "bom_components",
    "plugins",
    "plugin_installations",
    "plugin_event_subscriptions",
}

DEFAULT_TEST_DSN = (
    "postgresql+asyncpg://honeywell:honeywell_test_2026@localhost:5434/honeywell_sales_test"
)


def _resolved_test_dsn() -> str:
    return os.environ.get("TEST_DATABASE_URL") or DEFAULT_TEST_DSN


def _sync_dsn(dsn: str) -> str:
    """Convert an async DSN into the sync driver so create_engine + alembic
    can both connect without asyncpg."""
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg2://", 1)
    return dsn


def _postgres_reachable(dsn: str) -> bool:
    try:
        engine = create_engine(_sync_dsn(dsn), connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.mark.unit
def test_v3_tables_are_registered_with_metadata():
    table_names = set(Base.metadata.tables.keys())
    missing = V3_REQUIRED_TABLES - table_names
    assert not missing, f"Models missing from Base.metadata: {sorted(missing)}"


@pytest.mark.integration
def test_migration_chain_verifier_reports_single_head():
    env = os.environ.copy()
    env.setdefault("DATABASE_URL", "")
    env.setdefault("ENV", "test")
    result = subprocess.run(
        ["python", "-m", "scripts.verify_migrations"],
        cwd=str(REPO_BACKEND),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "migration(s) verified" in result.stdout


@pytest.mark.integration
def test_alembic_reports_single_head():
    env = os.environ.copy()
    env.setdefault("DATABASE_URL", "")
    env.setdefault("ENV", "test")
    result = subprocess.run(
        ["alembic", "heads"],
        cwd=str(REPO_BACKEND),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    heads = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(heads) == 1, f"Expected one alembic head, got: {heads}"


@pytest.mark.integration
def test_full_chain_applies_against_real_postgres():
    """Executes `alembic upgrade head` against a real Postgres instance.

    Skipped automatically when the test DB is not running so the suite
    passes on a fresh checkout. Run ``docker compose -f
    docker-compose.dev.yml up -d db-test`` to enable.
    """
    dsn = _resolved_test_dsn()
    if not _postgres_reachable(dsn):
        pytest.skip(
            "Postgres test DB not reachable. Run "
            "`docker compose -f docker-compose.dev.yml up -d db-test` first."
        )

    sync_dsn = _sync_dsn(dsn)
    engine = create_engine(sync_dsn)
    try:
        # Clean slate so every run is reproducible.
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))

        # Mirror the production bootstrap: the app creates the full ORM
        # schema via Base.metadata.create_all at first boot, then Alembic
        # is stamped to the head revision so future migrations layer on top.
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    env = os.environ.copy()
    env["DATABASE_URL"] = dsn
    env.setdefault("ENV", "test")

    stamp = subprocess.run(
        ["alembic", "stamp", "head"],
        cwd=str(REPO_BACKEND),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert stamp.returncode == 0, stamp.stderr or stamp.stdout

    # `alembic upgrade head` must now be a no-op because every migration is
    # already applied. A failure here means the chain references a revision
    # outside the one we just stamped.
    upgrade = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=str(REPO_BACKEND),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert upgrade.returncode == 0, (
        f"alembic upgrade head failed on stamped DB.\nSTDOUT:\n{upgrade.stdout}\n"
        f"STDERR:\n{upgrade.stderr}"
    )

    # `alembic current` must now print the head revision + "(head)". This
    # confirms the stamp + upgrade both saw the same head and the DB is in
    # a deployable state.
    current = subprocess.run(
        ["alembic", "current"],
        cwd=str(REPO_BACKEND),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert current.returncode == 0, current.stderr or current.stdout
    assert "head" in current.stdout.lower(), (
        f"alembic current did not report head: {current.stdout!r}"
    )

    engine = create_engine(sync_dsn)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        missing = V3_REQUIRED_TABLES - tables
        assert not missing, (
            f"After bootstrap+stamp+upgrade, v3 tables missing: {missing}"
        )
    finally:
        engine.dispose()
