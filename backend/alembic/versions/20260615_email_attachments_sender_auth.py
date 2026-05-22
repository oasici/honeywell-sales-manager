"""Round-17 email pipeline hardening — add ``attachments_json`` and
``sender_auth_status`` to ``email_requests``.

Closes the biggest gap in the email pipeline coverage audit
(``docs/audits/2026-05-21-email-pipeline-coverage.md``): incoming
attachments (Excel / CSV / PDF) were never parsed, and inbound
sender authentication (SPF / DKIM / DMARC) was never verified.

Both columns are nullable — legacy rows have no parsed attachments
to record and no auth verdict to back-fill. The IMAP poll path now
populates them at ingest time; existing rows simply skip the
attachment-merge step at re-parse time.

Idempotent — uses ``ADD COLUMN IF NOT EXISTS`` so a re-run after a
partial deploy is a no-op.

Revision ID: 20260615_email_attachments_sender_auth
Revises: 20260614_add_tenant_id_to_feature_store_rollups
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op


revision = "20260615_email_attachments_sender_auth"
down_revision = "20260614_add_tenant_id_to_feature_store_rollups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE email_requests "
        "ADD COLUMN IF NOT EXISTS attachments_json TEXT"
    )
    op.execute(
        "ALTER TABLE email_requests "
        "ADD COLUMN IF NOT EXISTS sender_auth_status VARCHAR(20)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE email_requests DROP COLUMN IF EXISTS sender_auth_status")
    op.execute("ALTER TABLE email_requests DROP COLUMN IF EXISTS attachments_json")
