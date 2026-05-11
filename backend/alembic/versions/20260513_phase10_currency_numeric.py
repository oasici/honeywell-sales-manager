"""Round-10 R10-DB-CCY — currency columns Float → NUMERIC(19, 2).

Migrates every column that stores a currency amount from the binary
IEEE-754 ``FLOAT`` representation to PostgreSQL ``NUMERIC(19, 2)``
(decimal, 19 digits total, 2 after the decimal point). ``Numeric`` is
SQL's canonical type for monetary values; it preserves exact decimal
arithmetic and prevents the accumulating-rounding-error class of bug
that affects float-based revenue reconciliation.

The Python-side type stays ``float`` because the ORM declares
``Numeric(19, 2, asdecimal=False)`` — SQLAlchemy converts read values
back to ``float`` automatically. No serializer or downstream caller
needs to change; the only observable difference is that
``ROUND(x, 2)`` is now enforced at write time.

Columns migrated (24 total across 9 models):
- quotes.{subtotal, discount_total, tax_amount, grand_total}
- quote_items.{unit_price, line_total}
- invoices.{subtotal, tax_amount, grand_total}
- opportunities.{amount, previous_amount}
- contracts.value
- revenue_schedules.{total_amount, recognized_amount}
- revenue_schedule_entries.{amount, recognized_amount}
- forecast_adjustments.{original_amount, adjusted_amount}
- pipeline_snapshots.{total_amount, weighted_amount}
- subscriptions.mrr
- price_tiers.unit_price
- customer_pricing.contracted_price

Columns intentionally left as Float (percentages, not currency):
- quotes.tax_rate, invoices.tax_rate (percentage)
- quote_items.discount_pct (percentage)
- price_tiers.discount_pct, customer_pricing.discount_pct (percentage)

Conversion strategy: ``ALTER COLUMN ... TYPE NUMERIC(19, 2) USING
ROUND(<col>::numeric, 2)``. Postgres copies the data column-by-column
and rounds each value to the new precision. For our currency columns
(2 decimals max in practice) this is lossless; any float wobble in
the 3rd+ decimal is the rounding error we are trying to eliminate.

Idempotency: the ALTER is wrapped in a DO block that checks
``information_schema.columns.data_type`` before issuing the change,
so re-running on an already-migrated DB is a no-op.

Revision ID: 20260513_phase10_currency_numeric
Revises: 20260512_phase9_tenant_sweep
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op


revision = "20260513_phase10_currency_numeric"
down_revision = "20260512_phase9_tenant_sweep"
branch_labels = None
depends_on = None


_COLUMNS: tuple[tuple[str, str], ...] = (
    ("quotes", "subtotal"),
    ("quotes", "discount_total"),
    ("quotes", "tax_amount"),
    ("quotes", "grand_total"),
    ("quote_items", "unit_price"),
    ("quote_items", "line_total"),
    ("invoices", "subtotal"),
    ("invoices", "tax_amount"),
    ("invoices", "grand_total"),
    ("opportunities", "amount"),
    ("opportunities", "previous_amount"),
    ("contracts", "value"),
    ("revenue_schedules", "total_amount"),
    ("revenue_schedules", "recognized_amount"),
    ("revenue_schedule_entries", "amount"),
    ("revenue_schedule_entries", "recognized_amount"),
    ("forecast_adjustments", "original_amount"),
    ("forecast_adjustments", "adjusted_amount"),
    ("pipeline_snapshots", "total_amount"),
    ("pipeline_snapshots", "weighted_amount"),
    ("subscriptions", "mrr"),
    ("price_tiers", "unit_price"),
    ("customer_pricing", "contracted_price"),
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
