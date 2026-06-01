"""Round-19 Phase 12 — complete optimistic-locking rollout (D-009).

Phase 2 (F-017) added ``row_version`` to ``quotes``; Phase 7 extended it
to ``customers``, ``opportunities``, ``contracts``. This migration
finishes the rollout across the remaining seven mutable entities so the
generic ``guarded_update`` helper can lock every race-prone row:

    invoices, subscriptions, campaigns, leads, email_requests,
    workflow_rules, approval_rules

Idempotent. ``NOT NULL DEFAULT 1`` so legacy rows lock at version 1
without a back-fill pass. Wrapped in a table-exists guard so the
migration is safe on partial schemas (feature-flagged tables that may
not exist on every deploy, e.g. subscriptions).

Revision ID: 20260703_phase12_occ_complete
Revises: 20260702_phase8_roadmap
"""

from __future__ import annotations

from alembic import op


revision = "20260703_phase12_occ_complete"
down_revision = "20260702_phase8_roadmap"
branch_labels = None
depends_on = None


_TABLES = (
    "invoices",
    "subscriptions",
    "campaigns",
    "leads",
    "email_requests",
    "workflow_rules",
    "approval_rules",
)


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
