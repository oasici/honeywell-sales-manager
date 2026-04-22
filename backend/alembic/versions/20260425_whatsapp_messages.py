"""WhatsApp Business inbound / outbound message log (v3).

Revision ID: 20260425_whatsapp_messages
Revises: 20260424_field_audit_log
Create Date: 2026-04-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260425_whatsapp_messages"
down_revision = "20260424_field_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("wa_message_id", sa.String(length=128), nullable=True),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("media_url", sa.String(length=500), nullable=True),
        sa.Column("template_name", sa.String(length=128), nullable=True),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customers.id"),
            nullable=True,
        ),
        sa.Column(
            "lead_id",
            sa.Integer(),
            sa.ForeignKey("leads.id"),
            nullable=True,
        ),
        sa.Column(
            "sent_by",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="received"),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_whatsapp_messages_direction", "whatsapp_messages", ["direction"])
    op.create_index("ix_whatsapp_messages_phone", "whatsapp_messages", ["phone_number"])
    op.create_index("ix_whatsapp_messages_customer", "whatsapp_messages", ["customer_id"])
    op.create_index("ix_whatsapp_messages_lead", "whatsapp_messages", ["lead_id"])
    op.create_index("ix_whatsapp_messages_wa", "whatsapp_messages", ["wa_message_id"])
    op.create_index("ix_whatsapp_messages_created_at", "whatsapp_messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_whatsapp_messages_created_at", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_wa", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_lead", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_customer", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_phone", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_direction", table_name="whatsapp_messages")
    op.drop_table("whatsapp_messages")
