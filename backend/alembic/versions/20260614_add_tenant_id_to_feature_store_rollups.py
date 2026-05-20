"""Round-16 E (M-02) — add tenant_id to feature-store rollup tables.

Closes audit N15-DB-3 (``docs/audits/2026-05-20-cross-layer-audit-round15.md``
§3.3). ``account_features_daily`` and ``rep_features_daily`` were the
only feature-store rollups missing a ``tenant_id`` column — sibling
``opportunity_features_daily`` got one in cohort 5
(``20260526_phase12_tenant_did_cohort5``). The gap meant any future
``scoped_for_user`` query touching these rollups would silently skip
the filter and cross-pollinate aggregates between tenants.

Engineering decision (Sprint 16e, no PM/data-science blocker found):
add ``tenant_id`` to both tables and backfill from the FK chain:

  - account_features_daily.tenant_id ← customers.tenant_id via account_id
  - rep_features_daily.tenant_id      ← users.tenant_id via rep_id

Defense-in-depth pattern — column is nullable for now so the migration
is non-blocking on legacy rows. Promotion to NOT NULL is deferred to
a follow-up cohort once the backfill is verified clean in prod.

Revision ID: 20260614_add_tenant_id_to_feature_store_rollups
Revises: 20260613_phase13_tenant_not_null_cohort9
Create Date: 2026-05-21
"""

from __future__ import annotations

from alembic import op


revision = "20260614_add_tenant_id_to_feature_store_rollups"
down_revision = "20260613_phase13_tenant_not_null_cohort9"
branch_labels = None
depends_on = None


_PLAN: tuple[tuple[str, str, str, str], ...] = (
    # (child_table, parent_table, child_fk_col, parent_pk_col)
    ("account_features_daily", "customers", "account_id", "id"),
    ("rep_features_daily", "users", "rep_id", "id"),
)


def upgrade() -> None:
    # 1. Add the column. Nullable for backwards-compat; ``IF NOT EXISTS``
    # so a re-run is idempotent.
    for table, _parent, _fk, _pk in _PLAN:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant ON {table} (tenant_id)"
        )

    # 2. Backfill from the parent's tenant_id via the existing FK chain.
    for child, parent, fk_col, pk_col in _PLAN:
        op.execute(
            f"""
            UPDATE {child} c
            SET tenant_id = p.tenant_id
            FROM {parent} p
            WHERE c.tenant_id IS NULL
              AND c.{fk_col} = p.{pk_col}
              AND p.tenant_id IS NOT NULL
            """
        )

    # 3. Single-tenant fallback (dev / single-tenant installs only).
    for child, _parent, _fk, _pk in _PLAN:
        op.execute(
            f"""
            UPDATE {child}
            SET tenant_id = (SELECT id FROM tenants ORDER BY id LIMIT 1)
            WHERE tenant_id IS NULL
              AND (SELECT COUNT(*) FROM tenants) = 1
            """
        )

    # Note: NOT NULL promotion is intentionally deferred. The audit's
    # M-02 plan flagged that as a follow-up cohort once the backfill
    # is verified clean in prod — the orphan-check pattern from
    # cohort-9 runs at promotion time.


def downgrade() -> None:
    for table, _parent, _fk, _pk in _PLAN:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_tenant")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")
