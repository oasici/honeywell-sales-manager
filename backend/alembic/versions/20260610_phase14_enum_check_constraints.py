"""Round-15 audit F-018 — add DB-level CHECK constraints for String(20) enum columns.

Pre-fix these columns relied on Pydantic validation (and only at API
boundaries — direct service-layer writes had no guard). A buggy
service that wrote ``role='admin_typo'`` to the DB would silently
succeed and then fail at the next role-check.

Adding CHECK constraints makes the database the final guard. CI's
schema-drift gate won't see drift because constraints are part of
the alembic chain.

The constraints are idempotent (``IF NOT EXISTS``-equivalent via
PG's ``DO $$ ... WHERE NOT EXISTS`` pattern). Asyncpg restriction:
one statement per ``op.execute()``.

Revision ID: 20260610_phase14_enum_check_constraints
Revises: 20260609_phase13_tenant_not_null_cohort6
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op


revision = "20260610_phase14_enum_check_constraints"
down_revision = "20260609_phase13_tenant_not_null_cohort6"
branch_labels = None
depends_on = None


# (table, constraint_name, expression)
_CHECKS: tuple[tuple[str, str, str], ...] = (
    (
        "users",
        "ck_users_role",
        "role IN ('sales_rep','sales_manager','operations','admin')",
    ),
    (
        "competitor_mentions",
        "ck_competitor_mentions_sentiment",
        "sentiment IS NULL OR sentiment IN ('positive','neutral','negative')",
    ),
    (
        "competitor_mentions",
        "ck_competitor_mentions_detected_by",
        "detected_by IN ('keyword','ai','manual')",
    ),
    (
        "meeting_bookings",
        "ck_meeting_bookings_status",
        "status IN ('confirmed','cancelled','rescheduled','completed','no_show')",
    ),
    (
        "playbook_executions",
        "ck_playbook_executions_status",
        "status IN ('pending','running','completed','failed','cancelled')",
    ),
    (
        "revenue_schedules",
        "ck_revenue_schedules_recognition_type",
        "recognition_type IN ('immediate','straight_line','milestone','usage')",
    ),
    (
        "revenue_schedule_entries",
        "ck_revenue_schedule_entries_status",
        "status IN ('pending','recognized','reversed')",
    ),
)


def _add_check_idempotent(table: str, constraint: str, expression: str) -> str:
    """Return a single PG statement that adds a CHECK if it doesn't exist."""
    return f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            WHERE t.relname = '{table}'
              AND c.conname = '{constraint}'
          ) THEN
            ALTER TABLE {table}
              ADD CONSTRAINT {constraint}
              CHECK ({expression});
          END IF;
        END
        $$
    """


def upgrade() -> None:
    for table, constraint, expression in _CHECKS:
        op.execute(_add_check_idempotent(table, constraint, expression))


def downgrade() -> None:
    for table, constraint, _ in _CHECKS:
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}"
        )
