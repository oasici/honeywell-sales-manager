"""opportunity foundation: opportunities + timeline + signals + tasks + quote binding

Revision ID: 20260422_opportunity_foundation
Revises: 20260413_add_customer_parent_id
Create Date: 2026-04-22

"""

from alembic import op
from app.core.migration_helpers import create_table_if_absent
import sqlalchemy as sa


revision = "20260422_opportunity_foundation"
down_revision = "20260413_add_customer_parent_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── opportunities ─────────────────────────────────────
    create_table_if_absent(
        "opportunities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=False, server_default="prospecting"),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="TRY"),
        sa.Column("close_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        # Optional v2 fields already referenced by services (keep nullable/defaults).
        sa.Column("source", sa.String(length=30), nullable=True),
        sa.Column("forecast_category", sa.String(length=20), nullable=True),
        sa.Column("probability", sa.Float(), nullable=False, server_default="0"),
        sa.Column("loss_reason", sa.String(length=200), nullable=True),
        sa.Column("previous_stage", sa.String(length=30), nullable=True),
        sa.Column("previous_close_date", sa.Date(), nullable=True),
        sa.Column("previous_amount", sa.Float(), nullable=True),
        sa.Column("pipeline_id", sa.Integer(), nullable=True),
        sa.Column("territory_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipelines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["territory_id"], ["territories.id"], ondelete="SET NULL"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_opp_owner_stage ON opportunities (owner_id, stage)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_opp_customer ON opportunities (customer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_opp_close_date ON opportunities (close_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_opportunities_pipeline_id ON opportunities (pipeline_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_opportunities_territory_id ON opportunities (territory_id)")

    # ── opportunity_events (timeline) ─────────────────────
    create_table_if_absent(
        "opportunity_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_opportunity_events_opportunity_id ON opportunity_events (opportunity_id)")

    # ── opportunity_signals ───────────────────────────────
    create_table_if_absent(
        "opportunity_signals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("signal_type", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False, server_default="med"),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_opportunity_signals_opportunity_id ON opportunity_signals (opportunity_id)")

    # ── tasks ─────────────────────────────────────────────
    create_table_if_absent(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="normal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tasks_owner_id ON tasks (owner_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tasks_opportunity_id ON tasks (opportunity_id)")

    # ── quotes.opportunity_id (nullable, backward compatible) ──
    # Round-4 v1.9.14 — converted from batch_alter_table to raw SQL
    # so it's a no-op on the bootstrapped schema.
    op.execute(
        "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS opportunity_id INTEGER"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_quotes_opportunity_id "
        "ON quotes (opportunity_id)"
    )
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE quotes
                ADD CONSTRAINT fk_quotes_opportunity_id
                FOREIGN KEY (opportunity_id) REFERENCES opportunities(id)
                ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object OR duplicate_table THEN NULL;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE quotes DROP CONSTRAINT IF EXISTS fk_quotes_opportunity_id"
    )
    op.execute("DROP INDEX IF EXISTS ix_quotes_opportunity_id")
    op.execute("ALTER TABLE quotes DROP COLUMN IF EXISTS opportunity_id")

    op.drop_index("ix_tasks_opportunity_id", table_name="tasks")
    op.drop_index("ix_tasks_owner_id", table_name="tasks")
    op.drop_table("tasks")

    op.drop_index("ix_opportunity_signals_opportunity_id", table_name="opportunity_signals")
    op.drop_table("opportunity_signals")

    op.drop_index("ix_opportunity_events_opportunity_id", table_name="opportunity_events")
    op.drop_table("opportunity_events")

    op.drop_index("ix_opportunities_territory_id", table_name="opportunities")
    op.drop_index("ix_opportunities_pipeline_id", table_name="opportunities")
    op.drop_index("ix_opp_close_date", table_name="opportunities")
    op.drop_index("ix_opp_customer", table_name="opportunities")
    op.drop_index("ix_opp_owner_stage", table_name="opportunities")
    op.drop_table("opportunities")

