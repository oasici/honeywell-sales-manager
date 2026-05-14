"""Round-15 F-004 — promote feature_store_daily.total_open_pipeline to NUMERIC(19, 2).

Round-10 R10-DB-CCY moved every other currency column to NUMERIC(19, 2);
this one slipped past. Float drift produces rounding inconsistency in
the weekly pipeline rollup. Non-breaking conversion — Postgres
NUMERIC ↔ DOUBLE PRECISION is safe over the value range we use.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement (multi-statement strings raise PostgresSyntaxError).

Revision ID: 20260520_phase12_currency_followup
Revises: 20260518_phase12_tenant_columns
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op


revision = "20260520_phase12_currency_followup"
down_revision = "20260518_phase12_tenant_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE feature_store_daily "
        "ALTER COLUMN total_open_pipeline TYPE NUMERIC(19, 2) "
        "USING total_open_pipeline::NUMERIC(19, 2)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE feature_store_daily "
        "ALTER COLUMN total_open_pipeline TYPE DOUBLE PRECISION"
    )
