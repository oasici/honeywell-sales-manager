"""Round-8 R8-PII-1 — phase-8 tenant_id sweep.

Adds ``tenant_id`` to nine high-volume / collaboration tables and
backfills via FK chains. Closes the last cross-tenant scoping gaps
called out by the Round-8 audit.

Backfill strategy:
- ``saved_views``, ``user_sessions``, ``feature_usage`` → ``user_id → users.tenant_id``
- ``activity_logs`` → ``opportunity_id → opportunities.tenant_id``,
  fall back to ``customer_id → customers.tenant_id``, then ``user_id → users.tenant_id``
- ``revenue_signals`` → owner_id → users.tenant_id, fallback opportunity
- ``stakeholders`` → opportunity_id → opportunities.tenant_id (else customer)
- ``opportunity_signals`` and ``tasks`` → opportunity_id → opportunities.tenant_id
- ``competitor_mentions`` → opportunity_id → opportunities.tenant_id

Also adds a server-side FK on ``feature_usage.user_id`` (R8-FK-1).

Revision ID: 20260510_phase8_tenant_sweep
Revises: 20260509_drop_dup_v113_tx
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op


revision = "20260510_phase8_tenant_sweep"
down_revision = "20260509_drop_dup_v113_tx"
branch_labels = None
depends_on = None


def _add_tenant_id(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id INTEGER NULL")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id ON {table} (tenant_id)")


def upgrade() -> None:
    # ── 1. saved_views, user_sessions, feature_usage — user-derived ──
    for table in ("saved_views", "user_sessions", "feature_usage"):
        _add_tenant_id(table)
        op.execute(
            f"""
            UPDATE {table} t
            SET tenant_id = u.tenant_id
            FROM users u
            WHERE t.user_id = u.id AND t.tenant_id IS NULL
            """
        )

    # feature_usage gains a real FK; ondelete=SET NULL preserves rows on user removal.
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE feature_usage
                ADD CONSTRAINT fk_feature_usage_user_id
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object THEN
            NULL;
        END $$;
        """
    )

    # ── 2. activity_logs — opportunity > customer > user ──
    _add_tenant_id("activity_logs")
    op.execute(
        """
        UPDATE activity_logs a
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE a.opportunity_id = o.id AND a.tenant_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE activity_logs a
        SET tenant_id = c.tenant_id
        FROM customers c
        WHERE a.customer_id = c.id AND a.tenant_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE activity_logs a
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE a.user_id = u.id AND a.tenant_id IS NULL
        """
    )

    # ── 3. revenue_signals — owner > opportunity ──
    _add_tenant_id("revenue_signals")
    op.execute(
        """
        UPDATE revenue_signals r
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE r.owner_id = u.id AND r.tenant_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE revenue_signals r
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE r.opportunity_id = o.id AND r.tenant_id IS NULL
        """
    )

    # ── 4. stakeholders — opportunity > customer ──
    _add_tenant_id("stakeholders")
    op.execute(
        """
        UPDATE stakeholders s
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE s.opportunity_id = o.id AND s.tenant_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE stakeholders s
        SET tenant_id = c.tenant_id
        FROM customers c
        WHERE s.customer_id = c.id AND s.tenant_id IS NULL
        """
    )

    # ── 5. opportunity_signals, tasks, competitor_mentions — opportunity ──
    for table in ("opportunity_signals", "tasks", "competitor_mentions"):
        _add_tenant_id(table)
        op.execute(
            f"""
            UPDATE {table} t
            SET tenant_id = o.tenant_id
            FROM opportunities o
            WHERE t.opportunity_id = o.id AND t.tenant_id IS NULL
            """
        )

    # tasks: also fallback to owner_id chain when opportunity_id is null.
    op.execute(
        """
        UPDATE tasks t
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE t.owner_id = u.id AND t.tenant_id IS NULL
        """
    )

    # ── 6. dashboard_configs — updated_at column from R8-CAST-2 ──
    op.execute(
        "ALTER TABLE dashboard_configs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL"
    )
    op.execute(
        "UPDATE dashboard_configs SET updated_at = created_at WHERE updated_at IS NULL"
    )

    # ── 7. report_templates — last_run_at column from R8-CAST-1 ──
    op.execute(
        "ALTER TABLE report_templates ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMPTZ NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE report_templates DROP COLUMN IF EXISTS last_run_at")
    op.execute("ALTER TABLE dashboard_configs DROP COLUMN IF EXISTS updated_at")
    op.execute(
        "ALTER TABLE feature_usage DROP CONSTRAINT IF EXISTS fk_feature_usage_user_id"
    )
    for table in (
        "saved_views",
        "user_sessions",
        "feature_usage",
        "activity_logs",
        "revenue_signals",
        "stakeholders",
        "opportunity_signals",
        "tasks",
        "competitor_mentions",
    ):
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_tenant_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")
