"""v4 sales events shadow table (additive)

Revision ID: 20260427_v4_sales_events_shadow
Revises: 20260426_network_benchmarks
Create Date: 2026-04-27
"""

from alembic import op
from app.core.migration_helpers import create_table_if_absent
import sqlalchemy as sa


revision = "20260427_v4_sales_events_shadow"
down_revision = "20260426_network_benchmarks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table_if_absent(
        "v4_sales_events_shadow",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_ref", sa.String(length=180), nullable=False),
        sa.Column("provenance", sa.String(length=40), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("contact_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("event_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_v4_sales_events_shadow_source_ref ON v4_sales_events_shadow (source_ref)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_v4_sales_events_shadow_account_id ON v4_sales_events_shadow (account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_v4_sales_events_shadow_opportunity_id ON v4_sales_events_shadow (opportunity_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_v4_sales_events_shadow_event_ts ON v4_sales_events_shadow (event_ts)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_v4_sales_shadow_opp_ts ON v4_sales_events_shadow (opportunity_id, event_ts)")


def downgrade() -> None:
    op.drop_index("ix_v4_sales_shadow_opp_ts", table_name="v4_sales_events_shadow")
    op.drop_index("ix_v4_sales_events_shadow_event_ts", table_name="v4_sales_events_shadow")
    op.drop_index("ix_v4_sales_events_shadow_opportunity_id", table_name="v4_sales_events_shadow")
    op.drop_index("ix_v4_sales_events_shadow_account_id", table_name="v4_sales_events_shadow")
    op.drop_index("ix_v4_sales_events_shadow_source_ref", table_name="v4_sales_events_shadow")
    op.drop_table("v4_sales_events_shadow")
