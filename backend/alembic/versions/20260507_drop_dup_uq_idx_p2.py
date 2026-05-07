"""Round-7 R7-DB-1 — drop redundant indexes on UNIQUE columns (phase 2).

Pre-R7:
- R6 closed the duplicate-index family for the auth-critical columns
  (``users.email``, ``customers.email``, ``user_sessions.jti``,
  ``signature_requests.token``).
- The same anti-pattern (``unique=True + index=True`` on the same
  column, or an explicit ``Index(..., col, unique=True)`` paired with
  column-level ``unique=True``) was alive on **13 more columns**:
    leads.email, api_keys.key_hash, email_requests.message_id,
    quotes.quote_number, spare_parts.honeywell_code, settings.key,
    meeting_links.slug, shared_documents.tracking_token,
    network_segments.segment_key, account_enrichments.customer_id,
    v4_sales_events_shadow.source_ref,
    lead_scoring_configs.factor_name, deal_rooms.external_token.

Effect of the duplication: storage waste + double write cost on every
INSERT/UPDATE on tables that include hot write paths (leads, emails,
quotes, parts).

The auto-created ``*_key`` constraint indexes (e.g. ``leads_email_key``)
stay in place — UNIQUE constraints in PostgreSQL always carry an index.

Revision ID: 20260507_drop_dup_uq_idx_p2
Revises: 20260506_drop_dup_unique_indexes
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op


revision = "20260507_drop_dup_uq_idx_p2"
down_revision = "20260506_drop_dup_unique_indexes"
branch_labels = None
depends_on = None


_DROPS = (
    "ix_leads_email",
    "ix_api_keys_key_hash",
    "ix_email_requests_message_id",
    "ix_quotes_quote_number",
    "ix_spare_parts_honeywell_code",
    "ix_settings_key",
    "ix_meeting_links_slug",
    "ix_shared_documents_tracking_token",
    "ix_network_segments_segment_key",
    "ix_account_enrichments_customer_id",
    "ix_v4_sales_events_shadow_source_ref",
    "ix_lead_scoring_configs_factor_name",
    "ix_deal_room_token",
)


def upgrade() -> None:
    for name in _DROPS:
        op.execute(f"DROP INDEX IF EXISTS {name}")


def downgrade() -> None:
    # Recreate as plain (non-unique) btree indexes; the column-level
    # UNIQUE constraint already provides the uniqueness guarantee.
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_email ON leads (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys (key_hash)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_requests_message_id "
        "ON email_requests (message_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_quotes_quote_number ON quotes (quote_number)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_spare_parts_honeywell_code "
        "ON spare_parts (honeywell_code)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_settings_key ON settings (key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_meeting_links_slug ON meeting_links (slug)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_shared_documents_tracking_token "
        "ON shared_documents (tracking_token)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_network_segments_segment_key "
        "ON network_segments (segment_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_account_enrichments_customer_id "
        "ON account_enrichments (customer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_v4_sales_events_shadow_source_ref "
        "ON v4_sales_events_shadow (source_ref)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lead_scoring_configs_factor_name "
        "ON lead_scoring_configs (factor_name)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_deal_room_token "
        "ON deal_rooms (external_token)"
    )
