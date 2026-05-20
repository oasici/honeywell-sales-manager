"""Live Chat API — visitor-agent messaging with auto-response rules."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.chat import AutoResponseRule, ChatMessage, ChatSession
from app.models.enums import UserRole
from app.models.user import User
from app.services.tenant_context import assert_same_tenant, scoped_for_user
from app.schemas.common import ItemsResponse, PaginatedResponse
from app.schemas.chat import (
    AutoResponseRuleResponse,
    ChatMessageSendResponse,
    ChatSessionResponse,
)

router = APIRouter(prefix="/chat", tags=["Live Chat"])

ADMIN_ROLES = (UserRole.SALES_MANAGER, UserRole.OPERATIONS)
AGENT_ROLES = (UserRole.SALES_MANAGER, UserRole.OPERATIONS, UserRole.SALES_REP)
VALID_SENDER_TYPES = {"visitor", "agent", "bot"}
VALID_MESSAGE_TYPES = {"text", "image", "file"}


def _require_live_chat() -> None:
    """Dependency: reject if FEATURE_LIVE_CHAT is off."""
    if not settings.FEATURE_LIVE_CHAT:
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic Schemas ──


class SessionCreate(BaseModel):
    visitor_id: str = Field(min_length=1, max_length=64)
    metadata_json: Optional[str] = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    sender_type: str = Field(max_length=20)
    sender_id: Optional[str] = Field(default=None, max_length=100)
    message_type: str = Field(default="text", max_length=20)


class AutoRuleCreate(BaseModel):
    trigger_keyword: str = Field(min_length=1, max_length=200)
    response_text: str = Field(min_length=1)
    is_active: bool = True
    priority: int = 0


class AutoRuleUpdate(BaseModel):
    trigger_keyword: Optional[str] = Field(default=None, min_length=1, max_length=200)
    response_text: Optional[str] = Field(default=None, min_length=1)
    is_active: Optional[bool] = None
    priority: Optional[int] = None


# ── Serializers ──


def _serialize_session(s: ChatSession) -> dict:
    return {
        "id": s.id,
        # Round-4 R4-DTO — round-trip tenant_id (R4-TEN-19).
        "tenant_id": getattr(s, "tenant_id", None),
        "visitor_id": s.visitor_id,
        "assigned_agent_id": s.assigned_agent_id,
        "status": s.status,
        "metadata_json": s.metadata_json,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _serialize_message(m: ChatMessage) -> dict:
    return {
        "id": m.id,
        # Round-4 R4-DTO — round-trip tenant_id (R4-TEN-19).
        "tenant_id": getattr(m, "tenant_id", None),
        "session_id": m.session_id,
        "sender_type": m.sender_type,
        "sender_id": m.sender_id,
        "content": m.content,
        "message_type": m.message_type,
        "is_read": m.is_read,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _serialize_rule(r: AutoResponseRule) -> dict:
    return {
        "id": r.id,
        # Round-4 R4-DTO — round-trip tenant_id (R4-TEN-19).
        "tenant_id": getattr(r, "tenant_id", None),
        "trigger_keyword": r.trigger_keyword,
        "response_text": r.response_text,
        "is_active": r.is_active,
        "priority": r.priority,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ── Session Endpoints ──


@router.post("/sessions", status_code=201, response_model=ChatSessionResponse)
async def create_session(
    body: SessionCreate,
    _: None = Depends(_require_live_chat),
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat session. No authentication required for visitors."""
    session = ChatSession(
        visitor_id=body.visitor_id,
        metadata_json=body.metadata_json,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _serialize_session(session)


@router.get("/sessions/", response_model=ItemsResponse)
async def list_sessions(
    status: Optional[str] = None,
    _: None = Depends(_require_live_chat),
    current_user: User = Depends(require_role(*AGENT_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """List chat sessions. Agent-only. Defaults to open sessions."""
    query = select(ChatSession).order_by(ChatSession.created_at.desc())
    filter_status = status or "open"
    query = query.where(ChatSession.status == filter_status)
    # Round-4 R4-TEN-19 — scope sessions to caller tenant.
    query = scoped_for_user(query, current_user, column=ChatSession.tenant_id)
    result = await db.execute(query)
    sessions = result.scalars().all()
    # R6-PAGE-1 — canonical envelope. Pre-R6 returned ``{sessions: [...]}``;
    # SPA list components had to special-case the shape.
    items = [_serialize_session(s) for s in sessions]
    total = len(items)
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
    }


@router.patch("/sessions/{session_id}/assign", response_model=ChatSessionResponse)
async def assign_session(
    session_id: int,
    _: None = Depends(_require_live_chat),
    current_user: User = Depends(require_role(*AGENT_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Assign session to the current user."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundException("Chat session not found")
    # Round-4 R4-TEN-19 — block cross-tenant assignment. Sessions started
    # by a visitor before any agent claim have tenant_id=None, so the
    # check is a no-op until the first claim stamps the tenant below.
    assert_same_tenant(session, current_user, exception_cls=NotFoundException)
    if session.status == "closed":
        raise BadRequestException("Cannot assign a closed session")

    session.assigned_agent_id = current_user.id
    session.status = "assigned"
    # Round-4 R4-TEN-19 — stamp tenant from the claiming agent so downstream
    # listing / messaging endpoints can scope on it.
    if getattr(session, "tenant_id", None) is None:
        session.tenant_id = getattr(current_user, "tenant_id", None)
    await db.commit()
    await db.refresh(session)
    return _serialize_session(session)


@router.patch("/sessions/{session_id}/close", response_model=ChatSessionResponse)
async def close_session(
    session_id: int,
    _: None = Depends(_require_live_chat),
    current_user: User = Depends(require_role(*AGENT_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Close a chat session."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundException("Chat session not found")
    # Round-4 R4-TEN-19 — block cross-tenant close.
    assert_same_tenant(session, current_user, exception_cls=NotFoundException)
    if session.status == "closed":
        raise BadRequestException("Session is already closed")

    session.status = "closed"
    await db.commit()
    await db.refresh(session)
    return _serialize_session(session)


# ── Message Endpoints ──


@router.get("/sessions/{session_id}/messages", response_model=ItemsResponse)
async def get_messages(
    session_id: int,
    _: None = Depends(_require_live_chat),
    current_user: User = Depends(require_role(*AGENT_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve message history for a session."""
    # Round-4 R4-TEN-19 — load the full session row so we can tenant-check
    # before exposing any messages.
    session_result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        raise NotFoundException("Chat session not found")
    assert_same_tenant(session, current_user, exception_cls=NotFoundException)

    msg_stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    # Defense in depth: scope by message tenant too in case legacy rows
    # exist with a different tenant_id than the session.
    msg_stmt = scoped_for_user(msg_stmt, current_user, column=ChatMessage.tenant_id)
    messages_result = await db.execute(msg_stmt)
    messages = messages_result.scalars().all()
    # R6-PAGE-1 — canonical envelope.
    items = [_serialize_message(m) for m in messages]
    total = len(items)
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
    }


@router.post("/sessions/{session_id}/messages", status_code=201, response_model=ChatMessageSendResponse)
async def send_message(
    session_id: int,
    body: MessageCreate,
    _: None = Depends(_require_live_chat),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to a session. Auto-response fires for visitor messages.

    R7-TEN-4 — public visitor endpoint; ``sender_type`` ∈ {agent, bot}
    is reserved for authenticated agent flows. Pre-fix, an anonymous
    caller could spoof ``sender_type=agent, sender_id=42`` and the
    transcript rendered as if agent #42 sent the message.
    """
    # R7-TEN-4 — block agent/bot impersonation on the public endpoint.
    # Authenticated agent message paths live elsewhere (assigned-agent
    # flow); the visitor endpoint must only accept ``visitor`` messages.
    if body.sender_type != "visitor":
        raise BadRequestException(
            "Only visitor messages may be posted to the public chat endpoint"
        )
    if body.sender_type not in VALID_SENDER_TYPES:
        raise BadRequestException(
            f"Invalid sender_type. Must be one of: {', '.join(sorted(VALID_SENDER_TYPES))}"
        )
    if body.message_type not in VALID_MESSAGE_TYPES:
        raise BadRequestException(
            f"Invalid message_type. Must be one of: {', '.join(sorted(VALID_MESSAGE_TYPES))}"
        )

    session_result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        raise NotFoundException("Chat session not found")
    if session.status == "closed":
        raise BadRequestException("Cannot send message to a closed session")

    # Round-4 R4-TEN-19 — chain message tenant from the parent session so
    # downstream listing endpoints stay tenant-scoped.
    session_tenant_id = getattr(session, "tenant_id", None)
    message = ChatMessage(
        session_id=session_id,
        sender_type=body.sender_type,
        sender_id=body.sender_id,
        content=body.content,
        message_type=body.message_type,
        tenant_id=session_tenant_id,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    bot_message: ChatMessage | None = None
    if body.sender_type == "visitor":
        bot_message = await _try_auto_response(
            session_id, body.content, db, tenant_id=session_tenant_id
        )

    response: dict = {"message": _serialize_message(message)}
    if bot_message is not None:
        response["auto_response"] = _serialize_message(bot_message)
    return response


async def _try_auto_response(
    session_id: int,
    content: str,
    db: AsyncSession,
    *,
    tenant_id: int | None = None,
) -> ChatMessage | None:
    """Check active auto-response rules and fire the highest-priority match.

    Round-4 R4-TEN-19 — scope the rule lookup by ``tenant_id`` (chained
    from the parent session). When the session has no tenant (single-tenant
    deployments), behave as before and consider all active rules.
    """
    rules_stmt = (
        select(AutoResponseRule)
        .where(AutoResponseRule.is_active.is_(True))
        .order_by(AutoResponseRule.priority.desc())
    )
    if tenant_id is not None:
        rules_stmt = rules_stmt.where(AutoResponseRule.tenant_id == tenant_id)
    rules_result = await db.execute(rules_stmt)
    rules = rules_result.scalars().all()

    content_lower = content.lower()
    matched_rule: AutoResponseRule | None = None
    for rule in rules:
        if rule.trigger_keyword.lower() in content_lower:
            matched_rule = rule
            break

    if matched_rule is None:
        return None

    bot_msg = ChatMessage(
        session_id=session_id,
        sender_type="bot",
        content=matched_rule.response_text,
        message_type="text",
        # Round-4 R4-TEN-19 — propagate tenant from the session.
        tenant_id=tenant_id,
    )
    db.add(bot_msg)
    await db.commit()
    await db.refresh(bot_msg)
    return bot_msg


# ── Auto-Response Rule Endpoints (admin only) ──


@router.get("/auto-response-rules/", response_model=PaginatedResponse[dict])
async def list_auto_rules(
    _: None = Depends(_require_live_chat),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """List all auto-response rules. Admin-only."""
    # Round-4 R4-TEN-19 — scope rules to caller tenant.
    rule_stmt = scoped_for_user(
        select(AutoResponseRule).order_by(AutoResponseRule.priority.desc()),
        current_user,
        column=AutoResponseRule.tenant_id,
    )
    result = await db.execute(rule_stmt)
    rules = result.scalars().all()
    # R6-PAGE-1 — canonical envelope.
    items = [_serialize_rule(r) for r in rules]
    total = len(items)
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
    }


@router.post("/auto-response-rules/", status_code=201, response_model=AutoResponseRuleResponse)
async def create_auto_rule(
    body: AutoRuleCreate,
    _: None = Depends(_require_live_chat),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Create an auto-response rule. Admin-only."""
    rule = AutoResponseRule(
        trigger_keyword=body.trigger_keyword,
        response_text=body.response_text,
        is_active=body.is_active,
        priority=body.priority,
        created_by=current_user.id,
        # Round-4 R4-TEN-19 — stamp tenant on create.
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _serialize_rule(rule)


@router.patch("/auto-response-rules/{rule_id}", response_model=AutoResponseRuleResponse)
async def update_auto_rule(
    rule_id: int,
    body: AutoRuleUpdate,
    _: None = Depends(_require_live_chat),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Update an auto-response rule. Admin-only."""
    result = await db.execute(
        select(AutoResponseRule).where(AutoResponseRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise NotFoundException("Auto-response rule not found")
    # Round-4 R4-TEN-19 — block cross-tenant rule update.
    assert_same_tenant(rule, current_user, exception_cls=NotFoundException)

    for key, value in body.model_dump(exclude_none=True).items():
        setattr(rule, key, value)

    await db.commit()
    await db.refresh(rule)
    return _serialize_rule(rule)


@router.delete("/auto-response-rules/{rule_id}", status_code=204)
async def delete_auto_rule(
    rule_id: int,
    _: None = Depends(_require_live_chat),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Delete an auto-response rule. Admin-only."""
    result = await db.execute(
        select(AutoResponseRule).where(AutoResponseRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise NotFoundException("Auto-response rule not found")
    # Round-4 R4-TEN-19 — block cross-tenant rule delete.
    assert_same_tenant(rule, current_user, exception_cls=NotFoundException)

    await db.delete(rule)
