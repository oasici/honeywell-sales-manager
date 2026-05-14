"""Round-15 F-002 / Sprint 15j cohort 11 — defense-in-depth tenant_id on user-derived rows.

Continues the cohort 1-10 pattern. This revision covers three tables
that are strictly user-owned (one row per user, FK to ``users.id``):

  * ``api_keys`` — public API keys minted per user.
  * ``achievements`` — gamification badges earned per user.
  * ``push_subscriptions`` — Web Push registrations per user / device.

All three backfill ``tenant_id`` from ``users.tenant_id`` via
``user_id``. Nullable on disk per the cohort convention.

Skipped on purpose:
  * ``custom_fields`` — ``created_by`` is nullable, so the user-derived
    backfill leaves seeded rows orphaned; needs a separate strategy
    that infers tenancy from any value row's entity.
  * ``lead_assignment_rules`` — ``assign_to_user_id`` is nullable for
    round-robin rules; same orphan problem. A future cohort will
    derive tenancy from the rules' creator audit row instead.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement.

Revision ID: 20260601_phase12_tenant_did_cohort11
Revises: 20260531_phase12_tenant_did_cohort10
Create Date: 2026-05-14
"""

from __future__ import annotations

from alembic import op


revision = "20260601_phase12_tenant_did_cohort11"
down_revision = "20260531_phase12_tenant_did_cohort10"
branch_labels = None
depends_on = None


# (child_table, parent_table, fk_column_on_child)
_TABLES: list[tuple[str, str, str]] = [
    ("api_keys", "users", "user_id"),
    ("achievements", "users", "user_id"),
    ("push_subscriptions", "users", "user_id"),
]


def upgrade() -> None:
    for table, parent, fk_col in _TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
        )
        op.execute(
            f"""
            UPDATE {table} c
            SET tenant_id = p.tenant_id
            FROM {parent} p
            WHERE c.tenant_id IS NULL
              AND c.{fk_col} = p.id
              AND p.tenant_id IS NOT NULL
            """
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id "
            f"ON {table} (tenant_id)"
        )


def downgrade() -> None:
    for table, _parent, _fk in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_tenant_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")
