"""Round-6 R6-API-1 — add tenant_id to campaigns and campaign_members.

Pre-R6:
- ``Campaign`` had no tenant_id, so any authenticated manager in
  tenant A could list every campaign in the database via
  ``GET /campaigns/`` (no ``scoped_for_user``) and read individual
  campaigns via ``GET /campaigns/{id}`` (no ``assert_same_tenant``).
- ``CampaignMember`` had the same shape, so member rosters
  (lead_id / customer_id pairs) were cross-tenant readable too.

Backfill:
- campaigns.tenant_id ← users.tenant_id of created_by.
- campaign_members.tenant_id ← campaigns.tenant_id of campaign_id
  (so child rows mirror their parent).

Rows whose creator has a NULL tenant (single-tenant deployments) stay
NULL; downstream scoped_for_user is a no-op when both sides are None.

Revision ID: 20260506_campaign_tenant
Revises: 20260505_drop_dup_indexes
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op


revision = "20260506_campaign_tenant"
down_revision = "20260505_drop_dup_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS tenant_id INTEGER")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_campaign_tenant ON campaigns (tenant_id)"
    )
    op.execute(
        """
        UPDATE campaigns c
        SET tenant_id = (SELECT u.tenant_id FROM users u WHERE u.id = c.created_by)
        WHERE tenant_id IS NULL AND created_by IS NOT NULL
        """
    )

    op.execute(
        "ALTER TABLE campaign_members ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_campaign_member_tenant "
        "ON campaign_members (tenant_id)"
    )
    op.execute(
        """
        UPDATE campaign_members m
        SET tenant_id = (SELECT c.tenant_id FROM campaigns c WHERE c.id = m.campaign_id)
        WHERE m.tenant_id IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_campaign_member_tenant")
    op.execute("ALTER TABLE campaign_members DROP COLUMN IF EXISTS tenant_id")

    op.execute("DROP INDEX IF EXISTS ix_campaign_tenant")
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS tenant_id")
