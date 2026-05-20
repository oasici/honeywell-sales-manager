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
    # Round-15 Sprint 15l cohort 2 — billing + campaigns surface.
    # Promoted by migration
    # ``20260605_phase13_tenant_not_null_cohort2.py``. All four hang
    # off customers (which became NOT NULL in cohort 1), so the
    # backfill chain is clean by construction.
    "contracts",
    "invoices",
    "campaigns",
    "subscriptions",
    # Round-15 Sprint 15m cohort 3 — opportunity-derived tables.
    # Promoted by migration
    # ``20260606_phase13_tenant_not_null_cohort3.py``. All four hang
    # off opportunities (NOT NULL post-cohort-1) via NOT NULL FK.
    "opportunity_events",
    "opportunity_signals",
    "decision_gaps",
    "forecast_adjustments",
    # Round-15 Sprint 15n cohort 4 — engagement add-ons with clean
    # parent FK chains (users / customers / opportunities — all
    # NOT NULL on tenant_id by this point). Promoted by migration
    # ``20260607_phase13_tenant_not_null_cohort4.py``.
    "comments",
    "shared_documents",
    "meeting_links",
    "webhook_subscriptions",
    "account_enrichments",
    "v4_deal_replay_snapshots",
    # Round-15 Sprint 15o cohort 5 — second-tier user/customer/opp/contract
    # derivatives. Promoted by migration
    # ``20260608_phase13_tenant_not_null_cohort5.py``.
    "coaching_plans",
    "achievements",
    "territories",
    "report_folders",
    "user_customer_pins",
    "account_teams",
    "forecast_snapshot_details",
    "deal_replay_deltas",
    "opportunity_embeddings",
    "action_experiments",
    "revenue_schedules",
    # Round-15 Sprint 15p cohort 6 — objections (opp-derived) and
    # workflow_rules (user-derived). Promoted by migration
    # ``20260609_phase13_tenant_not_null_cohort6.py``.
    "objections",
    "workflow_rules",
    # Round-15 Sprint 15q cohort 7 — api_keys (user-derived) +
    # deal_similarity_links (opp-derived). Promoted by migration
    # ``20260611_phase13_tenant_not_null_cohort7.py``.
    "api_keys",
    "deal_similarity_links",
    # Round-15 Sprint 15r cohort 8 — 3 more opp-derived tables.
    # Promoted by migration
    # ``20260612_phase13_tenant_not_null_cohort8.py``.
    "opportunity_text_embeddings",
    "opportunity_transformer_seq_embeddings",
    "recommended_action_windows",
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
