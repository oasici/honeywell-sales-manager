"""activity_logs: add source_ref for idempotency

Revision ID: 20260425_activity_logs_source_ref
Revises: 20260425_v4_feature_store_daily
Create Date: 2026-04-25

Made idempotent (2026-04-26): an earlier deploy left this revision in a
partially-applied state on Render — the column existed on some replicas
but the index was missing on others, so the next ``alembic upgrade head``
crashed with "column already exists" before reaching newer migrations.
Switching to raw ``ADD COLUMN IF NOT EXISTS`` / ``CREATE INDEX IF NOT
EXISTS`` makes the migration safe to re-run from any partial state.
"""

from alembic import op


revision = "20260425_activity_logs_source_ref"
down_revision = "20260425_v4_feature_store_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres-only DDL. ``IF NOT EXISTS`` makes both statements safe
    # against the partial-apply state described in the module docstring.
    op.execute(
        "ALTER TABLE activity_logs "
        "ADD COLUMN IF NOT EXISTS source_ref VARCHAR(120)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_activity_logs_source_ref "
        "ON activity_logs (source_ref)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_activity_logs_source_ref")
    op.execute("ALTER TABLE activity_logs DROP COLUMN IF EXISTS source_ref")

