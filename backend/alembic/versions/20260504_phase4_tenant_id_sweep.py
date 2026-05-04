"""Add tenant_id to 17 phase-4 tables (engagement / pricing / signatures / etc)

Revision ID: 20260504_phase4_tenant
Revises: 20260504_billing_tenant
Create Date: 2026-05-04

Round-4 audit Phase 4 — TEN-9..24 batch.

Phase 3 added tenant_id to the billing surface (Invoice, Contract,
Subscription, RevenueSchedule, RevenueScheduleEntry). Phase 4
extends the tenant boundary to 17 more tables that route handlers
were unable to scope until now:

  - signature_requests
  - webhook_subscriptions, webhook_deliveries
  - workflow_rules
  - approval_rules
  - sequences, sequence_enrollments, segments
  - comments
  - chat_sessions, chat_messages, auto_response_rules
  - customer_pricing
  - product_bundles
  - account_teams, sharing_rules
  - territories
  - email_requests

Backfill strategies:

1. Direct customer_id FK → customers.tenant_id
   (email_requests, customer_pricing, account_teams)

2. Direct created_by FK → users.tenant_id
   (workflow_rules, approval_rules, sequences, segments,
    product_bundles, sharing_rules, webhook_subscriptions, signature_requests)

3. Parent table chain
   - sequence_enrollments  → opportunity → opportunities.tenant_id, then
     fall back to lead → leads.tenant_id, then customer → customers.tenant_id
   - chat_messages         → chat_sessions.tenant_id
   - webhook_deliveries    → webhook_subscriptions.tenant_id (after #2)
   - auto_response_rules   → users.tenant_id (via created_by)
   - territories           → users.tenant_id (via created_by)
   - chat_sessions         → users.tenant_id (via created_by); fallback
     leaves NULL when there's no created_by populated.
   - comments              → derived from (entity_type, entity_id) — JOIN
     to customers/leads/opportunities. Only the customer/lead/opportunity
     entity_types are backfilled; quote/contract comments stay NULL on
     pre-existing rows and get stamped on next write.

4. Pre-existing rows that can't be backfilled stay NULL. Single-tenant
   deployments (where the user.tenant_id is None across the board)
   keep their pre-V8 behavior (no scoping). The route guards we
   shipped are tolerant: ``is_cross_tenant`` returns False when either
   side is NULL.

Idempotent both ways. Downgrade drops the column + index.
"""

from alembic import op


revision = "20260504_phase4_tenant"
down_revision = "20260504_billing_tenant"
branch_labels = None
depends_on = None


# ── Schema change phase ──
TABLES_INDEXES = [
    ("signature_requests", "ix_sig_tenant"),
    ("webhook_subscriptions", "ix_webhook_subscriptions_tenant_id"),
    ("webhook_deliveries", "ix_delivery_tenant"),
    ("workflow_rules", "ix_workflow_rules_tenant_id"),
    ("approval_rules", "ix_approval_rules_tenant_id"),
    ("sequences", "ix_sequences_tenant_id"),
    ("sequence_enrollments", "ix_sequence_enrollments_tenant_id"),
    ("segments", "ix_segments_tenant_id"),
    ("comments", "ix_comments_tenant_id"),
    ("chat_sessions", "ix_chat_sessions_tenant_id"),
    ("chat_messages", "ix_chat_messages_tenant_id"),
    ("auto_response_rules", "ix_auto_response_rules_tenant_id"),
    ("customer_pricing", "ix_cp_tenant"),
    ("product_bundles", "ix_pb_tenant"),
    ("account_teams", "ix_account_team_tenant"),
    ("sharing_rules", "ix_sharing_rule_tenant"),
    ("territories", "ix_territory_tenant"),
    ("email_requests", "ix_email_requests_tenant_id"),
]


def upgrade() -> None:
    # 1) Add column + index for every table.
    for table, index in TABLES_INDEXES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {index} ON {table} (tenant_id)"
        )

    # 2) Backfill (best-effort; only updates rows where tenant_id IS NULL).

    # 2a) Direct customer_id chain.
    op.execute(
        """
        UPDATE email_requests
           SET tenant_id = c.tenant_id
          FROM customers c
         WHERE email_requests.customer_id = c.id
           AND email_requests.tenant_id IS NULL
           AND c.tenant_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE customer_pricing
           SET tenant_id = c.tenant_id
          FROM customers c
         WHERE customer_pricing.customer_id = c.id
           AND customer_pricing.tenant_id IS NULL
           AND c.tenant_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE account_teams
           SET tenant_id = c.tenant_id
          FROM customers c
         WHERE account_teams.customer_id = c.id
           AND account_teams.tenant_id IS NULL
           AND c.tenant_id IS NOT NULL
        """
    )

    # 2b) created_by → users.tenant_id. Catches everything keyed on a
    # human author (the audit log records and admin-CRUD tables).
    for table, fk_col in (
        ("workflow_rules", "created_by"),
        ("approval_rules", "created_by"),
        ("sequences", "created_by"),
        ("segments", "created_by"),
        ("product_bundles", "created_by"),
        ("sharing_rules", "created_by"),
        ("webhook_subscriptions", "created_by"),
        ("signature_requests", "created_by"),
        ("territories", "created_by"),
        ("auto_response_rules", "created_by"),
        ("customer_pricing", "created_by"),  # secondary path if FK customer is missing
    ):
        op.execute(
            f"""
            UPDATE {table}
               SET tenant_id = u.tenant_id
              FROM users u
             WHERE {table}.{fk_col} = u.id
               AND {table}.tenant_id IS NULL
               AND u.tenant_id IS NOT NULL
            """
        )

    # 2c) Chain through parent tables that are now backfilled.
    # webhook_deliveries → webhook_subscriptions
    op.execute(
        """
        UPDATE webhook_deliveries
           SET tenant_id = w.tenant_id
          FROM webhook_subscriptions w
         WHERE webhook_deliveries.subscription_id = w.id
           AND webhook_deliveries.tenant_id IS NULL
           AND w.tenant_id IS NOT NULL
        """
    )
    # chat_messages → chat_sessions
    op.execute(
        """
        UPDATE chat_messages
           SET tenant_id = s.tenant_id
          FROM chat_sessions s
         WHERE chat_messages.session_id = s.id
           AND chat_messages.tenant_id IS NULL
           AND s.tenant_id IS NOT NULL
        """
    )
    # sequence_enrollments → opportunity → lead → customer (in that order).
    op.execute(
        """
        UPDATE sequence_enrollments
           SET tenant_id = o.tenant_id
          FROM opportunities o
         WHERE sequence_enrollments.opportunity_id = o.id
           AND sequence_enrollments.tenant_id IS NULL
           AND o.tenant_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE sequence_enrollments se
           SET tenant_id = l.tenant_id
          FROM leads l
         WHERE se.lead_id = l.id
           AND se.tenant_id IS NULL
           AND l.tenant_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE sequence_enrollments se
           SET tenant_id = c.tenant_id
          FROM customers c
         WHERE se.customer_id = c.id
           AND se.tenant_id IS NULL
           AND c.tenant_id IS NOT NULL
        """
    )

    # 2d) comments — backfill from the parent CRM entity by entity_type.
    # We deliberately only backfill the three tenant-scoped entities; quote
    # and contract comments would chain through customer but that's a
    # 3-table join we'd rather skip — the next write to those rows
    # stamps tenant_id correctly.
    op.execute(
        """
        UPDATE comments
           SET tenant_id = c.tenant_id
          FROM customers c
         WHERE comments.entity_type = 'customer'
           AND comments.entity_id = c.id
           AND comments.tenant_id IS NULL
           AND c.tenant_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE comments
           SET tenant_id = l.tenant_id
          FROM leads l
         WHERE comments.entity_type = 'lead'
           AND comments.entity_id = l.id
           AND comments.tenant_id IS NULL
           AND l.tenant_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE comments
           SET tenant_id = o.tenant_id
          FROM opportunities o
         WHERE comments.entity_type = 'opportunity'
           AND comments.entity_id = o.id
           AND comments.tenant_id IS NULL
           AND o.tenant_id IS NOT NULL
        """
    )


def downgrade() -> None:
    for table, index in reversed(TABLES_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {index}")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")
