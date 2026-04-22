"""WhatsApp Business API + inbound webhook.

Three concerns live here:
    - GET /integrations/whatsapp/webhook  -> Meta subscription handshake.
    - POST /integrations/whatsapp/webhook -> ingest inbound messages, store.
    - POST /integrations/whatsapp/send    -> authenticated outbound sends.

All behaviour is gated behind ``FEATURE_WHATSAPP``.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.user import User
from app.models.whatsapp import WhatsAppMessage
from app.services.whatsapp import (
    WhatsAppError,
    normalize_phone,
    parse_inbound,
    send_template,
    send_text,
    verify_webhook_challenge,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations/whatsapp", tags=["WhatsApp"])


def _require_flag() -> None:
    if not settings.FEATURE_WHATSAPP:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="WhatsApp integration disabled",
        )


# ── Webhook handshake + ingestion ───────────────────────────────────────────

@router.get("/webhook", response_class=Response)
async def webhook_verify(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
) -> Response:
    """Meta GET handshake: echo back the challenge on match."""
    _require_flag()
    result = verify_webhook_challenge(hub_mode, hub_verify_token, hub_challenge)
    if result is None:
        return Response(status_code=403)
    return Response(content=result, media_type="text/plain")


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def webhook_ingest(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Accept inbound WhatsApp messages, persist them, attach to a customer
    when we recognise the sender's phone number."""
    _require_flag()
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    messages = parse_inbound(payload)
    if not messages:
        return {"received": 0}

    saved = 0
    for msg in messages:
        phone = msg["phone_number"]
        existing = (
            await db.execute(
                select(WhatsAppMessage).where(
                    WhatsAppMessage.wa_message_id == msg["wa_message_id"]
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue

        customer_id = None
        customer = (
            await db.execute(
                select(Customer).where(Customer.phone.like(f"%{phone[-10:]}%"))
            )
        ).scalars().first()
        if customer:
            customer_id = customer.id

        record = WhatsAppMessage(
            direction="in",
            wa_message_id=msg["wa_message_id"],
            phone_number=phone,
            body=msg["text"] or "",
            customer_id=customer_id,
            status="received",
        )
        db.add(record)
        saved += 1

    if saved:
        await db.commit()
        logger.info("whatsapp.ingest saved=%d", saved)
    return {"received": saved}


# ── Outbound sends ──────────────────────────────────────────────────────────


class SendTextRequest(BaseModel):
    to: str = Field(..., min_length=5, max_length=32)
    body: str = Field(..., min_length=1, max_length=4096)
    customer_id: int | None = None
    lead_id: int | None = None


class SendTemplateRequest(BaseModel):
    to: str = Field(..., min_length=5, max_length=32)
    template_name: str = Field(..., min_length=1, max_length=128)
    language: str = Field("tr", min_length=2, max_length=8)
    parameters: list[str] = Field(default_factory=list)
    customer_id: int | None = None


class SendResult(BaseModel):
    message_id: int
    wa_message_id: str | None
    status: str


async def _persist_outbound(
    db: AsyncSession,
    *,
    response: dict[str, Any],
    phone: str,
    body: str,
    template_name: str | None,
    customer_id: int | None,
    lead_id: int | None,
    actor_id: int | None,
) -> WhatsAppMessage:
    wa_id: str | None = None
    messages = response.get("messages") if isinstance(response, dict) else None
    if isinstance(messages, list) and messages:
        wa_id = messages[0].get("id")
    row = WhatsAppMessage(
        direction="out",
        wa_message_id=wa_id,
        phone_number=phone,
        body=body,
        template_name=template_name,
        customer_id=customer_id,
        lead_id=lead_id,
        sent_by=actor_id,
        status="sent",
    )
    db.add(row)
    await db.flush()
    return row


@router.post("/send/text", response_model=SendResult)
async def send_text_message(
    body: SendTextRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.SALES_REP, UserRole.OPERATIONS))],
    db: AsyncSession = Depends(get_db),
) -> SendResult:
    _require_flag()
    try:
        phone = normalize_phone(body.to)
        response = await send_text(phone, body.body)
    except WhatsAppError as exc:
        raise HTTPException(400, str(exc)) from exc

    row = await _persist_outbound(
        db,
        response=response,
        phone=phone,
        body=body.body,
        template_name=None,
        customer_id=body.customer_id,
        lead_id=body.lead_id,
        actor_id=current_user.id,
    )
    await db.commit()
    return SendResult(message_id=row.id, wa_message_id=row.wa_message_id, status=row.status)


@router.post("/send/template", response_model=SendResult)
async def send_template_message(
    body: SendTemplateRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.SALES_REP, UserRole.OPERATIONS))],
    db: AsyncSession = Depends(get_db),
) -> SendResult:
    _require_flag()
    components = None
    if body.parameters:
        components = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in body.parameters],
            }
        ]
    try:
        phone = normalize_phone(body.to)
        response = await send_template(
            phone, body.template_name, language=body.language, components=components,
        )
    except WhatsAppError as exc:
        raise HTTPException(400, str(exc)) from exc

    rendered_body = f"[template:{body.template_name}] " + " | ".join(body.parameters)
    row = await _persist_outbound(
        db,
        response=response,
        phone=phone,
        body=rendered_body,
        template_name=body.template_name,
        customer_id=body.customer_id,
        lead_id=None,
        actor_id=current_user.id,
    )
    await db.commit()
    return SendResult(message_id=row.id, wa_message_id=row.wa_message_id, status=row.status)


# ── Thread listing ──────────────────────────────────────────────────────────


class ThreadMessage(BaseModel):
    id: int
    direction: str
    body: str
    status: str
    template_name: str | None
    created_at: str


@router.get("/threads/{phone}", response_model=list[ThreadMessage])
async def list_thread(
    phone: str,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.SALES_REP, UserRole.OPERATIONS))],
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[ThreadMessage]:
    _require_flag()
    try:
        normalized = normalize_phone(phone)
    except WhatsAppError as exc:
        raise HTTPException(400, str(exc)) from exc

    stmt = (
        select(WhatsAppMessage)
        .where(WhatsAppMessage.phone_number == normalized)
        .order_by(WhatsAppMessage.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        ThreadMessage(
            id=row.id,
            direction=row.direction,
            body=row.body,
            status=row.status,
            template_name=row.template_name,
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]
