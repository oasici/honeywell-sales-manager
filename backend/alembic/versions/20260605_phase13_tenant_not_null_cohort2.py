"""Round-15 F-001 / Sprint 15l cohort 2 — promote tenant_id to NOT NULL on billing + campaign tables.

Continues the cohort-1 promotion (customers / opportunities / quotes /
leads → NOT NULL). Cohort 2 closes the next tier:

  * ``contracts``
  * ``invoices``
  * ``campaigns``
  * ``subscriptions``

All four hang off ``customers`` (and ``users``); cohort 1 already
locked ``customers.tenant_id`` to NOT NULL so the backfill chain is
clean by construction. Same three-step pattern as cohort 1:

  1. **Defensive backfill** — primary source is the per-table FK to
     ``customers`` (where present) or to ``users``. Campaigns lacks a
     customer FK, so creator's tenant is the only source.
  2. **Single-tenant fallback** — fills any residual NULL when
     exactly one tenant exists in the deployment.
  3. **Abort-on-residual-NULL guard** + ``ALTER COLUMN ... SET NOT
     NULL``.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement.

Revision ID: 20260605_phase13_tenant_not_null_cohort2
Revises: 20260604_phase13_tenant_not_null_cohort1
Create Date: 2026-05-18
"""

from __future__ import annotations

from alembic import op


revision = "20260605_phase13_tenant_not_null_cohort2"
down_revision = "20260604_phase13_tenant_not_null_cohort1"
branch_labels = None
depends_on = None


_BACKFILLS: dict[str, list[str]] = {
    "contracts": [
        # Primary: parent customer (customer_id is NOT NULL on contract).
        """
        UPDATE contracts c
        SET tenant_id = cu.tenant_id
        FROM customers cu
        WHERE c.tenant_id IS NULL
          AND c.customer_id = cu.id
          AND cu.tenant_id IS NOT NULL
        """,
        # Fallback: creator's user.tenant_id (created_by is NOT NULL).
        """
        UPDATE contracts c
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE c.tenant_id IS NULL
          AND c.created_by = u.id
          AND u.tenant_id IS NOT NULL
        """,
    ],
    "invoices": [
        """
        UPDATE invoices i
        SET tenant_id = cu.tenant_id
        FROM customers cu
        WHERE i.tenant_id IS NULL
          AND i.customer_id = cu.id
          AND cu.tenant_id IS NOT NULL
        """,
        """
        UPDATE invoices i
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE i.tenant_id IS NULL
          AND i.created_by = u.id
          AND u.tenant_id IS NOT NULL
        """,
    ],
    "campaigns": [
        # Campaigns have no customer FK; the only edge is the creator.
        """
        UPDATE campaigns c
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE c.tenant_id IS NULL
          AND c.created_by = u.id
          AND u.tenant_id IS NOT NULL
        """,
    ],
    "subscriptions": [
        """
        UPDATE subscriptions s
        SET tenant_id = cu.tenant_id
        FROM customers cu
        WHERE s.tenant_id IS NULL
          AND s.customer_id = cu.id
          AND cu.tenant_id IS NOT NULL
        """,
        """
        UPDATE subscriptions s
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE s.tenant_id IS NULL
          AND s.created_by = u.id
          AND u.tenant_id IS NOT NULL
        """,
    ],
}


_TABLES: tuple[str, ...] = ("contracts", "invoices", "campaigns", "subscriptions")


def upgrade() -> None:
    # Step 1 — FK-chain backfill.
    for _table, statements in _BACKFILLS.items():
        for stmt in statements:
            op.execute(stmt)

    # Step 2 — single-tenant fallback.
    for table in _TABLES:
        op.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (SELECT id FROM tenants ORDER BY id LIMIT 1)
            WHERE tenant_id IS NULL
              AND (SELECT COUNT(*) FROM tenants) = 1
            """
        )

    # Step 3 — guard.
    for table in _TABLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF (SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL) > 0 THEN
                RAISE EXCEPTION
                  'Sprint 15l cohort 2: cannot promote {table}.tenant_id to NOT NULL — orphan rows remain. See docs/runbooks/r15k-tenant-orphan-backfill.md.';
              END IF;
            END $$
            """
        )

    # Step 4 — promote.
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id DROP NOT NULL")
