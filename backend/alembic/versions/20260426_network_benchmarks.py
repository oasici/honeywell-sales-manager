"""network segments + daily benchmarks

Revision ID: 20260426_network_benchmarks
Revises: 20260426_decision_gaps
Create Date: 2026-04-26
"""

from alembic import op
from app.core.migration_helpers import create_table_if_absent
import sqlalchemy as sa


revision = "20260426_network_benchmarks"
down_revision = "20260426_decision_gaps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table_if_absent(
        "network_segments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("segment_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("definition_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_network_segments_segment_key ON network_segments (segment_key)")

    create_table_if_absent(
        "segment_benchmarks_daily",
        sa.Column("segment_key", sa.String(length=80), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("win_rate_90d", sa.Float(), nullable=True),
        sa.Column("followup_median_days", sa.Float(), nullable=True),
        sa.Column("avg_discount_pct", sa.Float(), nullable=True),
        sa.Column("avg_stakeholder_count", sa.Float(), nullable=True),
        sa.Column("objection_rate_14d", sa.Float(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("segment_key", "snapshot_date"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_sbd_snapshot_date ON segment_benchmarks_daily (snapshot_date)")


def downgrade() -> None:
    op.drop_index("ix_sbd_snapshot_date", table_name="segment_benchmarks_daily")
    op.drop_table("segment_benchmarks_daily")

    op.drop_index("ix_network_segments_segment_key", table_name="network_segments")
    op.drop_table("network_segments")

