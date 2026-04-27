"""V7 DNA uplift columns: Bayesian-smoothed lift + CI

Revision ID: 20260427_v7_dna_uplift
Revises: 20260427_v6_federated_stub
Create Date: 2026-04-27

Adds smoothed uplift columns to ``dna_patterns`` so the
DNA→playbook promoter can filter on credible-interval lower bounds
instead of raw lift, which over-promotes low-support patterns.

Idempotent (``ADD COLUMN IF NOT EXISTS``).
"""

from alembic import op


revision = "20260427_v7_dna_uplift"
down_revision = "20260427_v6_federated_stub"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for ddl in (
        "ALTER TABLE dna_patterns ADD COLUMN IF NOT EXISTS smoothed_win_rate DOUBLE PRECISION",
        "ALTER TABLE dna_patterns ADD COLUMN IF NOT EXISTS uplift_score DOUBLE PRECISION",
        "ALTER TABLE dna_patterns ADD COLUMN IF NOT EXISTS ci_low DOUBLE PRECISION",
        "ALTER TABLE dna_patterns ADD COLUMN IF NOT EXISTS ci_high DOUBLE PRECISION",
        "ALTER TABLE dna_patterns ADD COLUMN IF NOT EXISTS is_promotable BOOLEAN NOT NULL DEFAULT FALSE",
    ):
        op.execute(ddl)


def downgrade() -> None:
    for col in (
        "is_promotable",
        "ci_high",
        "ci_low",
        "uplift_score",
        "smoothed_win_rate",
    ):
        op.execute(f"ALTER TABLE dna_patterns DROP COLUMN IF EXISTS {col}")
