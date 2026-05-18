"""Round-15 F-001 / Sprint 15k — gate against tenant_id NOT NULL regression.

The deep audit found that only 6 of 124 tables enforce ``tenant_id NOT
NULL``. Promotion is a multi-cohort campaign (see audit's Sprint 15k/l).
This test pins the current allowlist so a future refactor that
*relaxes* an already-promoted table back to nullable fails CI before
merge.

When you promote a new table to NOT NULL via a follow-up migration:

  1. Add the table name to ``NOT_NULL_TENANT_ALLOWLIST`` below.
  2. Run the existing orphan-row backfill (see
     ``docs/runbooks/r13-orphan-tenant-backfill.md`` for the template).
  3. Ship the ``ALTER COLUMN tenant_id SET NOT NULL`` migration.

The test asserts the *minimum* — adding more tables passes; removing
or relaxing trips the assert.
"""

from __future__ import annotations

import os


# Tables that currently declare ``tenant_id`` as NOT NULL in
# ``Base.metadata``. Surveyed by the Round-15 deep audit.
NOT_NULL_TENANT_ALLOWLIST: set[str] = {
    "contacts",
    "meeting_bookings",
    "notifications",
    "playbook_executions",
    "playbooks",
    "selling_guides",
    # Round-15 Sprint 15k cohort 1 — top-tier CRM tables. Promoted by
    # migration ``20260604_phase13_tenant_not_null_cohort1.py`` once
    # the test-fixture sweep (batches 1-8) closed the blocking gap.
    "customers",
    "opportunities",
    "quotes",
    "leads",
}


def test_tenant_id_not_null_floor_holds() -> None:
    """All allowlisted tables must keep their NOT NULL constraint.

    Regressions (a model edit that re-introduces nullability before
    backfill, an Alembic merge that re-applies the column with
    ``nullable=True``, etc.) trip this assert.
    """
    os.environ.setdefault("TEST_DATABASE_URL", "sqlite+aiosqlite:///./test.db")

    from app import models  # noqa: F401 — register all mappers
    from app.core.database import Base

    declared_not_null: set[str] = set()
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if column.name == "tenant_id" and not column.nullable:
                declared_not_null.add(table.name)

    missing = NOT_NULL_TENANT_ALLOWLIST - declared_not_null
    assert not missing, (
        "tenant_id NOT NULL regressed on: "
        f"{sorted(missing)}. Either re-promote the column or, "
        "if this is intentional, remove it from "
        "NOT_NULL_TENANT_ALLOWLIST in this test."
    )


def test_tenant_id_not_null_count_does_not_decrease() -> None:
    """Defense-in-depth — the total NOT-NULL tenant_id count must
    monotonically grow as cohorts promote.

    Today's floor is the size of ``NOT_NULL_TENANT_ALLOWLIST``. The
    Round-15 audit's Sprint 15k/l promotes this number; if a PR
    accidentally relaxes more than it adds, the assert trips.
    """
    os.environ.setdefault("TEST_DATABASE_URL", "sqlite+aiosqlite:///./test.db")

    from app import models  # noqa: F401
    from app.core.database import Base

    actual_not_null = 0
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if column.name == "tenant_id" and not column.nullable:
                actual_not_null += 1

    assert actual_not_null >= len(NOT_NULL_TENANT_ALLOWLIST), (
        f"NOT-NULL tenant_id count dropped to {actual_not_null}; "
        f"allowlist floor is {len(NOT_NULL_TENANT_ALLOWLIST)}."
    )
