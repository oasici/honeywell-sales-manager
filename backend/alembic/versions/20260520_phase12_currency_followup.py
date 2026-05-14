"""Round-15 F-004 — promote feature_store_daily.total_open_pipeline to NUMERIC(19, 2).

Round-10 R10-DB-CCY moved every other currency column to NUMERIC(19, 2);
this one slipped past. Float drift produces rounding inconsistency in
the weekly pipeline rollup. Non-breaking conversion — Postgres
NUMERIC ↔ DOUBLE PRECISION is safe over the value range we use.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement (multi-statement strings raise PostgresSyntaxError). A
``DO $$ ... END $$`` PL/pgSQL block counts as a single statement,
which is what lets us guard the ALTER on the table's existence.

Why the existence guard: ``feature_store_daily`` is gated behind
``FEATURE_V4_FEATURE_STORE``. Deployments where the flag has never
been turned on don't have the table at all, and a bare ALTER raises
``UndefinedTableError`` and aborts the whole migration. The
information_schema check makes the migration idempotent across
deployment topologies. (Render Free-tier deploys hit this on the
first attempt — fix authored from the live log signature.)

Revision ID: 20260520_r15_ccy_followup
Revises: 20260518_phase12_tenant_columns
Create Date: 2026-05-13

Note on the revision id length: revision strings are persisted into
``alembic_version.version_num``, which on legacy Postgres bootstraps
is VARCHAR(32). The previous full-length id
("20260520_phase12_currency_followup", 34 chars) exceeded the column
on environments where the env.py widener hadn't (yet) widened
``version_num`` to VARCHAR(128). Shortened to fit in 32 chars so the
INSERT succeeds regardless of the widener state. Filename retained
in full for human readability.
"""

from __future__ import annotations

from alembic import op


revision = "20260520_r15_ccy_followup"
down_revision = "20260518_phase12_tenant_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'feature_store_daily'
            ) THEN
                ALTER TABLE feature_store_daily
                    ALTER COLUMN total_open_pipeline TYPE NUMERIC(19, 2)
                    USING total_open_pipeline::NUMERIC(19, 2);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'feature_store_daily'
            ) THEN
                ALTER TABLE feature_store_daily
                    ALTER COLUMN total_open_pipeline TYPE DOUBLE PRECISION;
            END IF;
        END $$;
        """
    )
