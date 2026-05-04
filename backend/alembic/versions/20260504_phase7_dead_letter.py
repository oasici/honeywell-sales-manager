"""Create dead_letter_events table (R4-EG-1)

Revision ID: 20260504_dead_letter
Revises: 20260504_phase6_drift
Create Date: 2026-05-04

Round-4 audit R4-EG-1. The event bus drops payload on the floor
after retry exhaustion (Sentry captures the exception but no
operator surface exists to inspect or replay). This migration adds
the persistence layer; the admin CRUD lives in
``backend/app/api/v1/admin_dead_letters.py``.

Idempotent both ways.
"""

from alembic import op


revision = "20260504_dead_letter"
down_revision = "20260504_phase6_drift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dead_letter_events (
            id SERIAL PRIMARY KEY,
            event_type VARCHAR(80) NOT NULL,
            handler_name VARCHAR(120) NOT NULL,
            payload_json TEXT NOT NULL,
            error_message TEXT,
            error_traceback TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 2,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            replayed_at TIMESTAMPTZ,
            replayed_by INTEGER REFERENCES users(id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dle_event_type "
        "ON dead_letter_events (event_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dle_handler_name "
        "ON dead_letter_events (handler_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dle_created_at "
        "ON dead_letter_events (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dle_replayed_at "
        "ON dead_letter_events (replayed_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dead_letter_events")
