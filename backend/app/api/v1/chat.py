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
        "trigger_keyword": r.trigger_keyword,
        "response_text": r.response_text,
        "is_active": r.is_active,
        "priority": r.priority,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ── Session Endpoints ──


@router.post("/sessions", status_code=201)
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


@router.get("/sessions/")
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
    result = await db.execute(query)
    sessions = result.scalars().all()
    return {"sessions": [_serialize_session(s) for s in sessions]}


@router.patch("/sessions/{session_id}/assign")
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
    if session.status == "closed":
        raise BadRequestException("Cannot assign a closed session")

    session.assigned_agent_id = current_user.id
    session.status = "assigned"
    await db.commit()
    await db.refresh(session)
    return _serialize_session(session)


@router.patch("/sessions/{session_id}/close")
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
    if session.status == "closed":
        raise BadRequestException("Session is already closed")

    session.status = "closed"
    await db.commit()
    await db.refresh(session)
    return _serialize_session(session)


# ── Message Endpoints ──


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: int,
    _: None = Depends(_require_live_chat),
    current_user: User = Depends(require_role(*AGENT_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve message history for a session."""
    session_result = await db.execute(
        select(ChatSession.id).where(ChatSession.id == session_id)
    )
    if session_result.scalar_one_or_none() is None:
        raise NotFoundException("Chat session not found")

    messages_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    messages = messages_result.scalars().all()
    return {"messages": [_serialize_message(m) for m in messages]}


@router.post("/sessions/{session_id}/messages", status_code=201)
async def send_message(
    session_id: int,
    body: MessageCreate,
    _: None = Depends(_require_live_chat),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to a session. Auto-response fires for visitor messages."""
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

    message = ChatMessage(
        session_id=session_id,
        sender_type=body.sender_type,
        sender_id=body.sender_id,
        content=body.content,
        message_type=body.message_type,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    bot_message: ChatMessage | None = None
    if body.sender_type == "visitor":
        bot_message = await _try_auto_response(session_id, body.content, db)

    response: dict = {"message": _serialize_message(message)}
    if bot_message is not None:
        response["auto_response"] = _serialize_message(bot_message)
    return response


async def _try_auto_response(
    session_id: int, content: str, db: AsyncSession
) -> ChatMessage | None:
    """Check active auto-response rules and fire the highest-priority match."""
    rules_result = await db.execute(
        select(AutoResponseRule)
        .where(AutoResponseRule.is_active.is_(True))
        .order_by(AutoResponseRule.priority.desc())
    )
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
    )
    db.add(bot_msg)
    await db.commit()
    await db.refresh(bot_msg)
    return bot_msg


# ── Auto-Response Rule Endpoints (admin only) ──


@router.get("/auto-response-rules/")
async def list_auto_rules(
    _: None = Depends(_require_live_chat),
    current_user: User = Depends(require_role(*ADMIN_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """List all auto-response rules. Admin-only."""
    result = await db.execute(
        select(AutoResponseRule).order_by(AutoResponseRule.priority.desc())
    )
    rules = result.scalars().all()
    return {"rules": [_serialize_rule(r) for r in rules]}


@router.post("/auto-response-rules/", status_code=201)
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
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _serialize_rule(rule)


@router.patch("/auto-response-rules/{rule_id}")
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

    await db.delete(rule)
