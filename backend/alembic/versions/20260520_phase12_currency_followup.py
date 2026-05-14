"""Round-15 F-004 — promote account_features_daily.total_open_pipeline to NUMERIC(19, 2).

Round-10 R10-DB-CCY moved every other currency column to NUMERIC(19, 2);
this one slipped past. Float drift produces rounding inconsistency in
the weekly pipeline rollup. Non-breaking conversion — Postgres
NUMERIC ↔ DOUBLE PRECISION is safe over the value range we use.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement (multi-statement strings raise PostgresSyntaxError). A
``DO $$ ... END $$`` PL/pgSQL block counts as a single statement,
which is what lets us guard the ALTER on the table's existence.

Why the existence guard: ``account_features_daily`` ships in the
bootstrap migration but its V4 feature-store cousins
(``opportunity_features_daily``, ``rep_features_daily``) are gated
behind ``FEATURE_V4_FEATURE_STORE``. Render Free-tier deploys hit
``UndefinedTableError`` on the first attempt; the information_schema
check makes this migration idempotent across deployment topologies.

History notes.

  * f3dc3b2 briefly renamed this revision to
    ``20260520_r15_ccy_followup`` (25 chars) under the impression that
    the deploy was failing on the legacy VARCHAR(32) column. The
    rename was wrong — the env.py widener (R11) had already widened
    ``alembic_version.version_num`` to VARCHAR(128) on Render, and
    the long name had successfully landed in the prod table. Reverted
    in e45ad3b.

  * The previous version of this migration referenced the wrong
    table name — it guarded on / altered ``feature_store_daily``
    (the *Python module* file name in ``app/models/feature_store_daily.py``),
    but the actual ORM ``__tablename__`` is ``account_features_daily``.
    The information_schema guard silently no-op'd on every deploy
    because the wrong-named table never existed, and the schema-drift
    CI gate kept failing with
    ``account_features_daily.total_open_pipeline model=NUMERIC db=FLOAT``.
    Corrected here.
"""

from __future__ import annotations

from alembic import op


revision = "20260520_phase12_currency_followup"
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
                  AND table_name = 'account_features_daily'
            ) THEN
                ALTER TABLE account_features_daily
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
                  AND table_name = 'account_features_daily'
            ) THEN
                ALTER TABLE account_features_daily
                    ALTER COLUMN total_open_pipeline TYPE DOUBLE PRECISION;
            END IF;
        END $$;
        """
    )
