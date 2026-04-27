"""V5 playbook expansion: playbook_steps + adherence + performance

Revision ID: 20260427_v5_playbook_expansion
Revises: 20260427_v5_network_expansion
Create Date: 2026-04-27

Existing `playbooks.steps_json` blob is kept (backwards compat) but
parallel rows in `playbook_steps` give us per-step tracking. Adherence
is what coaching_service computes in-memory today; persisting it
unlocks the lift_vs_control rollup in `playbook_performance`.
"""

from alembic import op


revision = "20260427_v5_playbook_expansion"
down_revision = "20260427_v5_network_expansion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS playbook_steps (
            id SERIAL PRIMARY KEY,
            playbook_id INTEGER NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
            step_no INTEGER NOT NULL,
            trigger_condition_json TEXT NOT NULL DEFAULT '{}',
            recommended_action_json TEXT NOT NULL DEFAULT '{}',
            expected_window_hours INTEGER NOT NULL DEFAULT 48,
            success_metric VARCHAR(60),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (playbook_id, step_no)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_playbook_steps_playbook "
        "ON playbook_steps (playbook_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS playbook_adherence (
            id SERIAL PRIMARY KEY,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            playbook_id INTEGER NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
            step_id INTEGER NOT NULL REFERENCES playbook_steps(id) ON DELETE CASCADE,
            eligible_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_playbook_adherence_opp "
        "ON playbook_adherence (opportunity_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_playbook_adherence_status "
        "ON playbook_adherence (playbook_id, status)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS playbook_performance (
            id SERIAL PRIMARY KEY,
            playbook_id INTEGER NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            usage_count INTEGER NOT NULL DEFAULT 0,
            completion_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
            won_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
            lift_vs_control DOUBLE PRECISION NOT NULL DEFAULT 0,
            sample_size INTEGER NOT NULL DEFAULT 0,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (playbook_id, period_start, period_end)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS playbook_performance")
    op.execute("DROP TABLE IF EXISTS playbook_adherence")
    op.execute("DROP TABLE IF EXISTS playbook_steps")
