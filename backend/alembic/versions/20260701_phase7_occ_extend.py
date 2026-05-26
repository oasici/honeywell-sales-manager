"""Round-19 Phase 7 — extend optimistic locking + customer support columns.

F-017 follow-up: ``quotes.row_version`` shipped in Phase 2, but
``customers``, ``opportunities``, and ``contracts`` still race-edit
without OCC. This migration adds ``row_version INTEGER NOT NULL
DEFAULT 1`` to all three so the generic ``guarded_update`` helper
can lock them too.

Idempotent. NOT NULL DEFAULT 1 so legacy rows lock at version 1
without back-fill.

Revision ID: 20260701_phase7_occ_extend
Revises: 20260630_phase6_finishing
"""

from __future__ import annotations

from alembic import op


revision = "20260701_phase7_occ_extend"
down_revision = "20260630_phase6_finishing"
branch_labels = None
depends_on = None


_TABLES = ("customers", "opportunities", "contracts")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM information_schema.tables
                         WHERE table_name = '{table}') THEN
                ALTER TABLE {table}
                  ADD COLUMN IF NOT EXISTS row_version INTEGER NOT NULL DEFAULT 1;
              END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM information_schema.tables
                         WHERE table_name = '{table}') THEN
                ALTER TABLE {table} DROP COLUMN IF EXISTS row_version;
              END IF;
            END $$;
            """
        )
