"""Round-15 Sprint 15r cohort 8 — promote tenant_id NOT NULL on 3 opp-derived tables.

Three more opportunity-derived tables with clean NOT NULL parent FK
chains to ``opportunities.tenant_id`` (NOT NULL since Sprint 15k):

  * ``opportunity_text_embeddings``        — opportunity_id PK
  * ``opportunity_transformer_seq_embeddings`` — opportunity_id PK
  * ``recommended_action_windows``         — opportunity_id NOT NULL

Standard 4-step asyncpg-safe contract.

Revision ID: 20260612_phase13_tenant_not_null_cohort8
Revises: 20260611_phase13_tenant_not_null_cohort7
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op


revision = "20260612_phase13_tenant_not_null_cohort8"
down_revision = "20260611_phase13_tenant_not_null_cohort7"
branch_labels = None
depends_on = None


_BACKFILL_PLAN: tuple[tuple[str, str, str, str], ...] = (
    ("opportunity_text_embeddings", "opportunities", "opportunity_id", "id"),
    (
        "opportunity_transformer_seq_embeddings",
        "opportunities",
        "opportunity_id",
        "id",
    ),
    ("recommended_action_windows", "opportunities", "opportunity_id", "id"),
)

_TABLES: tuple[str, ...] = tuple(plan[0] for plan in _BACKFILL_PLAN)


def upgrade() -> None:
    for table, parent, fk_col, pk_col in _BACKFILL_PLAN:
        op.execute(
            f"""
            UPDATE {table} c
            SET tenant_id = p.tenant_id
            FROM {parent} p
            WHERE c.tenant_id IS NULL
              AND c.{fk_col} = p.{pk_col}
              AND p.tenant_id IS NOT NULL
            """
        )

    for table in _TABLES:
        op.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (SELECT id FROM tenants ORDER BY id LIMIT 1)
            WHERE tenant_id IS NULL
              AND (SELECT COUNT(*) FROM tenants) = 1
            """
        )

    for table in _TABLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF (SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL) > 0 THEN
                RAISE EXCEPTION
                  'Sprint 15r cohort 8: cannot promote {table}.tenant_id to NOT NULL — orphan rows remain. See docs/runbooks/r15k-tenant-orphan-backfill.md.';
              END IF;
            END $$
            """
        )

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id DROP NOT NULL")
