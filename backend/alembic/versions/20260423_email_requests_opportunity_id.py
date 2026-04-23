"""email_requests.opportunity_id — v2 opportunity timeline (S2)

Revision ID: 20260423_email_opportunity
Revises: 20260422_opportunity_foundation
Create Date: 2026-04-23

"""

from alembic import op
import sqlalchemy as sa


revision = "20260423_email_opportunity"
down_revision = "20260422_opportunity_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("email_requests") as batch:
        batch.add_column(sa.Column("opportunity_id", sa.Integer(), nullable=True))
        batch.create_index("ix_email_requests_opportunity_id", ["opportunity_id"])
        batch.create_foreign_key(
            "fk_email_requests_opportunity_id",
            "opportunities",
            ["opportunity_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("email_requests") as batch:
        batch.drop_constraint("fk_email_requests_opportunity_id", type_="foreignkey")
        batch.drop_index("ix_email_requests_opportunity_id")
        batch.drop_column("opportunity_id")
