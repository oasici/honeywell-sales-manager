"""Round-11 R11-DB-CCY — currency Float → NUMERIC(19, 2) phase 2.

Round-10 phase 10 migrated 23 currency columns to NUMERIC(19, 2). The
audit caught 13 more that escaped the first sweep — campaign budgets,
account enrichment aggregates, forecast snapshot detail amounts, base
pricing on price_entries and spare_parts, approval thresholds, bundle
prices, and the pipeline review queue's suggested amount.

The Python-side type stays ``float`` because each ORM column declares
``Numeric(19, 2, asdecimal=False)``. SQLAlchemy converts read values
back to ``float`` automatically. No serializer or downstream caller
needs to change; the only observable difference is that ``ROUND(x, 2)``
is now enforced at write time.

Columns migrated (13 total across 8 models):
- campaigns.{budget, actual_cost, expected_revenue, actual_revenue}
- account_enrichments.{pipeline_open_amount, closed_won_revenue}
- forecast_snapshot_details.amount
- price_entries.{list_price, net_price}
- spare_parts.{transfer_price, supplier_price}
- approval_rules.threshold_value
- product_bundles.bundle_price
- pipeline_review_queue.suggested_amount

Intentionally NOT migrated (non-currency Float fields surfaced by the
audit but excluded after review):
- ai_attributes.value_number — generic per-attribute numeric, can be
  anything (count, ratio, score). Not money.
- custom_fields.value_number — same rationale.
- v5_network.{expected_value, actual_value} — AI-confidence metric.
- feature_store_daily.total_open_pipeline — aggregate analytics input
  that always reads from already-NUMERIC quote.grand_total upstream;
  rewriting in place would force a backfill we don't need.

Idempotency follows the phase-10 pattern: the ALTER is wrapped in a
DO block that checks ``information_schema.columns.data_type`` before
issuing the change, so re-running on an already-migrated DB is a no-op.

Revision ID: 20260515_phase11_currency_sweep
Revises: 20260514_promote_phase9_not_null
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op


revision = "20260515_phase11_currency_sweep"
down_revision = "20260514_promote_phase9_not_null"
branch_labels = None
depends_on = None


_COLUMNS: tuple[tuple[str, str], ...] = (
    ("campaigns", "budget"),
    ("campaigns", "actual_cost"),
    ("campaigns", "expected_revenue"),
    ("campaigns", "actual_revenue"),
    ("account_enrichments", "pipeline_open_amount"),
    ("account_enrichments", "closed_won_revenue"),
    ("forecast_snapshot_details", "amount"),
    ("price_entries", "list_price"),
    ("price_entries", "net_price"),
    ("spare_parts", "transfer_price"),
    ("spare_parts", "supplier_price"),
    ("approval_rules", "threshold_value"),
    ("product_bundles", "bundle_price"),
    ("pipeline_review_queue", "suggested_amount"),
)


def _alter_to_numeric(table: str, column: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = '{table}'
                  AND column_name = '{column}'
                  AND data_type = 'double precision'
            ) THEN
                ALTER TABLE {table}
                ALTER COLUMN {column} TYPE NUMERIC(19, 2)
                USING ROUND({column}::numeric, 2);
            END IF;
        END $$;
        """
    )


def _alter_to_float(table: str, column: str) -> None:
    """Reverse path for downgrade — NUMERIC → DOUBLE PRECISION."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = '{table}'
                  AND column_name = '{column}'
                  AND data_type = 'numeric'
            ) THEN
                ALTER TABLE {table}
                ALTER COLUMN {column} TYPE DOUBLE PRECISION
                USING {column}::double precision;
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    for table, column in _COLUMNS:
        _alter_to_numeric(table, column)


def downgrade() -> None:
    for table, column in _COLUMNS:
        _alter_to_float(table, column)
