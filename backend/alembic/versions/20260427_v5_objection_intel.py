"""V5 objection intelligence: objections, resolution_actions, patterns

Revision ID: 20260427_v5_objection_intel
Revises: 20260427_v5_foundation
Create Date: 2026-04-27

Persistent store for objection lifecycle tracking. Detection logic
already exists in `conversation_insights_service`; this migration adds
the schema needed to materialize objections, track resolution actions,
and mine successful patterns per segment.
"""

from alembic import op


revision = "20260427_v5_objection_intel"
down_revision = "20260427_v5_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── objections ──
    # `event_id` is a soft pointer to the originating sales_event_shadow
    # row when detection runs over events. Not a hard FK because we may
    # also detect from older activity_log rows that pre-date V4 shadow.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS objections (
            id SERIAL PRIMARY KEY,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            event_id INTEGER,
            objection_type VARCHAR(40) NOT NULL,
            severity VARCHAR(10) NOT NULL DEFAULT 'med',
            evidence_text TEXT,
            resolved_flag BOOLEAN NOT NULL DEFAULT FALSE,
            resolved_at TIMESTAMPTZ,
            ttr_hours DOUBLE PRECISION,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_objections_opportunity_id ON objections (opportunity_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_objections_type_resolved "
        "ON objections (objection_type, resolved_flag)"
    )

    # ── objection_resolution_actions ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS objection_resolution_actions (
            id SERIAL PRIMARY KEY,
            objection_id INTEGER NOT NULL REFERENCES objections(id) ON DELETE CASCADE,
            action_type VARCHAR(40) NOT NULL,
            action_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            payload_json TEXT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_objection_resolution_actions_objection_id "
        "ON objection_resolution_actions (objection_id)"
    )

    # ── objection_patterns ──
    # Mined per (segment_key, objection_type). Updated by nightly job;
    # `success_rate` = won_after_action / total_with_action over 90d.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS objection_patterns (
            id SERIAL PRIMARY KEY,
            segment_key VARCHAR(80) NOT NULL,
            objection_type VARCHAR(40) NOT NULL,
            recommended_resolution_json TEXT NOT NULL DEFAULT '[]',
            success_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
            sample_size INTEGER NOT NULL DEFAULT 0,
            last_trained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (segment_key, objection_type)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_objection_patterns_segment "
        "ON objection_patterns (segment_key)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS objection_patterns")
    op.execute("DROP TABLE IF EXISTS objection_resolution_actions")
    op.execute("DROP TABLE IF EXISTS objections")
