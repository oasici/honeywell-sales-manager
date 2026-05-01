"""Create invoices table — model existed without a migration

Revision ID: 20260503_create_invoices
Revises: 20260502_value_date_to_date
Create Date: 2026-05-03

The Invoice model has been live in prod since the v1.5.x invoicing
sprint, but no migration was ever authored. The table presumably got
created via SQLAlchemy's metadata.create_all() at first boot or via a
one-off SQL run; either way it's invisible to `alembic upgrade head`.

Round-3 audit DB-7. This migration uses CREATE TABLE IF NOT EXISTS so
existing prod deployments are a no-op while fresh environments can
bootstrap the schema cleanly. Column list, types, defaults, and indexes
match `app/models/invoice.py` exactly so future autogenerate runs see
no drift.

Tenant column note: the model does NOT carry tenant_id (unlike Quote,
Customer, Opportunity). If multi-tenant invoice isolation becomes a
requirement, that's a separate model + migration (and would need TEN-
style bulk-action / detail tenant guards everywhere).

Idempotent both ways.
"""

from alembic import op


revision = "20260503_create_invoices"
down_revision = "20260502_value_date_to_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id SERIAL PRIMARY KEY,
            invoice_number VARCHAR(50) UNIQUE NOT NULL,
            quote_id INTEGER REFERENCES quotes(id),
            contract_id INTEGER REFERENCES contracts(id),
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            created_by INTEGER NOT NULL REFERENCES users(id),
            issue_date TIMESTAMPTZ,
            due_date TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            currency VARCHAR(10) NOT NULL DEFAULT 'TRY',
            subtotal DOUBLE PRECISION NOT NULL DEFAULT 0,
            tax_rate DOUBLE PRECISION NOT NULL DEFAULT 18,
            tax_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
            grand_total DOUBLE PRECISION NOT NULL DEFAULT 0,
            items_json TEXT,
            notes TEXT,
            pdf_path VARCHAR(500),
            paid_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_invoice_customer ON invoices (customer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_invoice_status ON invoices (status)"
    )


def downgrade() -> None:
    # Intentionally no-op. Dropping the table would destroy live
    # invoice data; the audit fix is purely about getting alembic to
    # know the table exists. If you actually need to remove invoices
    # in a future migration, write a dedicated drop with explicit
    # confirmation.
    pass
