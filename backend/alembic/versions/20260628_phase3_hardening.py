"""Round-19 Phase 3 — quorum, supersede, pricing source, approval SLA.

F-018 ``approval_rules.quorum_policy`` + ``quorum_n`` + new
  ``approval_decisions`` child table. ``ApprovalRequest`` keeps the
  single status field as the *aggregate*; the child table is the
  per-approver vote ledger that drives that aggregate.

F-026 ``quotes.superseded_by_id`` + ``superseded_at`` so v1 can be
  marked dead when v2 is sent and the API blocks v1 actions.

F-027 ``quote_items.price_source`` enum string column. Set on each
  line at creation by the pricing resolver. Lets the UI explain
  "$X — campaign promo" hover text and lets reports break down
  margin by source.

F-028 ``approval_requests.due_at`` + ``escalated_at`` + ``escalation_level``
  driven by the existing ``ApprovalRule.escalation_hours``. A cron
  finds rows past ``due_at`` and bumps ``escalation_level``,
  reassigning to the rule's escalation chain.

Revision ID: 20260628_phase3_hardening
Revises: 20260627_phase2_hardening
"""

from __future__ import annotations

from alembic import op


revision = "20260628_phase3_hardening"
down_revision = "20260627_phase2_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── F-018: quorum on rules + decision ledger ───────────────────
    op.execute(
        "ALTER TABLE approval_rules "
        "ADD COLUMN IF NOT EXISTS quorum_policy VARCHAR(20) NOT NULL DEFAULT 'any_one'"
    )
    op.execute(
        "ALTER TABLE approval_rules "
        "ADD COLUMN IF NOT EXISTS quorum_n INTEGER"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS approval_decisions (
            id              BIGSERIAL PRIMARY KEY,
            request_id      INTEGER NOT NULL REFERENCES approval_requests(id) ON DELETE CASCADE,
            decider_id      INTEGER NOT NULL REFERENCES users(id),
            outcome         VARCHAR(20) NOT NULL,    -- approve | reject
            comment         TEXT,
            decided_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (request_id, decider_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_approval_decisions_request "
        "ON approval_decisions (request_id, outcome)"
    )

    # ── F-026: quote supersede chain ────────────────────────────────
    op.execute(
        "ALTER TABLE quotes "
        "ADD COLUMN IF NOT EXISTS superseded_by_id INTEGER REFERENCES quotes(id)"
    )
    op.execute(
        "ALTER TABLE quotes "
        "ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_quotes_superseded_by "
        "ON quotes (superseded_by_id) WHERE superseded_by_id IS NOT NULL"
    )

    # ── F-027: price_source on quote_items ─────────────────────────
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'quote_items') THEN
            ALTER TABLE quote_items
              ADD COLUMN IF NOT EXISTS price_source VARCHAR(40) NOT NULL DEFAULT 'catalog',
              ADD COLUMN IF NOT EXISTS price_source_ref VARCHAR(64);
          END IF;
        END $$;
        """
    )

    # ── F-028: SLA timestamps on approval_requests ─────────────────
    op.execute(
        "ALTER TABLE approval_requests "
        "ADD COLUMN IF NOT EXISTS due_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE approval_requests "
        "ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE approval_requests "
        "ADD COLUMN IF NOT EXISTS escalation_level INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_approval_requests_due_status "
        "ON approval_requests (status, due_at) WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE approval_requests DROP COLUMN IF EXISTS escalation_level")
    op.execute("ALTER TABLE approval_requests DROP COLUMN IF EXISTS escalated_at")
    op.execute("ALTER TABLE approval_requests DROP COLUMN IF EXISTS due_at")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'quote_items') THEN
            ALTER TABLE quote_items
              DROP COLUMN IF EXISTS price_source_ref,
              DROP COLUMN IF EXISTS price_source;
          END IF;
        END $$;
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_quotes_superseded_by")
    op.execute("ALTER TABLE quotes DROP COLUMN IF EXISTS superseded_at")
    op.execute("ALTER TABLE quotes DROP COLUMN IF EXISTS superseded_by_id")
    op.execute("DROP TABLE IF EXISTS approval_decisions")
    op.execute("ALTER TABLE approval_rules DROP COLUMN IF EXISTS quorum_n")
    op.execute("ALTER TABLE approval_rules DROP COLUMN IF EXISTS quorum_policy")
