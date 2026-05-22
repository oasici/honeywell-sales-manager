"""Round-18 multi-email RFQ aggregation — add ``rfq_thread_key``.

Stable 16-hex digest of the RFQ thread identity (tenant_id +
thread_id, or tenant_id + sender_domain + normalised_subject) so
emails belonging to the same logical RFQ can be grouped without an
explicit FK to a separate RFQ table.

Nullable — legacy rows have no key yet; the
``EmailProcessingService.process_email`` path back-fills on the
next parse of each row. An idempotent backfill query is included
in the upgrade for the easy case (rows with a non-null
``thread_id``).

Revision ID: 20260616_email_rfq_thread_key
Revises: 20260615_email_attachments_sender_auth
Create Date: 2026-05-22
"""

from __future__ import annotations

from alembic import op


revision = "20260616_email_rfq_thread_key"
down_revision = "20260615_email_attachments_sender_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE email_requests "
        "ADD COLUMN IF NOT EXISTS rfq_thread_key VARCHAR(32)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_requests_rfq_thread_key "
        "ON email_requests (rfq_thread_key)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_email_requests_rfq_thread_key")
    op.execute("ALTER TABLE email_requests DROP COLUMN IF EXISTS rfq_thread_key")
