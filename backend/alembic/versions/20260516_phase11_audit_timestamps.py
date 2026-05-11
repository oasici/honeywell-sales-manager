"""Round-11 R11-DB-TS — add created_at/updated_at to config tables.

The audit caught two config tables that lack proper audit timestamps:
``settings`` only has ``updated_at`` (no ``created_at``) and
``stage_configs`` has neither. Both are administrator-edited surfaces
that benefit from full change history.

Each column is added with ``DEFAULT NOW()`` so existing rows are
populated at ALTER time, then a defensive ``UPDATE ... WHERE x IS NULL``
backfills any straggler before the column is promoted to ``NOT NULL``
to match the ORM model declaration. The schema drift gate
(``schema_check.py``) compares model.nullable to DB column nullability;
keeping them in sync is what closes R11-DB-TS.

Idempotent: ``ADD COLUMN IF NOT EXISTS`` is a no-op the second time,
``UPDATE ... WHERE x IS NULL`` matches zero rows, and
``ALTER COLUMN ... SET NOT NULL`` is a no-op on a column that's
already NOT NULL.

asyncpg constraint: each ``op.execute()`` must carry exactly one
statement (asyncpg rejects multi-statement prepared strings with
`cannot insert multiple commands into a prepared statement`).

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
    # Promote to NOT NULL to match the ORM model. The ADD COLUMN +
    # backfill above guarantees every existing row has a non-NULL
    # value, and the DEFAULT NOW() clause keeps future inserts safe
    # without requiring the application to specify the timestamp.
    op.execute("ALTER TABLE settings ALTER COLUMN created_at SET NOT NULL")
    # Settings already had updated_at; the existing migration created
    # it nullable but the ORM model now declares nullable=False, so we
    # also promote it here. Backfill any historical NULLs first.
    op.execute(
        "UPDATE settings "
        "SET updated_at = COALESCE(updated_at, created_at, NOW()) "
        "WHERE updated_at IS NULL"
    )
    op.execute("ALTER TABLE settings ALTER COLUMN updated_at SET NOT NULL")

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
    op.execute("ALTER TABLE stage_configs ALTER COLUMN created_at SET NOT NULL")
    op.execute("ALTER TABLE stage_configs ALTER COLUMN updated_at SET NOT NULL")


def downgrade() -> None:
    # Drop the NOT NULL constraints before dropping the columns so the
    # downgrade is safe on a DB that already promoted them.
    op.execute("ALTER TABLE settings ALTER COLUMN created_at DROP NOT NULL")
    op.execute("ALTER TABLE settings ALTER COLUMN updated_at DROP NOT NULL")
    op.execute("ALTER TABLE settings DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE stage_configs DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE stage_configs DROP COLUMN IF EXISTS updated_at")
