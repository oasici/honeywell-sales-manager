"""V5 foundation: extend account/rep features daily + add contacts

Revision ID: 20260427_v5_foundation
Revises: 20260429_v4_sales_dna_snapshots
Create Date: 2026-04-27

V4 already shipped narrow ``account_features_daily`` and
``rep_features_daily`` tables. V5 expands them with the columns the
plan §1 calls for, and adds the new ``contacts`` entity (separate from
``customers``, which today conflates company + person).

All DDL uses ``IF NOT EXISTS`` / ``ADD COLUMN IF NOT EXISTS`` so this
migration is safe to re-run from any partial state.
"""

from alembic import op


revision = "20260427_v5_foundation"
down_revision = "20260429_v4_sales_dna_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── account_features_daily: add V5 columns ──
    for ddl in (
        "ALTER TABLE account_features_daily ADD COLUMN IF NOT EXISTS avg_momentum DOUBLE PRECISION",
        "ALTER TABLE account_features_daily ADD COLUMN IF NOT EXISTS stakeholder_coverage_avg DOUBLE PRECISION",
        "ALTER TABLE account_features_daily ADD COLUMN IF NOT EXISTS buyer_engagement_score DOUBLE PRECISION",
        "ALTER TABLE account_features_daily ADD COLUMN IF NOT EXISTS objection_density_30d DOUBLE PRECISION NOT NULL DEFAULT 0",
        "ALTER TABLE account_features_daily ADD COLUMN IF NOT EXISTS expansion_signal_score DOUBLE PRECISION NOT NULL DEFAULT 0",
    ):
        op.execute(ddl)

    # ── rep_features_daily: add V5 columns ──
    for ddl in (
        "ALTER TABLE rep_features_daily ADD COLUMN IF NOT EXISTS objection_recovery_rate DOUBLE PRECISION",
        "ALTER TABLE rep_features_daily ADD COLUMN IF NOT EXISTS sequence_adherence_rate DOUBLE PRECISION",
        "ALTER TABLE rep_features_daily ADD COLUMN IF NOT EXISTS stage_slippage_rate DOUBLE PRECISION",
        "ALTER TABLE rep_features_daily ADD COLUMN IF NOT EXISTS discount_dependence DOUBLE PRECISION",
        "ALTER TABLE rep_features_daily ADD COLUMN IF NOT EXISTS sample_deals INTEGER NOT NULL DEFAULT 0",
    ):
        op.execute(ddl)

    # ── contacts ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            name VARCHAR(200) NOT NULL,
            title VARCHAR(160),
            department VARCHAR(120),
            email VARCHAR(255),
            phone VARCHAR(60),
            seniority_score INTEGER NOT NULL DEFAULT 50,
            is_decision_maker BOOLEAN NOT NULL DEFAULT FALSE,
            linkedin_url VARCHAR(400),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_contacts_account_id ON contacts (account_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_contacts_email ON contacts (email)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contacts")
    for col in (
        "expansion_signal_score",
        "objection_density_30d",
        "buyer_engagement_score",
        "stakeholder_coverage_avg",
        "avg_momentum",
    ):
        op.execute(f"ALTER TABLE account_features_daily DROP COLUMN IF EXISTS {col}")
    for col in (
        "sample_deals",
        "discount_dependence",
        "stage_slippage_rate",
        "sequence_adherence_rate",
        "objection_recovery_rate",
    ):
        op.execute(f"ALTER TABLE rep_features_daily DROP COLUMN IF EXISTS {col}")
