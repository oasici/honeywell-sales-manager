"""decision gaps tables

Revision ID: 20260426_decision_gaps
Revises: 20260426_buyer_state_history
Create Date: 2026-04-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260426_decision_gaps"
down_revision = "20260426_buyer_state_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stakeholder_roles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("stakeholder_id", sa.Integer(), nullable=False),
        sa.Column("role_key", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="rule"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stakeholder_id"], ["stakeholders.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_stakeholder_roles_opportunity_id", "stakeholder_roles", ["opportunity_id"])
    op.create_index("ix_stakeholder_roles_stakeholder_id", "stakeholder_roles", ["stakeholder_id"])
    op.create_index("ix_stakeholder_roles_opp_role", "stakeholder_roles", ["opportunity_id", "role_key"])

    op.create_table(
        "decision_gaps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("gap_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False, server_default="med"),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("expected_roles_json", sa.Text(), nullable=True),
        sa.Column("observed_roles_json", sa.Text(), nullable=True),
        sa.Column("recommended_actions_json", sa.Text(), nullable=True),
        sa.Column("drivers_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_decision_gaps_opportunity_id", "decision_gaps", ["opportunity_id"])
    op.create_index("ix_decision_gaps_opp_type", "decision_gaps", ["opportunity_id", "gap_type"])


def downgrade() -> None:
    op.drop_index("ix_decision_gaps_opp_type", table_name="decision_gaps")
    op.drop_index("ix_decision_gaps_opportunity_id", table_name="decision_gaps")
    op.drop_table("decision_gaps")

    op.drop_index("ix_stakeholder_roles_opp_role", table_name="stakeholder_roles")
    op.drop_index("ix_stakeholder_roles_stakeholder_id", table_name="stakeholder_roles")
    op.drop_index("ix_stakeholder_roles_opportunity_id", table_name="stakeholder_roles")
    op.drop_table("stakeholder_roles")

