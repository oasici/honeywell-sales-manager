"""Round-6 R6-DB-1 — drop redundant indexes on UNIQUE columns.

Pre-R6:
- ``users.email`` had ``unique=True`` AND ``index=True`` → two indexes
  covering the same column.
- Same shape on ``customers.email``, ``user_sessions.jti``, and
  ``signature_requests.token`` (the last via an explicit
  ``Index("ix_sig_token", "token", unique=True)`` plus column-level
  ``unique=True``).

Effect of the duplication: storage waste + double write cost on every
INSERT/UPDATE on auth-critical tables. Same anti-pattern Round-5
R5-DB-2/3 closed for ``tenant_id``; this family was missed.

The auto-created ``*_key`` constraint indexes (e.g. ``users_email_key``)
stay in place — UNIQUE constraints in PostgreSQL always carry an index.

Revision ID: 20260506_drop_dup_unique_indexes
Revises: 20260506_campaign_tenant
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op


revision = "20260506_drop_dup_unique_indexes"
down_revision = "20260506_campaign_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_email")
    op.execute("DROP INDEX IF EXISTS ix_customers_email")
    op.execute("DROP INDEX IF EXISTS ix_user_sessions_jti")
    op.execute("DROP INDEX IF EXISTS ix_sig_token")


def downgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customers_email ON customers (email)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_sessions_jti ON user_sessions (jti)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_sig_token "
        "ON signature_requests (token)"
    )
