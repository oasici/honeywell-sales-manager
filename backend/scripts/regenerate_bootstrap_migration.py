"""Regenerate the bootstrap migration body from current Base.metadata.

Run this when:
  - A new table is added to a model that NO migration creates.
  - An existing legacy table gets a new column / index that should be
    part of the first-boot snapshot.

DO NOT run this lightly. The bootstrap is a snapshot of "what
production already had at first boot"; once it's stable, prefer
authoring incremental migrations for new changes. Regenerating
indiscriminately would shift the boundary between bootstrap-vs-
incremental and could mask drift.

Usage:
  cd backend
  DATABASE_URL=postgresql+asyncpg://x:x@127.0.0.1:65432/legacy \\
    JWT_SECRET_KEY=test ENV=development \\
    python scripts/regenerate_bootstrap_migration.py

Requires a live Postgres at the URL (used only to compile DDL via
SQLAlchemy's pg dialect). Output overwrites
``alembic/versions/20260101_bootstrap_legacy.py``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy.dialects.postgresql import dialect as pg_dialect
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models  # noqa: F401  — registers all models on Base
from app.core.database import Base


VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic" / "versions"
TARGET = VERSIONS_DIR / "20260101_bootstrap_legacy.py"


def _migration_owned_tables() -> set[str]:
    """Always returns an empty set — bootstrap owns ALL tables.

    Earlier iterations of this script tried to filter the bootstrap
    to "tables no migration creates", but the resulting bootstrap
    couldn't satisfy FKs that crossed the bootstrap / migration
    boundary (e.g. ``account_enrichments`` FK to ``customers``).

    The cleanest invariant is: bootstrap creates EVERY table the
    model declares, in dependency order, with IF NOT EXISTS. The 20
    ``op.create_table(...)`` calls in subsequent migrations get a
    has-table guard via ``backend/alembic/_create_table_helper.py``
    so they're no-ops on bootstrapped envs.
    """
    return set()


def _bootstrap_ddl() -> str:
    """Compile CREATE TABLE + CREATE INDEX for every bootstrap table."""
    owned = _migration_owned_tables()
    dialect = pg_dialect()
    chunks: list[str] = ["-- Bootstrap DDL — auto-generated from Base.metadata at HEAD"]
    indexes: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name in owned:
            continue
        ct = CreateTable(table, if_not_exists=True)
        chunks.append(str(ct.compile(dialect=dialect)).strip().rstrip(";") + ";")
        for idx in table.indexes:
            ci = CreateIndex(idx, if_not_exists=True)
            indexes.append(str(ci.compile(dialect=dialect)).strip().rstrip(";") + ";")
    chunks.append("\n-- Indexes")
    chunks.extend(indexes)
    return "\n\n".join(chunks)


_TEMPLATE = '''"""Bootstrap legacy tables that pre-date alembic adoption

Revision ID: 20260101_bootstrap_legacy
Revises:
Create Date: 2026-05-04

The tables below were created by ``Base.metadata.create_all()`` at
first boot of the production database in 2024-2025, before alembic
was wired in. No migration in the chain creates them — every
subsequent migration ALTERs them on the assumption they exist.

Round-4 audit (R4-DB-1, R4-DB-2) flagged this as a fragility: the CI
"schema-drift check" step needs a full ``alembic upgrade head`` from
an empty schema, which would otherwise fail at the first ``op.add_
column("customers", ...)`` call.

This migration is the head of the chain (``down_revision = None``);
the previous root (20260413_add_customer_parent_id) now depends on it.

The DDL is auto-generated from ``Base.metadata`` at HEAD via
``backend/scripts/regenerate_bootstrap_migration.py``. To regenerate
after a model change, re-run that script — or just author a new
incremental migration; the bootstrap is now a snapshot we don't edit
by hand.

Idempotent in both directions:
  - upgrade() uses CREATE TABLE/INDEX IF NOT EXISTS so it's a no-op
    on existing prod and on re-runs.
  - downgrade() is a no-op (refusing to drop production data).
"""

from alembic import op


revision = "20260101_bootstrap_legacy"
down_revision = None
branch_labels = None
depends_on = None


# Auto-generated from Base.metadata; do not edit by hand.
# Regenerate via backend/scripts/regenerate_bootstrap_migration.py.
_BOOTSTRAP_DDL = r"""
{ddl}
"""


def upgrade() -> None:
    # Widen alembic's own version_num column. Default is VARCHAR(32),
    # but the chain has revision IDs up to 33 chars (e.g.
    # ``20260425_activity_logs_source_ref``). Without this, alembic
    # crashes on the first revision-stamp UPDATE with
    # StringDataRightTruncationError. Idempotent.
    op.execute(
        "ALTER TABLE alembic_version "
        "ALTER COLUMN version_num TYPE VARCHAR(64)"
    )

    # PostgreSQL does not allow multi-statement DDL inside a single
    # ``execute()`` call when transactional DDL is in play, so split
    # the embedded DDL into individual statements first.
    #
    # Strip line-comments (``-- ...``) before splitting so they don't
    # get glued onto the first statement and cause the whole chunk
    # to be filtered out (round-4 v1.9.14 incident).
    cleaned_lines = [
        line for line in _BOOTSTRAP_DDL.splitlines()
        if not line.lstrip().startswith("--")
    ]
    cleaned = "\\n".join(cleaned_lines)
    for stmt in cleaned.split(";\\n"):
        stmt = stmt.strip()
        if not stmt:
            continue
        op.execute(stmt + ";")


def downgrade() -> None:
    # Refuse to drop production tables. If you need a clean slate,
    # do it with ``DROP SCHEMA public CASCADE`` outside alembic.
    pass
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print stats without writing the migration file",
    )
    args = parser.parse_args()

    ddl = _bootstrap_ddl()
    table_count = ddl.count("CREATE TABLE")
    index_count = ddl.count("CREATE INDEX")
    print(f"Bootstrap tables:  {table_count}")
    print(f"Bootstrap indexes: {index_count}")
    if args.dry_run:
        return
    assert '"""' not in ddl, "DDL contains triple-quotes; cannot embed"
    TARGET.write_text(_TEMPLATE.format(ddl=ddl))
    print(f"Wrote {TARGET} ({TARGET.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
