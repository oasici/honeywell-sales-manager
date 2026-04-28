"""V9 CRM sync platform

Revision ID: 20260428_v9_crm_sync
Revises: 20260427_v8_crm_tenant_id
Create Date: 2026-04-28

Bidirectional CRM sync (Salesforce / HubSpot / Dynamics) — V2 Epic C2
that was deferred. Tables are additive; runtime only activates when
``FEATURE_V9_CRM_SYNC`` is on AND a connection row exists for the
tenant.

Idempotent.
"""

from alembic import op


revision = "20260428_v9_crm_sync"
down_revision = "20260427_v8_crm_tenant_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_connections (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER,
            provider VARCHAR(40) NOT NULL,
            label VARCHAR(120) NOT NULL,
            base_url VARCHAR(400),
            oauth_token_encrypted TEXT,
            refresh_token_encrypted TEXT,
            expires_at TIMESTAMPTZ,
            sync_state VARCHAR(40) NOT NULL DEFAULT 'idle',
            last_sync_at TIMESTAMPTZ,
            is_active BOOLEAN NOT NULL DEFAULT FALSE,
            credentials_json TEXT,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_crm_connections_tenant_active ON crm_connections (tenant_id, is_active)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_field_mappings (
            id SERIAL PRIMARY KEY,
            connection_id INTEGER NOT NULL REFERENCES crm_connections(id) ON DELETE CASCADE,
            entity_type VARCHAR(40) NOT NULL,
            internal_field VARCHAR(120) NOT NULL,
            external_field VARCHAR(120) NOT NULL,
            direction VARCHAR(20) NOT NULL DEFAULT 'bidirectional',
            transform_rule_json TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_sync_jobs (
            id SERIAL PRIMARY KEY,
            connection_id INTEGER NOT NULL REFERENCES crm_connections(id) ON DELETE CASCADE,
            entity_type VARCHAR(40) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            items_pulled INTEGER NOT NULL DEFAULT 0,
            items_pushed INTEGER NOT NULL DEFAULT 0,
            items_failed INTEGER NOT NULL DEFAULT 0,
            error_log_json TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_crm_sync_jobs_conn_started ON crm_sync_jobs (connection_id, started_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_record_links (
            id SERIAL PRIMARY KEY,
            connection_id INTEGER NOT NULL REFERENCES crm_connections(id) ON DELETE CASCADE,
            internal_entity_type VARCHAR(40) NOT NULL,
            internal_id INTEGER NOT NULL,
            external_id VARCHAR(120) NOT NULL,
            last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            hash_signature VARCHAR(64),
            CONSTRAINT uq_crm_record_links UNIQUE (connection_id, internal_entity_type, internal_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_crm_record_links_external ON crm_record_links (connection_id, external_id)"
    )


def downgrade() -> None:
    for t in ("crm_record_links", "crm_sync_jobs", "crm_field_mappings", "crm_connections"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
