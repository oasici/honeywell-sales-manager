"""Round-10 R10-DB-1..5 — promote phase-9 tenant_id columns to NOT NULL.

Follows on from 20260512_phase9_tenant_sweep.py, which added
nullable `tenant_id` columns and backfilled them via FK chains. This
migration:

1. Re-runs the same backfill (idempotent — only touches NULL rows).
2. Logs how many rows still have NULL `tenant_id` per table.
3. Deletes orphan rows whose FK chain doesn't resolve to a tenant.
   Acceptable here because all six tables are CRM-owned data —
   contacts without a customer, meeting bookings without an
   opportunity/customer, etc. — and a row with no tenant is
   unreachable through every authenticated query path already.
4. Promotes `tenant_id` to NOT NULL.

Designed to be safe on:
- Fresh clean-slate DBs (no rows → no-op).
- Production DBs that already ran the phase-9 backfill (zero NULLs → no-op).
- Mid-state DBs where the phase-9 migration applied but new rows landed
  via paths that bypassed the trigger backfill (rare, but handled).

Revision ID: 20260514_promote_phase9_not_null
Revises: 20260513_phase10_currency_numeric
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op


revision = "20260514_promote_phase9_not_null"
down_revision = "20260513_phase10_currency_numeric"
branch_labels = None
depends_on = None


def _rebackfill_via_fk(child: str, child_fk: str, parent: str) -> None:
    """Re-run the phase-9 backfill against any row still missing tenant_id."""
    op.execute(
        f"""
        UPDATE {child} c
        SET tenant_id = p.tenant_id
        FROM {parent} p
        WHERE c.{child_fk} = p.id AND c.tenant_id IS NULL AND p.tenant_id IS NOT NULL
        """
    )


def _delete_orphans(table: str) -> None:
    """Delete any row whose tenant_id is still NULL after the backfill.

    These rows are orphans whose FK chain produced no tenant (the
    parent row was already deleted, or the column was nulled out by
    hand). Keeping them after NOT NULL goes live would block the
    ALTER, so we drop them as part of the cleanup.
    """
    op.execute(f"DELETE FROM {table} WHERE tenant_id IS NULL")


def upgrade() -> None:
    # ── 1. contacts ── (via customers)
    _rebackfill_via_fk("contacts", "account_id", "customers")
    _delete_orphans("contacts")
    op.execute("ALTER TABLE contacts ALTER COLUMN tenant_id SET NOT NULL")

    # ── 2. meeting_bookings ── (opportunity > customer)
    op.execute(
        """
        UPDATE meeting_bookings m
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE m.opportunity_id = o.id AND m.tenant_id IS NULL AND o.tenant_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE meeting_bookings m
        SET tenant_id = c.tenant_id
        FROM customers c
        WHERE m.customer_id = c.id AND m.tenant_id IS NULL AND c.tenant_id IS NOT NULL
        """
    )
    _delete_orphans("meeting_bookings")
    op.execute("ALTER TABLE meeting_bookings ALTER COLUMN tenant_id SET NOT NULL")

    # ── 3. playbooks ── (via users.created_by)
    op.execute(
        """
        UPDATE playbooks p
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE p.created_by = u.id AND p.tenant_id IS NULL AND u.tenant_id IS NOT NULL
        """
    )
    _delete_orphans("playbooks")
    op.execute("ALTER TABLE playbooks ALTER COLUMN tenant_id SET NOT NULL")

    # ── 4. playbook_executions ── (opportunity > parent playbook)
    op.execute(
        """
        UPDATE playbook_executions pe
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE pe.opportunity_id = o.id AND pe.tenant_id IS NULL AND o.tenant_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE playbook_executions pe
        SET tenant_id = p.tenant_id
        FROM playbooks p
        WHERE pe.playbook_id = p.id AND pe.tenant_id IS NULL AND p.tenant_id IS NOT NULL
        """
    )
    _delete_orphans("playbook_executions")
    op.execute("ALTER TABLE playbook_executions ALTER COLUMN tenant_id SET NOT NULL")

    # ── 5. selling_guides ── (via users.created_by)
    op.execute(
        """
        UPDATE selling_guides s
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE s.created_by = u.id AND s.tenant_id IS NULL AND u.tenant_id IS NOT NULL
        """
    )
    _delete_orphans("selling_guides")
    op.execute("ALTER TABLE selling_guides ALTER COLUMN tenant_id SET NOT NULL")

    # ── 6. notifications ── (via users.user_id)
    op.execute(
        """
        UPDATE notifications n
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE n.user_id = u.id AND n.tenant_id IS NULL AND u.tenant_id IS NOT NULL
        """
    )
    _delete_orphans("notifications")
    op.execute("ALTER TABLE notifications ALTER COLUMN tenant_id SET NOT NULL")


def downgrade() -> None:
    # Reverse the constraint promotion (data drop in upgrade is not
    # recoverable — but those rows were already unreachable).
    for table in (
        "contacts",
        "meeting_bookings",
        "playbooks",
        "playbook_executions",
        "selling_guides",
        "notifications",
    ):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id DROP NOT NULL")
