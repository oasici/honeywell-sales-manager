"""Round-19 Phase 1 — eligibility-gate columns on email_requests.

F-002 ``parse_skipped_reason`` + ``parse_overridden_by``:
  Lets the auto-quote pipeline short-circuit on auth=fail mails
  *without* burning Anthropic tokens, while still surfacing the
  skipped state in the operator queue. ``parse_overridden_by``
  records the manager who later forces a parse (audit trail).

F-003 ``attachment_pages_truncated`` + ``ocr_skipped_pages``:
  Eligibility gate must refuse auto-quote when OCR truncated a
  multi-page PDF. Pre-Round-19 the truncation was only surfaced as
  a note; the gate ignored it.

F-004 ``first_time_sender``:
  Trust-on-first-use mitigation. Any email from a sender whose
  ``from_address`` does not match an existing ``Customer.primary_email``
  (within this tenant) is blocked from auto-quote until a human
  promotes the sender to a customer.

All columns are nullable (or have safe defaults) so the migration is
idempotent and the back-fill is a no-op for legacy rows.

Revision ID: 20260626_email_eligibility_gate
Revises: 20260616_email_rfq_thread_key
"""

from __future__ import annotations

from alembic import op


revision = "20260626_email_eligibility_gate"
down_revision = "20260616_email_rfq_thread_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE email_requests "
        "ADD COLUMN IF NOT EXISTS parse_skipped_reason VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE email_requests "
        "ADD COLUMN IF NOT EXISTS parse_overridden_by INTEGER "
        "REFERENCES users(id)"
    )
    op.execute(
        "ALTER TABLE email_requests "
        "ADD COLUMN IF NOT EXISTS attachment_pages_truncated BOOLEAN "
        "NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE email_requests "
        "ADD COLUMN IF NOT EXISTS ocr_skipped_pages INTEGER"
    )
    op.execute(
        "ALTER TABLE email_requests "
        "ADD COLUMN IF NOT EXISTS first_time_sender BOOLEAN "
        "NOT NULL DEFAULT FALSE"
    )
    # Index on parse_skipped_reason for the operator queue filter
    # ("show me everything pending manual review").
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_requests_parse_skipped_reason "
        "ON email_requests (parse_skipped_reason) "
        "WHERE parse_skipped_reason IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_email_requests_parse_skipped_reason")
    op.execute(
        "ALTER TABLE email_requests DROP COLUMN IF EXISTS first_time_sender"
    )
    op.execute(
        "ALTER TABLE email_requests DROP COLUMN IF EXISTS ocr_skipped_pages"
    )
    op.execute(
        "ALTER TABLE email_requests "
        "DROP COLUMN IF EXISTS attachment_pages_truncated"
    )
    op.execute(
        "ALTER TABLE email_requests DROP COLUMN IF EXISTS parse_overridden_by"
    )
    op.execute(
        "ALTER TABLE email_requests DROP COLUMN IF EXISTS parse_skipped_reason"
    )
