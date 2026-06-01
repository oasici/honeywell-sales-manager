"""Round-19 Phase 12 — per-tenant forecast cron timezone (D-034).

The forecast pipeline snapshot ran on a single weekly UTC interval, so
a tenant in Europe/Istanbul got its baseline captured mid-afternoon
local time rather than at a consistent start-of-business-day boundary.
This adds two tenant-settings knobs so each tenant chooses *when* (and
in which timezone) its snapshot is taken, and a tenant_id column on
pipeline_snapshots so per-tenant snapshots are distinguishable from the
legacy global rows.

  tenant_settings.forecast_cron_hour  INTEGER     NOT NULL DEFAULT 4
  tenant_settings.forecast_cron_tz    VARCHAR(40) NOT NULL DEFAULT 'UTC'
  pipeline_snapshots.tenant_id        INTEGER     NULL (indexed)

Idempotent. Legacy global snapshots keep tenant_id = NULL; the
on-demand /forecast/snapshot endpoint still writes global rows.

Revision ID: 20260704_phase12_forecast_tz
Revises: 20260703_phase12_occ_complete
"""

from __future__ import annotations

from alembic import op


revision = "20260704_phase12_forecast_tz"
down_revision = "20260703_phase12_occ_complete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'tenant_settings') THEN
            ALTER TABLE tenant_settings
              ADD COLUMN IF NOT EXISTS forecast_cron_hour INTEGER NOT NULL DEFAULT 4;
            ALTER TABLE tenant_settings
              ADD COLUMN IF NOT EXISTS forecast_cron_tz VARCHAR(40) NOT NULL DEFAULT 'UTC';
          END IF;
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'pipeline_snapshots') THEN
            ALTER TABLE pipeline_snapshots
              ADD COLUMN IF NOT EXISTS tenant_id INTEGER;
            CREATE INDEX IF NOT EXISTS ix_pipeline_snapshot_tenant
              ON pipeline_snapshots (tenant_id);
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'pipeline_snapshots') THEN
            DROP INDEX IF EXISTS ix_pipeline_snapshot_tenant;
            ALTER TABLE pipeline_snapshots DROP COLUMN IF EXISTS tenant_id;
          END IF;
          IF EXISTS (SELECT 1 FROM information_schema.tables
                     WHERE table_name = 'tenant_settings') THEN
            ALTER TABLE tenant_settings DROP COLUMN IF EXISTS forecast_cron_tz;
            ALTER TABLE tenant_settings DROP COLUMN IF EXISTS forecast_cron_hour;
          END IF;
        END $$;
        """
    )
