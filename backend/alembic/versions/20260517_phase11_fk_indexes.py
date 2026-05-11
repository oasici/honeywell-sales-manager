"""Round-11 R11-DB-IDX — index foreign-key columns flagged by the audit.

The audit identified ~34 high-traffic foreign-key columns that lack
their own btree index. Most JOIN/WHERE queries on these columns
currently force sequential scans, which compound under list endpoints
that filter or aggregate by FK.

Round-11 picks the FK columns that:
  1. drive list-endpoint filters or detail-page joins, and
  2. are not already covered by a composite index whose leading
     column matches (composite-covered FKs are listed in the
     migration docstring but skipped here).

``CREATE INDEX IF NOT EXISTS`` makes the migration safe to re-run
and safe against the small population of indexes that may already
exist under a non-canonical name from older bootstrap snapshots —
the worst case is an extra ~8 bytes/row, not a duplicate failure.

Indexes created (45):

invoice:       quote_id, contract_id
lead:          converted_customer_id, converted_opportunity_id, converted_by
opportunity:   owner_id, customer_id (redundant with composite if present;
               kept for single-column query planner hints)
quote:         created_by, approved_by, parent_quote_id
contract:      created_by, approved_by
campaign:      created_by, customer_id, lead_id
chat:          assigned_agent_id, created_by, session_id
deal_replay_snapshot: opportunity_id
sales_dna_snapshot:   opportunity_id
audit_log:     user_id
approval_rules: approver_user_id, delegate_to, requested_by, assigned_to,
               decided_by
revenue_schedules: contract_id, created_by
forecast_adjustments: opportunity_id, adjusted_by
forecast_snapshot_details: snapshot_id, opportunity_id
territory:     parent_id, created_by
pricing.price_tiers: price_entry_id, customer_id, spare_part_id, created_by
report_templates: created_by, folder_id
report_folders: parent_id, owner_id
sequence_v2.sequence_step_runs: created_by
signature_requests: created_by
shared_documents: created_by
comments:      user_id, parent_id

Revision ID: 20260517_phase11_fk_indexes
Revises: 20260516_phase11_audit_timestamps
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op


revision = "20260517_phase11_fk_indexes"
down_revision = "20260516_phase11_audit_timestamps"
branch_labels = None
depends_on = None


# (table, column) pairs the audit identified as high-impact FK indexes.
# Naming convention: ix_<table>_<column>. Some short table names get a
# shorter prefix to stay under Postgres' 63-char identifier cap.
_INDEXES: tuple[tuple[str, str], ...] = (
    ("invoices", "quote_id"),
    ("invoices", "contract_id"),
    ("leads", "converted_customer_id"),
    ("leads", "converted_opportunity_id"),
    ("leads", "converted_by"),
    ("opportunities", "owner_id"),
    ("opportunities", "customer_id"),
    ("quotes", "created_by"),
    ("quotes", "approved_by"),
    ("quotes", "parent_quote_id"),
    ("contracts", "created_by"),
    ("contracts", "approved_by"),
    ("campaigns", "created_by"),
    ("campaign_members", "customer_id"),
    ("campaign_members", "lead_id"),
    ("chat_sessions", "assigned_agent_id"),
    ("chat_sessions", "created_by"),
    ("chat_messages", "session_id"),
    ("v4_deal_replay_snapshots", "opportunity_id"),
    ("v4_sales_dna_snapshots", "opportunity_id"),
    ("audit_logs", "user_id"),
    ("approval_rules", "approver_user_id"),
    ("approval_rules", "delegate_to"),
    ("approval_requests", "requested_by"),
    ("approval_requests", "assigned_to"),
    ("approval_requests", "decided_by"),
    ("revenue_schedules", "contract_id"),
    ("revenue_schedules", "created_by"),
    ("forecast_adjustments", "opportunity_id"),
    ("forecast_adjustments", "adjusted_by"),
    ("forecast_snapshot_details", "snapshot_id"),
    ("forecast_snapshot_details", "opportunity_id"),
    ("territories", "parent_id"),
    ("territories", "created_by"),
    ("price_tiers", "price_entry_id"),
    ("price_tiers", "customer_id"),
    ("price_tiers", "spare_part_id"),
    ("price_tiers", "created_by"),
    ("report_templates", "created_by"),
    ("report_templates", "folder_id"),
    ("report_folders", "parent_id"),
    ("report_folders", "owner_id"),
    ("sequence_step_runs", "created_by"),
    ("signature_requests", "created_by"),
    ("shared_documents", "created_by"),
    ("comments", "user_id"),
    ("comments", "parent_id"),
)


def _index_name(table: str, column: str) -> str:
    name = f"ix_{table}_{column}"
    # Postgres caps identifiers at 63 characters. None of the entries
    # above hit that today, but a defensive truncation keeps the gate
    # green if a future entry does.
    return name[:63]


def upgrade() -> None:
    for table, column in _INDEXES:
        idx = _index_name(table, column)
        # Wrap in DO block: only create if the underlying table+column
        # actually exist (legacy deployments may not have every table).
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = '{table}'
                      AND column_name = '{column}'
                ) THEN
                    EXECUTE 'CREATE INDEX IF NOT EXISTS {idx} ON {table} ({column})';
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for table, column in _INDEXES:
        idx = _index_name(table, column)
        op.execute(f"DROP INDEX IF EXISTS {idx};")
