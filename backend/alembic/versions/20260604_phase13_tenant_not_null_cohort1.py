"""Round-15 F-001 / Sprint 15k cohort 1 — promote tenant_id to NOT NULL on top-tier CRM tables.

Re-introduces the migration that was parked in
``docs/audits/2026-05-15-15kl-parking-notes.md``. The blocker (test
fixtures creating CRM rows without ``tenant_id``) is now resolved
across batches 1-8 of the test-fixture sweep (47 of 49 test files
migrated; the legacy-NULL test was removed since the codepath becomes
unreachable here).

Audit F-001 found 58 of 124 tables declare ``tenant_id`` NULLABLE.
This cohort locks the four top-tier CRM tables:

  * ``customers``
  * ``opportunities``
  * ``quotes``
  * ``leads``

All four are root entities — every other CRM row hangs off these via
FK chains that prior cohorts (15j 1-13) traced and backfilled.
Promoting them to ``NOT NULL`` is the strongest defense-in-depth
lever: any orphan that survives the backfill becomes detectable at
INSERT time rather than silently invisible to every tenant.

Safety contract (each step is a single ``op.execute()`` per asyncpg).

  1. **Defensive backfill** — for each table, fill any remaining NULL
     ``tenant_id`` from the most reliable source available:
       - ``customers`` → ``users.tenant_id`` via ``created_by``.
       - ``opportunities`` → ``customers.tenant_id`` via
         ``customer_id`` (primary), with fallback to
         ``users.tenant_id`` via ``owner_id`` (``owner_id`` is NOT
         NULL on the row).
       - ``quotes`` → ``opportunities.tenant_id`` via the (optional)
         ``opportunity_id``, fallback to ``customers`` via
         ``customer_id``, final fallback to ``users.tenant_id`` via
         ``created_by``.
       - ``leads`` → ``users.tenant_id`` via ``owner_id`` (NOT NULL
         on the row).

  2. **Single-tenant fallback** — if exactly one tenant exists in the
     deployment, fill any residual NULL with that tenant's id. Multi-
     tenant deployments skip this branch (the guard below will fire).

  3. **Abort-on-residual-NULL guard** — a ``DO $$ ... $$`` block per
     table that raises an exception if any row still has NULL
     ``tenant_id``. The migration fails fast rather than promote a
     column with orphans.

  4. **Promote to NOT NULL** — ``ALTER TABLE ... ALTER COLUMN
     tenant_id SET NOT NULL``.

Idempotency: re-running upgrade is safe — the backfill ``WHERE
tenant_id IS NULL`` clause is empty on a clean DB; the guard succeeds
(zero rows); ``SET NOT NULL`` is a no-op when the column is already
NOT NULL on PostgreSQL.

Downgrade reverses to NULLABLE in declaration order; backfilled rows
keep their tenant_id.

Revision ID: 20260604_phase13_tenant_not_null_cohort1
Revises: 20260603_phase12_tenant_did_cohort13
Create Date: 2026-05-15
"""

from __future__ import annotations

from alembic import op


revision = "20260604_phase13_tenant_not_null_cohort1"
down_revision = "20260603_phase12_tenant_did_cohort13"
branch_labels = None
depends_on = None


# Per-table backfill strategy: list of ``UPDATE`` statements run in
# order. First statement is the primary source; subsequent ones are
# fallbacks for rows the primary couldn't fill.
_BACKFILLS: dict[str, list[str]] = {
    "customers": [
        """
        UPDATE customers c
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE c.tenant_id IS NULL
          AND c.created_by = u.id
          AND u.tenant_id IS NOT NULL
        """,
    ],
    "opportunities": [
        # Primary: parent customer.tenant_id.
        """
        UPDATE opportunities o
        SET tenant_id = c.tenant_id
        FROM customers c
        WHERE o.tenant_id IS NULL
          AND o.customer_id = c.id
          AND c.tenant_id IS NOT NULL
        """,
        # Fallback: owner.tenant_id (owner_id is NOT NULL).
        """
        UPDATE opportunities o
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE o.tenant_id IS NULL
          AND o.owner_id = u.id
          AND u.tenant_id IS NOT NULL
        """,
    ],
    "quotes": [
        # Primary: linked opportunity.
        """
        UPDATE quotes q
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE q.tenant_id IS NULL
          AND q.opportunity_id = o.id
          AND o.tenant_id IS NOT NULL
        """,
        # Fallback 1: customer of the quote.
        """
        UPDATE quotes q
        SET tenant_id = c.tenant_id
        FROM customers c
        WHERE q.tenant_id IS NULL
          AND q.customer_id = c.id
          AND c.tenant_id IS NOT NULL
        """,
        # Fallback 2: creator's tenant.
        """
        UPDATE quotes q
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE q.tenant_id IS NULL
          AND q.created_by = u.id
          AND u.tenant_id IS NOT NULL
        """,
    ],
    "leads": [
        # Primary: lead owner (NOT NULL).
        """
        UPDATE leads l
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE l.tenant_id IS NULL
          AND l.owner_id = u.id
          AND u.tenant_id IS NOT NULL
        """,
    ],
}


_TABLES: tuple[str, ...] = ("customers", "opportunities", "quotes", "leads")


def upgrade() -> None:
    # Step 1 — FK-chain backfill.
    for _table, statements in _BACKFILLS.items():
        for stmt in statements:
            op.execute(stmt)

    # Step 2 — single-tenant fallback. If exactly one tenant exists,
    # use it as the safe-default for any remaining NULLs.
    for table in _TABLES:
        op.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (SELECT id FROM tenants ORDER BY id LIMIT 1)
            WHERE tenant_id IS NULL
              AND (SELECT COUNT(*) FROM tenants) = 1
            """
        )

    # Step 3 — abort if any row still has NULL. See
    # ``docs/runbooks/r15k-tenant-orphan-backfill.md`` for the triage
    # path.
    for table in _TABLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF (SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL) > 0 THEN
                RAISE EXCEPTION
                  'Sprint 15k cohort 1: cannot promote {table}.tenant_id to NOT NULL — orphan rows remain. Run the backfill runbook before retrying.';
              END IF;
            END $$
            """
        )

    # Step 4 — promote to NOT NULL.
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id DROP NOT NULL")
