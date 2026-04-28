"""V9 calendar OAuth + meeting auto-log

Revision ID: 20260428_v9_calendar_oauth
Revises: 20260428_v9_crm_sync
Create Date: 2026-04-28

V2 Epic C1 — calendar adapter skeleton + auto-log.

Idempotent.
"""

from alembic import op


revision = "20260428_v9_calendar_oauth"
down_revision = "20260428_v9_crm_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS calendar_connections (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider VARCHAR(40) NOT NULL,
            calendar_id VARCHAR(200),
            oauth_token_encrypted TEXT,
            refresh_token_encrypted TEXT,
            expires_at TIMESTAMPTZ,
            is_active BOOLEAN NOT NULL DEFAULT FALSE,
            last_sync_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_calendar_connections_user_provider UNIQUE (user_id, provider)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS meeting_auto_links (
            id SERIAL PRIMARY KEY,
            meeting_booking_id INTEGER REFERENCES meeting_bookings(id) ON DELETE CASCADE,
            external_event_id VARCHAR(200),
            opportunity_id INTEGER REFERENCES opportunities(id) ON DELETE SET NULL,
            customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
            matched_by VARCHAR(40) NOT NULL DEFAULT 'attendee_email',
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_meeting_auto_links_opp ON meeting_auto_links (opportunity_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS meeting_auto_links")
    op.execute("DROP TABLE IF EXISTS calendar_connections")
