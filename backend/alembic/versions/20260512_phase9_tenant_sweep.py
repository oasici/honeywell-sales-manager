"""Round-10 R10-DB-1..7 — phase-9 tenant_id sweep + audit timestamps.

Closes the remaining cross-tenant scoping gaps surfaced by the
Round-10 cross-layer audit (Investigator A). Six tables gain a
nullable ``tenant_id`` column; two gain canonical ``created_at`` /
``updated_at`` audit timestamps.

Backfill strategy:
- ``contacts`` → customer chain (``account_id → customers.tenant_id``)
- ``meeting_bookings`` → opportunity chain (``opportunity_id → opportunities.tenant_id``),
  fall back to customer chain (``customer_id → customers.tenant_id``)
- ``playbooks`` → user chain (``created_by → users.tenant_id``)
- ``playbook_executions`` → opportunity chain (``opportunity_id → opportunities.tenant_id``),
  fall back to parent playbook (``playbook_id → playbooks.tenant_id``)
- ``selling_guides`` → user chain (``created_by → users.tenant_id``)
- ``notifications`` → user chain (``user_id → users.tenant_id``)

The columns remain NULLABLE for now. A follow-up migration
(20260513_promote_phase9_not_null.py) will promote them once the
backfill has been verified clean in staging; doing the promotion in a
second step lets the schema_check gate flag any rows that slipped
through the backfill so they can be inspected before the constraint
goes live.

Tables intentionally NOT touched by this migration (pending business
decision on whether the catalog is global or tenant-local):
- ``product_rules`` (pricing rule catalog)
- ``spare_parts`` (product catalog)
- ``price_entries`` (price book)

Revision ID: 20260512_phase9_tenant_sweep
Revises: 20260510_phase8_tenant_sweep
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op


revision = "20260512_phase9_tenant_sweep"
down_revision = "20260510_phase8_tenant_sweep"
branch_labels = None
depends_on = None


def _add_tenant_id(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id INTEGER NULL")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id ON {table} (tenant_id)")


def _add_timestamps(table: str) -> None:
    op.execute(
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS created_at "
        "TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
    )
    op.execute(
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS updated_at "
        "TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"
    )


def upgrade() -> None:
    # ── 1. contacts — customer chain ──
    _add_tenant_id("contacts")
    op.execute(
        """
        UPDATE contacts c
        SET tenant_id = cust.tenant_id
        FROM customers cust
        WHERE c.account_id = cust.id AND c.tenant_id IS NULL
        """
    )

    # ── 2. meeting_bookings — opportunity > customer ──
    _add_tenant_id("meeting_bookings")
    op.execute(
        """
        UPDATE meeting_bookings m
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE m.opportunity_id = o.id AND m.tenant_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE meeting_bookings m
        SET tenant_id = c.tenant_id
        FROM customers c
        WHERE m.customer_id = c.id AND m.tenant_id IS NULL
        """
    )

    # ── 3. playbooks — created_by chain ──
    _add_tenant_id("playbooks")
    op.execute(
        """
        UPDATE playbooks p
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE p.created_by = u.id AND p.tenant_id IS NULL
        """
    )

    # ── 4. playbook_executions — opportunity > parent playbook ──
    _add_tenant_id("playbook_executions")
    op.execute(
        """
        UPDATE playbook_executions pe
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE pe.opportunity_id = o.id AND pe.tenant_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE playbook_executions pe
        SET tenant_id = p.tenant_id
        FROM playbooks p
        WHERE pe.playbook_id = p.id AND pe.tenant_id IS NULL
        """
    )

    # ── 5. selling_guides — created_by chain ──
    _add_tenant_id("selling_guides")
    op.execute(
        """
        UPDATE selling_guides s
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE s.created_by = u.id AND s.tenant_id IS NULL
        """
    )

    # ── 6. notifications — user chain ──
    _add_tenant_id("notifications")
    op.execute(
        """
        UPDATE notifications n
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE n.user_id = u.id AND n.tenant_id IS NULL
        """
    )

    # ── 7. account_enrichments — audit timestamps ──
    _add_timestamps("account_enrichments")

    # ── 8. quote_items — audit timestamps ──
    _add_timestamps("quote_items")


def downgrade() -> None:
    # Idempotent reverse — drop the columns. Indexes are dropped
    # implicitly when the column goes away.
    for table in (
        "contacts",
        "meeting_bookings",
        "playbooks",
        "playbook_executions",
        "selling_guides",
        "notifications",
    ):
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_tenant_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")

    for table in ("account_enrichments", "quote_items"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS created_at")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS updated_at")
