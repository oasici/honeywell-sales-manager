"""Hotfix: ensure opportunities.source column exists

Revision ID: 20260503_opp_source_safety
Revises: 20260503_create_invoices
Create Date: 2026-05-03

Production crash: the v1.8.0 DB-6 model change added a `source` field
to the Opportunity ORM, but the prod `opportunities` table did not
actually have the column despite migration `20260422_opportunity_foundation`
declaring it. Once the model started referencing the field every
SELECT against `opportunities` raised
`UndefinedColumnError: column opportunities.source does not exist`,
including the `/analytics/revenue-leaks` endpoint that triggered the
Sentry report.

Suspect cause: the prod schema was created via metadata.create_all()
or from an older snapshot of the foundation migration that didn't
include `source`. Either way, the right fix is an idempotent
ADD COLUMN — both fresh envs (where the column already exists from
the foundation migration) and prod (where it doesn't) end up
correctly aligned.

Idempotent both ways. Safe to re-run.
"""

from alembic import op


revision = "20260503_opp_source_safety"
down_revision = "20260503_create_invoices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL ADD COLUMN IF NOT EXISTS — no-op when the column
    # already exists, adds it as nullable VARCHAR(30) when missing.
    # Matches the model declaration in app/models/opportunity.py
    # and the original foundation migration's intent.
    op.execute(
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS source VARCHAR(30)"
    )


def downgrade() -> None:
    # Intentionally no-op: dropping the column would lose the
    # lead-source attribution data we're now writing. If you really
    # need to remove it, write a dedicated drop migration with an
    # explicit data-export step first.
    pass
