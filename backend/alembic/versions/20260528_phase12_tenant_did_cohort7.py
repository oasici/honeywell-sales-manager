"""Round-15 F-002 / Sprint 15j cohort 7 — defense-in-depth tenant_id on V5 similarity tables.

Continues the cohort 1-6 pattern. This revision covers:
  * ``opportunity_embeddings`` — structured-feature vector per
    opportunity (1-row-per-opp).
  * ``deal_similarity_links`` — pairwise similarity index keyed by
    ``opportunity_id`` (the source side; the ``similar_opportunity_id``
    target inherits tenancy through the source's row).

Both inherit tenancy through ``opportunity_id``. Nullable on disk per
the cohort convention so the migration is non-breaking and reversible.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement.

Revision ID: 20260528_phase12_tenant_did_cohort7
Revises: 20260527_phase12_tenant_did_cohort6
Create Date: 2026-05-14
"""

from __future__ import annotations

from alembic import op


revision = "20260528_phase12_tenant_did_cohort7"
down_revision = "20260527_phase12_tenant_did_cohort6"
branch_labels = None
depends_on = None


_TABLES: list[tuple[str, str]] = [
    ("opportunity_embeddings", "opportunity_id"),
    ("deal_similarity_links", "opportunity_id"),
]


def upgrade() -> None:
    for table, fk_col in _TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
        )
        op.execute(
            f"""
            UPDATE {table} c
            SET tenant_id = o.tenant_id
            FROM opportunities o
            WHERE c.tenant_id IS NULL
              AND c.{fk_col} = o.id
              AND o.tenant_id IS NOT NULL
            """
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id "
            f"ON {table} (tenant_id)"
        )


def downgrade() -> None:
    for table, _ in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_tenant_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")
