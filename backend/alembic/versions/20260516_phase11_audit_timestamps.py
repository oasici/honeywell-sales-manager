"""Round-11 R11-DB-TS — add created_at/updated_at to config tables.

The audit caught two config tables that lack proper audit timestamps:
``settings`` only has ``updated_at`` (no ``created_at``) and
``stage_configs`` has neither. Both are administrator-edited surfaces
that benefit from full change history.

Both timestamps are backfilled with ``NOW()`` at column add time so
existing rows get a defined value rather than NULL. The column stays
nullable on disk to keep the migration light; the ORM model declares
``nullable=False`` after deploy so new inserts always carry a value.

Idempotent via ``IF NOT EXISTS`` (Postgres ≥ 9.6).

Round-11 follow-up (CI green-up): each ``op.execute()`` carries exactly
one statement. The original revision packed two-to-four DDL/DML
statements per call, but the asyncpg driver that alembic uses in this
project rejects multi-statement strings (`cannot insert multiple
commands into a prepared statement`). Splitting is the documented fix.

Revision ID: 20260516_phase11_audit_timestamps
Revises: 20260515_phase11_currency_sweep
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op


revision = "20260516_phase11_audit_timestamps"
down_revision = "20260515_phase11_currency_sweep"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── settings.created_at ──
    op.execute(
        "ALTER TABLE settings "
        "ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()"
    )
    op.execute(
        "UPDATE settings "
        "SET created_at = COALESCE(created_at, updated_at, NOW()) "
        "WHERE created_at IS NULL"
    )

    # ── stage_configs.created_at + updated_at ──
    op.execute(
        "ALTER TABLE stage_configs "
        "ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()"
    )
    op.execute(
        "ALTER TABLE stage_configs "
        "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()"
    )
    op.execute(
        "UPDATE stage_configs "
        "SET created_at = COALESCE(created_at, NOW()) "
        "WHERE created_at IS NULL"
    )
    op.execute(
        "UPDATE stage_configs "
        "SET updated_at = COALESCE(updated_at, NOW()) "
        "WHERE updated_at IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE settings DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE stage_configs DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE stage_configs DROP COLUMN IF EXISTS updated_at")
