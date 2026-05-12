"""Round-12 R12-AUTH-1/2 — add tenant_id to email_templates and shared_documents.

The Round-12 audit identified that ``email_templates`` and
``shared_documents`` had no ``tenant_id`` column, making cross-tenant
reads/writes possible:

  * ``EmailTemplateService.list_templates`` filtered only by
    ``created_by == user_id OR is_shared``, so any ``is_shared=True``
    template was globally visible across tenants. ``get_template(id)``
    had no owner filter at all.

  * ``SharedDocument`` filtered list/analytics by ``created_by``, but
    a ``user_id`` collision across tenants (theoretical today, possible
    after user-import) would have leaked tracking analytics + linked
    quotes across tenants.

Fix:
  * Add nullable ``tenant_id INTEGER`` to both tables, indexed for the
    scoped_for_user filter.
  * Backfill from ``created_by → users.tenant_id`` for existing rows.
  * Keep nullable on disk for one deploy cycle so any orphan
    (created_by user deleted) doesn't trip NOT NULL; a follow-up
    revision will promote to NOT NULL after a stable cycle, matching
    the R10 phase8 → R10 promote_not_null pattern.

ProductRule was intentionally NOT included — ``spare_parts`` is the
global product catalog (no tenant_id), so product rules are
system-wide by design. ``CustomField`` was also excluded for the same
reason (admin-only global config). The Round-12 audit's flags on
those two were false positives.

asyncpg constraint: every ``op.execute()`` carries exactly one SQL
statement (multi-statement strings raise PostgresSyntaxError).

Revision ID: 20260518_phase12_tenant_columns
Revises: 20260517_phase11_fk_indexes
Create Date: 2026-05-12
"""

from __future__ import annotations

from alembic import op


revision = "20260518_phase12_tenant_columns"
down_revision = "20260517_phase11_fk_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── email_templates.tenant_id ──
    op.execute(
        "ALTER TABLE email_templates "
        "ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    # Backfill from the creator's tenant. Users without tenant_id keep
    # the column NULL (legacy single-tenant deployments).
    op.execute(
        """
        UPDATE email_templates et
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE et.tenant_id IS NULL
          AND et.created_by = u.id
          AND u.tenant_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_templates_tenant_id "
        "ON email_templates (tenant_id)"
    )

    # ── shared_documents.tenant_id ──
    op.execute(
        "ALTER TABLE shared_documents "
        "ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    op.execute(
        """
        UPDATE shared_documents sd
        SET tenant_id = u.tenant_id
        FROM users u
        WHERE sd.tenant_id IS NULL
          AND sd.created_by = u.id
          AND u.tenant_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_shared_documents_tenant_id "
        "ON shared_documents (tenant_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_email_templates_tenant_id")
    op.execute("DROP INDEX IF EXISTS ix_shared_documents_tenant_id")
    op.execute("ALTER TABLE email_templates DROP COLUMN IF EXISTS tenant_id")
    op.execute("ALTER TABLE shared_documents DROP COLUMN IF EXISTS tenant_id")
