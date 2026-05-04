"""add customer parent_id for account hierarchy

Revision ID: 20260413_add_customer_parent_id
Revises: 20260101_bootstrap_legacy
Create Date: 2026-04-13

Round-4 migration-consolidation sprint (v1.9.14):
- Re-rooted onto the new bootstrap migration so a fresh env can run
  ``alembic upgrade head`` against an empty schema. Previously this
  was the chain root and assumed ``customers`` already existed via
  ``Base.metadata.create_all()``.
- Switched to idempotent raw SQL so this is a no-op when the bootstrap
  has already created the column / index / FK from the current model
  schema.
"""
from alembic import op


revision = "20260413_add_customer_parent_id"
down_revision = "20260101_bootstrap_legacy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS parent_id INTEGER"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_parent_id "
        "ON customers (parent_id)"
    )
    # FK creation has no IF NOT EXISTS in PG; trap duplicate_object so
    # the migration is safe to re-run after bootstrap.
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE customers
                ADD CONSTRAINT fk_customers_parent_id
                FOREIGN KEY (parent_id) REFERENCES customers(id)
                ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE customers DROP CONSTRAINT IF EXISTS fk_customers_parent_id"
    )
    op.execute("DROP INDEX IF EXISTS ix_customers_parent_id")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS parent_id")
