"""Round-15 F-002 / Sprint 15j cohort 12 — defense-in-depth tenant_id on four more derived tables.

Continues the cohort 1-11 pattern. This revision covers four tables
with two distinct parents:

  * ``deal_replay_deltas`` — per-(opportunity, time-range) change
    log (backfill from ``opportunities.tenant_id``).
  * ``opportunity_text_embeddings`` — per-opportunity bigram BoW
    vector (PK = opportunity_id) (backfill from ``opportunities``).
  * ``opportunity_transformer_seq_embeddings`` — per-opportunity
    sequence embedding from the V12 transformer (PK = opportunity_id)
    (backfill from ``opportunities``).
  * ``contract_amendments`` — per-contract change record
    (backfill from ``contracts.tenant_id``).

Nullable on disk per the cohort convention. The audit's parked
F-001 Sprint 15k/l NOT-NULL promotion remains parked — see
``docs/audits/2026-05-13-deep-cross-layer-audit.md`` notes.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement.

Revision ID: 20260602_phase12_tenant_did_cohort12
Revises: 20260601_phase12_tenant_did_cohort11
Create Date: 2026-05-15
"""

from __future__ import annotations

from alembic import op


revision = "20260602_phase12_tenant_did_cohort12"
down_revision = "20260601_phase12_tenant_did_cohort11"
branch_labels = None
depends_on = None


# (child_table, parent_table, fk_column_on_child)
_TABLES: list[tuple[str, str, str]] = [
    ("deal_replay_deltas", "opportunities", "opportunity_id"),
    ("opportunity_text_embeddings", "opportunities", "opportunity_id"),
    ("opportunity_transformer_seq_embeddings", "opportunities", "opportunity_id"),
    ("contract_amendments", "contracts", "contract_id"),
]


def upgrade() -> None:
    for table, parent, fk_col in _TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
        )
        op.execute(
            f"""
            UPDATE {table} c
            SET tenant_id = p.tenant_id
            FROM {parent} p
            WHERE c.tenant_id IS NULL
              AND c.{fk_col} = p.id
              AND p.tenant_id IS NOT NULL
            """
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id "
            f"ON {table} (tenant_id)"
        )


def downgrade() -> None:
    for table, _parent, _fk in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_tenant_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")
