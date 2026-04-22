"""WhatsApp Business models.

Two simple tables keep the WhatsApp thread auditable:

    whatsapp_messages           - every inbound + outbound message.
    whatsapp_template_sends     - outbound template deliveries for
                                  rate-limit + billing monitoring.

Threading: messages are keyed by ``phone_number`` (E.164) and optionally
attached to a ``customer_id`` / ``lead_id`` when we can resolve it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    direction: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    # "in" | "out"

    wa_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # E.164 form (+905551112233)

    body: Mapped[str] = mapped_column(Text, nullable=False)
    media_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    template_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True, index=True
    )
    lead_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("leads.id"), nullable=True, index=True
    )

    sent_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="received")
    # inbound: "received" | "read"
    # outbound: "queued" | "sent" | "delivered" | "read" | "failed"

    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
