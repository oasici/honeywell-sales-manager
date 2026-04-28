"""V9 quote revisions

Revision ID: 20260428_v9_quote_revisions
Revises: 20260428_v9_nl_search
Create Date: 2026-04-28

V2 Faz 3.4 #24 — versioned quotes under one opportunity (revision tree).

Idempotent (``ADD COLUMN IF NOT EXISTS``).
"""

from alembic import op


revision = "20260428_v9_quote_revisions"
down_revision = "20260428_v9_nl_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS parent_quote_id INTEGER REFERENCES quotes(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS revision_no INTEGER NOT NULL DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS superseded_by INTEGER REFERENCES quotes(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_quotes_parent_revision ON quotes (parent_quote_id, revision_no)"
    )


def downgrade() -> None:
    for col in ("superseded_by", "revision_no", "parent_quote_id"):
        op.execute(f"ALTER TABLE quotes DROP COLUMN IF EXISTS {col}")
