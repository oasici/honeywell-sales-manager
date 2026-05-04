"""v4 feature store daily tables

Revision ID: 20260425_v4_feature_store_daily
Revises: 20260427_index_hardening
Create Date: 2026-04-25
"""

from alembic import op
from app.core.migration_helpers import create_table_if_absent
import sqlalchemy as sa


revision = "20260425_v4_feature_store_daily"
down_revision = "20260427_index_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── opportunity_features_daily ──────────────────────
    create_table_if_absent(
        "opportunity_features_daily",
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("deal_age_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("days_since_last_rep_touch", sa.Integer(), nullable=False, server_default="999"),
        sa.Column("days_since_last_buyer_touch", sa.Integer(), nullable=False, server_default="999"),
        sa.Column("rep_touch_count_14d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buyer_reply_count_14d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meeting_count_30d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latest_discount_pct", sa.Float(), nullable=True),
        sa.Column("competitor_mentions_30d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pricing_objections_30d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("positive_signal_count_14d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("negative_signal_count_14d", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("momentum_score", sa.Integer(), nullable=True),
        sa.Column("buyer_state", sa.String(length=30), nullable=True),
        sa.Column("close_probability", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("opportunity_id", "snapshot_date"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ofd_snapshot_date ON opportunity_features_daily (snapshot_date)")

    # ── account_features_daily (account_id == customers.id) ──
    create_table_if_absent(
        "account_features_daily",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("open_opportunity_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_open_pipeline", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_deal_health", sa.Float(), nullable=True),
        sa.Column("last_touch_days", sa.Integer(), nullable=False, server_default="999"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("account_id", "snapshot_date"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_afd_snapshot_date ON account_features_daily (snapshot_date)")

    # ── rep_features_daily ──────────────────────────────
    create_table_if_absent(
        "rep_features_daily",
        sa.Column("rep_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("avg_followup_hours", sa.Float(), nullable=True),
        sa.Column("stakeholder_coverage_rate", sa.Float(), nullable=True),
        sa.Column("win_rate_adj", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["rep_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("rep_id", "snapshot_date"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_rfd_snapshot_date ON rep_features_daily (snapshot_date)")


def downgrade() -> None:
    op.drop_index("ix_rfd_snapshot_date", table_name="rep_features_daily")
    op.drop_table("rep_features_daily")

    op.drop_index("ix_afd_snapshot_date", table_name="account_features_daily")
    op.drop_table("account_features_daily")

    op.drop_index("ix_ofd_snapshot_date", table_name="opportunity_features_daily")
    op.drop_table("opportunity_features_daily")

