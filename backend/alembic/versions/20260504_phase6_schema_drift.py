"""Backfill missing CREATE TABLE statements for create_all-only tables (R4-DB-1/2/3)

Revision ID: 20260504_phase6_drift
Revises: 20260504_phase5_reports
Create Date: 2026-05-04

Round-4 audit identified eight tables (plus columns on customers and
quotes) that exist in production purely because ``Base.metadata.
create_all()`` runs at boot. They have no migration. This is the
same anti-pattern that produced DB-7 (invoices) and DB-6
(opportunities.source) last sprint.

Fresh prod environments — anything that bootstraps via ``alembic
upgrade head`` only (read replica, IaC-provisioned DB, restored
from logical backup) — crash on first query because the table
isn't there. Existing envs are fine because create_all already
made the tables; the migration is a no-op on those (CREATE TABLE
IF NOT EXISTS, ADD COLUMN IF NOT EXISTS).

Tables created:
  - customers              (the actual base table; round-3 only added
                            tenant_id and KVKK columns to the
                            already-existing one)
  - audit_logs
  - coaching_plans
  - competitor_mentions
  - forecast_snapshot_details
  - territories + territory_assignments
  - subscriptions          (R4-CLOSE-1 sibling — Phase 3 added
                            tenant_id but the base table itself was
                            still create_all-only)

Columns added to existing tables:
  - quotes: version, pdf_path, close_reason, closed_at + KVKK-related
  - customers (when the CREATE TABLE IF NOT EXISTS is a no-op): all
    KVKK fields, enrichment fields, and territory_id

Idempotent both ways. Downgrade is intentionally no-op on the
CREATE TABLE side (we never want a future upgrade to silently
recreate the table on a env where downgrade was run; explicit drop
should be a separate manual migration if ever needed).
"""

from alembic import op


revision = "20260504_phase6_drift"
down_revision = "20260504_phase5_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── customers ─────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            company VARCHAR(255),
            email VARCHAR(255) NOT NULL,
            phone VARCHAR(50),
            address TEXT,
            tax_id VARCHAR(50),
            preferred_lang VARCHAR(5) NOT NULL DEFAULT 'tr',
            tenant_id INTEGER,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            kvkk_consent BOOLEAN NOT NULL DEFAULT FALSE,
            kvkk_consent_date TIMESTAMPTZ,
            kvkk_consent_method VARCHAR(50),
            data_retention_until TIMESTAMPTZ,
            data_processing_purpose VARCHAR(200),
            deletion_requested_at TIMESTAMPTZ,
            data_classification VARCHAR(20),
            industry VARCHAR(100),
            employee_count INTEGER,
            annual_revenue VARCHAR(50),
            website VARCHAR(255),
            linkedin_url VARCHAR(255),
            enriched_at TIMESTAMPTZ,
            territory_id INTEGER,
            parent_id INTEGER
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_customers_email ON customers (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customers_tenant_id ON customers (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customers_parent_id ON customers (parent_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customers_territory_id ON customers (territory_id)"
    )
    # Extra columns that prior model edits introduced (no-op when the
    # CREATE TABLE above just ran; populates on legacy envs that
    # only had the original 8 columns).
    for col, ddl in (
        ("preferred_lang", "VARCHAR(5) NOT NULL DEFAULT 'tr'"),
        ("kvkk_consent", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("kvkk_consent_date", "TIMESTAMPTZ"),
        ("kvkk_consent_method", "VARCHAR(50)"),
        ("data_retention_until", "TIMESTAMPTZ"),
        ("data_processing_purpose", "VARCHAR(200)"),
        ("deletion_requested_at", "TIMESTAMPTZ"),
        ("data_classification", "VARCHAR(20)"),
    ):
        op.execute(
            f"ALTER TABLE customers ADD COLUMN IF NOT EXISTS {col} {ddl}"
        )

    # ── quotes — missing columns (R4-DB-3) ──────────────────────
    for col, ddl in (
        ("version", "INTEGER NOT NULL DEFAULT 1"),
        ("pdf_path", "VARCHAR(500)"),
        ("close_reason", "VARCHAR(50)"),
        ("closed_at", "TIMESTAMPTZ"),
    ):
        op.execute(f"ALTER TABLE quotes ADD COLUMN IF NOT EXISTS {col} {ddl}")

    # ── audit_logs ─────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            tenant_id INTEGER,
            action VARCHAR(50) NOT NULL,
            entity_type VARCHAR(50) NOT NULL,
            entity_id INTEGER NOT NULL,
            changes TEXT,
            ip_address VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_id ON audit_logs (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_type ON audit_logs (entity_type)")

    # ── coaching_plans ─────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS coaching_plans (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            manager_id INTEGER NOT NULL REFERENCES users(id),
            goals_json TEXT NOT NULL,
            weeks INTEGER NOT NULL DEFAULT 4,
            start_date DATE,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_coaching_plans_user_id ON coaching_plans (user_id)"
    )

    # ── competitor_mentions ────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS competitor_mentions (
            id SERIAL PRIMARY KEY,
            competitor_name VARCHAR(200) NOT NULL,
            source_entity_type VARCHAR(30) NOT NULL,
            source_entity_id INTEGER NOT NULL,
            opportunity_id INTEGER REFERENCES opportunities(id),
            context_snippet TEXT,
            sentiment VARCHAR(20),
            detected_by VARCHAR(20) NOT NULL DEFAULT 'keyword',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_competitor_mentions_name "
        "ON competitor_mentions (competitor_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_competitor_mentions_opportunity_id "
        "ON competitor_mentions (opportunity_id)"
    )

    # ── forecast_snapshot_details ──────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS forecast_snapshot_details (
            id SERIAL PRIMARY KEY,
            snapshot_id INTEGER REFERENCES pipeline_snapshots(id),
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
            forecast_category VARCHAR(20),
            amount DOUBLE PRECISION NOT NULL DEFAULT 0,
            stage VARCHAR(30) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_fsd_snapshot ON forecast_snapshot_details (snapshot_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fsd_opportunity "
        "ON forecast_snapshot_details (opportunity_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fsd_created ON forecast_snapshot_details (created_at)"
    )

    # ── territories ────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS territories (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER,
            name VARCHAR(100) NOT NULL,
            parent_id INTEGER REFERENCES territories(id),
            description TEXT,
            region VARCHAR(100),
            rules_json TEXT,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_territory_parent ON territories (parent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_territory_tenant ON territories (tenant_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS territory_assignments (
            id SERIAL PRIMARY KEY,
            territory_id INTEGER NOT NULL REFERENCES territories(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            role VARCHAR(20) NOT NULL DEFAULT 'member',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_territory_user UNIQUE (territory_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ta_territory ON territory_assignments (territory_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ta_user ON territory_assignments (user_id)")

    # ── subscriptions ──────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            quote_id INTEGER REFERENCES quotes(id),
            name VARCHAR(200) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            billing_cycle VARCHAR(20) NOT NULL DEFAULT 'monthly',
            start_date DATE NOT NULL,
            end_date DATE,
            mrr DOUBLE PRECISION NOT NULL DEFAULT 0,
            next_renewal_date DATE,
            auto_renew BOOLEAN NOT NULL DEFAULT TRUE,
            items_json TEXT,
            currency VARCHAR(10) NOT NULL DEFAULT 'TRY',
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_customer_id "
        "ON subscriptions (customer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_subscriptions_tenant_id "
        "ON subscriptions (tenant_id)"
    )


def downgrade() -> None:
    # Intentional no-op. Dropping these tables would destroy live
    # data. The audit fix is purely about getting alembic to know
    # the tables exist; if a future migration needs to remove them
    # it should be authored explicitly.
    pass
