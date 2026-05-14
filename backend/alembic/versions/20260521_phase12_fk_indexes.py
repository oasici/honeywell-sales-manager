"""Round-15 F-003 — cover 80 unindexed FK columns identified by the deep audit.

Round-11 ``20260517_phase11_fk_indexes`` covered ~46 FKs. The deep
cross-layer audit found 80 more — mostly admin-page lookups
(``created_by``, ``owner_id``, ``user_id``) plus a few hot
relationships (``invoices.quote_id``, ``quotes.parent_quote_id``).

Without a covering index, ``WHERE fk = N`` lookups and
``JOIN ... ON ...`` joins seq-scan. The performance hit is invisible
in dev / Render free tier, but a real tenant with N rows incurs
O(N) work per query.

Pattern: idempotent ``CREATE INDEX IF NOT EXISTS`` per (table, column).
asyncpg constraint: each ``op.execute()`` carries exactly one
statement.

Revision ID: 20260521_phase12_fk_indexes
Revises: 20260520_r15_ccy_followup
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op


revision = "20260521_phase12_fk_indexes"
down_revision = "20260520_r15_ccy_followup"
branch_labels = None
depends_on = None


# (table, column) pairs identified by the audit's FK-index scan.
# Indexes named ``ix_<table>_<column>`` for consistency with Round-11.
_INDEXES: list[tuple[str, str]] = [
    ("ai_attribute_definitions", "created_by"),
    ("api_keys", "user_id"),
    ("approval_rules", "approver_user_id"),
    ("approval_rules", "delegate_to"),
    ("audit_logs", "user_id"),
    ("auto_response_rules", "created_by"),
    ("breach_notifications", "created_by"),
    ("calendar_connections", "user_id"),
    ("chat_sessions", "assigned_agent_id"),
    ("coaching_plans", "manager_id"),
    ("comments", "user_id"),
    ("comments", "parent_id"),
    ("crm_connections", "created_by"),
    ("custom_fields", "created_by"),
    ("dashboard_configs", "owner_id"),
    ("dead_letter_events", "replayed_by"),
    ("dna_recommendations", "source_pattern_id"),
    ("feature_usage", "user_id"),
    ("lead_assignment_rules", "assign_to_user_id"),
    ("pipelines", "created_by"),
    ("playbooks", "created_by"),
    ("relationship_scores", "strongest_edge_id"),
    ("report_folders", "parent_id"),
    ("report_folders", "owner_id"),
    ("segments", "created_by"),
    ("selling_guides", "created_by"),
    ("sequences", "created_by"),
    ("sharing_rules", "share_with_user_id"),
    ("signature_requests", "created_by"),
    ("territories", "created_by"),
    ("webhook_subscriptions", "created_by"),
    ("workflow_rules", "created_by"),
    ("approval_requests", "rule_id"),
    ("approval_requests", "requested_by"),
    ("approval_requests", "decided_by"),
    ("crm_field_mappings", "connection_id"),
    ("customers", "created_by"),
    ("playbook_performance", "playbook_id"),
    ("report_templates", "created_by"),
    ("report_templates", "folder_id"),
    ("customer_pricing", "spare_part_id"),
    ("customer_pricing", "created_by"),
    ("user_customer_pins", "customer_id"),
    ("activity_logs", "user_id"),
    ("deal_rooms", "created_by"),
    ("deal_similarity_links", "similar_opportunity_id"),
    ("email_requests", "assigned_to"),
    ("email_requests", "reviewed_by"),
    ("forecast_adjustments", "adjusted_by"),
    ("leads", "converted_customer_id"),
    ("leads", "converted_opportunity_id"),
    ("leads", "converted_by"),
    ("pipeline_review_queue", "decided_by"),
    ("playbook_adherence", "playbook_id"),
    ("playbook_adherence", "step_id"),
    ("stakeholders", "created_by"),
    ("transcripts", "created_by"),
    ("ai_training_data", "created_by"),
    ("campaign_members", "lead_id"),
    ("campaign_members", "customer_id"),
    ("decision_nodes", "owner_stakeholder_id"),
    ("meeting_auto_links", "meeting_booking_id"),
    ("meeting_auto_links", "customer_id"),
    ("playbook_executions", "triggered_by_signal_id"),
    ("quotes", "created_by"),
    ("quotes", "approved_by"),
    ("quotes", "parent_quote_id"),
    ("quotes", "superseded_by"),
    ("sequence_enrollments", "customer_id"),
    ("sequence_enrollments", "enrolled_by"),
    ("contracts", "created_by"),
    ("quote_items", "spare_part_id"),
    ("shared_documents", "created_by"),
    ("subscriptions", "quote_id"),
    ("subscriptions", "created_by"),
    ("contract_amendments", "approved_by"),
    ("invoices", "quote_id"),
    ("invoices", "contract_id"),
    ("invoices", "created_by"),
    ("revenue_schedules", "created_by"),
]


def upgrade() -> None:
    for table, column in _INDEXES:
        # NB: alembic wraps each migration in a transaction; CONCURRENTLY
        # is therefore not available here. Indexes are created with a
        # short table lock — acceptable for our deployment cadence
        # (Render free tier; tables are small).
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} "
            f"ON {table} ({column})"
        )


def downgrade() -> None:
    for table, column in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_{column}")
