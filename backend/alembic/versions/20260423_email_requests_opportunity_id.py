"""email_requests.opportunity_id — v2 opportunity timeline (S2)

Revision ID: 20260423_email_opportunity
Revises: 20260422_opportunity_foundation
Create Date: 2026-04-23

Round-4 v1.9.14 — converted from ``op.batch_alter_table(...)`` to
raw SQL with IF NOT EXISTS / DO $$ guards so the migration is a
no-op on the bootstrapped schema.
"""

from alembic import op


revision = "20260423_email_opportunity"
down_revision = "20260422_opportunity_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE email_requests "
        "ADD COLUMN IF NOT EXISTS opportunity_id INTEGER"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_requests_opportunity_id "
        "ON email_requests (opportunity_id)"
    )
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE email_requests
                ADD CONSTRAINT fk_email_requests_opportunity_id
                FOREIGN KEY (opportunity_id) REFERENCES opportunities(id)
                ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE email_requests "
        "DROP CONSTRAINT IF EXISTS fk_email_requests_opportunity_id"
    )
    op.execute("DROP INDEX IF EXISTS ix_email_requests_opportunity_id")
    op.execute(
        "ALTER TABLE email_requests DROP COLUMN IF EXISTS opportunity_id"
    )
