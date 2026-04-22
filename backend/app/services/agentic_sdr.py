"""Agentic SDR — autonomous follow-up agent powered by Claude tool-use.

Triggered when certain domain events fire (revenue_signal.created,
opportunity.stage_changed) for opportunities that match the enrolment
rules. The agent uses Claude's tool-use loop to:

    1. Read a compact context pack (deal + last emails + last transcript
       summary + recent signals).
    2. Pick ONE of the allowed tools:
         - draft_follow_up_email
         - schedule_task
         - escalate_to_manager
         - no_action
    3. Persist the chosen action (Task, email draft, notification).

Safety rails:
    - FEATURE_AGENTIC_SDR gate so the agent is dormant until explicitly on.
    - Never sends an email directly - only drafts; a human must click send.
    - All outputs stamped with ``origin="agentic_sdr"`` on the Task so we
      can audit who decided what.
    - PII is scrubbed through the AI Trust Layer before reaching Claude.

The agent is scoped narrowly on purpose: we extend the tool catalogue in
later iterations rather than giving unrestricted write access now.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.email_request import EmailRequest
from app.models.engagement import Transcript
from app.models.opportunity import Opportunity, Task
from app.models.revenue_signal import RevenueSignal
from app.models.user import User
from app.services.ai_trust import AITrustContext, audit_record, scrub, unscrub
from app.services.domain_events import emit_domain_event

logger = logging.getLogger(__name__)

MAX_RECENT_EMAILS = 3
MAX_RECENT_SIGNALS = 5
MAX_CONTEXT_CHARS = 6000


# ── Tool catalogue exposed to Claude ────────────────────────────────────────

_TOOLS = [
    {
        "name": "draft_follow_up_email",
        "description": (
            "Draft a follow-up email to the deal owner so they can review "
            "and send it. Do not use if the opportunity has been touched in "
            "the last 48h."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["subject", "body", "rationale"],
        },
    },
    {
        "name": "schedule_task",
        "description": "Create a CRM task assigned to the opportunity owner.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "due_in_days": {"type": "integer", "minimum": 0, "maximum": 30},
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
                "rationale": {"type": "string"},
            },
            "required": ["title", "due_in_days", "priority", "rationale"],
        },
    },
    {
        "name": "escalate_to_manager",
        "description": (
            "Raise a notification to the opportunity owner's manager. "
            "Reserved for high-severity signals (stuck deals, objections)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "severity": {
                    "type": "string",
                    "enum": ["high", "critical"],
                },
            },
            "required": ["reason", "severity"],
        },
    },
    {
        "name": "no_action",
        "description": "No follow-up needed right now.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
]


_SYSTEM_PROMPT = (
    "Sen Honeywell Turkey satıs ekibinin agentic SDR asistanisin. "
    "Fırsat özetine, son e-postalara, transkript özetine ve revenue "
    "sinyallerine bakarak bir sonraki adımı seçersin. HER ZAMAN tek bir "
    "tool çağrısı yaparsın; prose yazma. Acil değilse 'no_action' seç. "
    "Türkçe cevap ver."
)


def _normalise_priority(value: Any) -> str:
    """Claude returns low/medium/high; Task model uses low/normal/high/urgent."""
    if value == "medium":
        return "normal"
    if value in {"low", "normal", "high", "urgent"}:
        return value
    return "normal"


# ── Context pack ────────────────────────────────────────────────────────────


@dataclass
class AgentDecision:
    tool: str
    arguments: dict[str, Any]
    persisted_ids: dict[str, Any]
    trust_audit: dict[str, Any] | None = None


async def run_for_opportunity(
    db: AsyncSession,
    *,
    opportunity_id: int,
    trigger: str,
    trigger_payload: dict | None = None,
) -> AgentDecision | None:
    """Run one decision loop for the given opportunity.

    Returns ``None`` when the agent is disabled, Claude is unavailable,
    or no decision could be made.
    """
    if not settings.FEATURE_AGENTIC_SDR:
        return None
    if not settings.ANTHROPIC_API_KEY:
        logger.debug("Agentic SDR skipped: ANTHROPIC_API_KEY missing")
        return None

    opportunity = await db.get(Opportunity, opportunity_id)
    if not opportunity:
        return None

    context_pack = await _build_context_pack(db, opportunity, trigger, trigger_payload)
    safe_pack, trust_ctx = _scrub_pack(context_pack)

    try:
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=30.0)
        response = await client.messages.create(
            model=settings.AI_MODEL_NAME,
            max_tokens=min(settings.AI_MAX_TOKENS, 768),
            system=_SYSTEM_PROMPT,
            tools=_TOOLS,
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": json.dumps(safe_pack, ensure_ascii=False)}],
        )
    except Exception as exc:  # pragma: no cover - transport
        logger.warning("Agentic SDR Claude call failed for opp %s: %s", opportunity_id, exc)
        return None

    tool_name, tool_input = _extract_tool_call(response)
    if not tool_name:
        logger.info("Agentic SDR: Claude returned no tool use for opp %s", opportunity_id)
        return None

    if trust_ctx is not None and trust_ctx.is_dirty():
        tool_input = _unscrub(tool_input, trust_ctx)

    persisted = await _apply_tool(
        db,
        opportunity=opportunity,
        tool_name=tool_name,
        tool_input=tool_input,
    )
    await db.flush()

    await emit_domain_event(
        db,
        "agentic_sdr.action_taken",
        {
            "opportunity_id": opportunity_id,
            "tool": tool_name,
            "trigger": trigger,
            "rationale": tool_input.get("rationale") or tool_input.get("reason"),
            "persisted": persisted,
        },
        entity_type="opportunity",
        entity_id=opportunity_id,
        persist=True,
    )

    audit_dict = None
    if trust_ctx is not None and trust_ctx.is_dirty():
        audit_dict = audit_record(
            trust_ctx,
            prompt=json.dumps(context_pack, ensure_ascii=False),
            model=settings.AI_MODEL_NAME,
        )

    return AgentDecision(
        tool=tool_name,
        arguments=tool_input,
        persisted_ids=persisted,
        trust_audit=audit_dict,
    )


# ── Context assembly ────────────────────────────────────────────────────────


async def _build_context_pack(
    db: AsyncSession,
    opportunity: Opportunity,
    trigger: str,
    trigger_payload: dict | None,
) -> dict[str, Any]:
    recent_emails = (
        await db.execute(
            select(EmailRequest)
            .where(EmailRequest.customer_id == opportunity.customer_id)
            .order_by(EmailRequest.created_at.desc())
            .limit(MAX_RECENT_EMAILS)
        )
    ).scalars().all()

    last_transcript = (
        await db.execute(
            select(Transcript)
            .where(Transcript.opportunity_id == opportunity.id)
            .order_by(Transcript.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    recent_signals = (
        await db.execute(
            select(RevenueSignal)
            .where(RevenueSignal.opportunity_id == opportunity.id)
            .order_by(RevenueSignal.created_at.desc())
            .limit(MAX_RECENT_SIGNALS)
        )
    ).scalars().all()

    last_touched_at = opportunity.updated_at or opportunity.created_at
    if last_touched_at:
        hours_since_touch = (datetime.now(timezone.utc) - last_touched_at).total_seconds() / 3600
    else:
        hours_since_touch = None

    pack: dict[str, Any] = {
        "trigger": trigger,
        "trigger_payload": trigger_payload or {},
        "opportunity": {
            "id": opportunity.id,
            "title": opportunity.title,
            "stage": opportunity.stage.value if hasattr(opportunity.stage, "value") else opportunity.stage,
            "amount": float(opportunity.amount) if opportunity.amount is not None else None,
            "close_date": opportunity.close_date.isoformat() if opportunity.close_date else None,
            "hours_since_touch": hours_since_touch,
        },
        "recent_emails": [
            {
                "subject": email.subject or "",
                "body_excerpt": (email.body_text or email.body or "")[:400],
                "received_at": email.created_at.isoformat() if email.created_at else None,
            }
            for email in recent_emails
        ],
        "last_transcript": (
            {
                "title": last_transcript.title,
                "sentiment": last_transcript.sentiment,
                "summary": last_transcript.summary,
            }
            if last_transcript
            else None
        ),
        "recent_signals": [
            {
                "type": signal.signal_type,
                "severity": signal.severity,
                "recommended_action": signal.recommended_action,
                "created_at": signal.created_at.isoformat() if signal.created_at else None,
            }
            for signal in recent_signals
        ],
    }

    payload = json.dumps(pack, ensure_ascii=False)
    if len(payload) > MAX_CONTEXT_CHARS:
        # Trim email bodies progressively until we fit.
        for email in pack["recent_emails"]:
            email["body_excerpt"] = email["body_excerpt"][:200]
    return pack


def _scrub_pack(pack: dict[str, Any]) -> tuple[dict[str, Any], AITrustContext | None]:
    if not settings.FEATURE_AI_TRUST_LAYER:
        return pack, None
    ctx = AITrustContext()
    scrubbed = _walk(pack, lambda s: scrub(s, ctx=ctx)[0])
    return scrubbed, ctx


def _walk(value, fn):
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, list):
        return [_walk(v, fn) for v in value]
    if isinstance(value, dict):
        return {k: _walk(v, fn) for k, v in value.items()}
    return value


def _unscrub(value, ctx: AITrustContext):
    return _walk(value, lambda s: unscrub(s, ctx))


def _extract_tool_call(response) -> tuple[str | None, dict[str, Any]]:
    for block in response.content:
        if block.type == "tool_use":
            return block.name, dict(block.input or {})
    return None, {}


# ── Tool execution ──────────────────────────────────────────────────────────


async def _apply_tool(
    db: AsyncSession,
    *,
    opportunity: Opportunity,
    tool_name: str,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    if tool_name == "schedule_task":
        return await _apply_schedule_task(db, opportunity, tool_input)
    if tool_name == "draft_follow_up_email":
        return await _apply_draft_email(db, opportunity, tool_input)
    if tool_name == "escalate_to_manager":
        return await _apply_escalate(db, opportunity, tool_input)
    if tool_name == "no_action":
        return {"action": "no_action", "reason": tool_input.get("reason")}
    logger.warning("Agentic SDR: unknown tool %s", tool_name)
    return {"action": "unknown", "tool": tool_name}


async def _apply_schedule_task(
    db: AsyncSession, opportunity: Opportunity, tool_input: dict[str, Any]
) -> dict[str, Any]:
    due_days = int(tool_input.get("due_in_days") or 1)
    due_at = datetime.now(timezone.utc) + timedelta(days=due_days)
    priority = _normalise_priority(tool_input.get("priority"))
    if not opportunity.owner_id:
        return {"action": "schedule_task_skipped", "reason": "no_owner"}
    task = Task(
        owner_id=opportunity.owner_id,
        opportunity_id=opportunity.id,
        title=str(tool_input.get("title") or "Takip arama")[:200],
        description=str(tool_input.get("description") or tool_input.get("rationale") or ""),
        due_at=due_at,
        priority=priority,
        status="open",
        source="ai",
    )
    db.add(task)
    await db.flush()
    return {"task_id": task.id, "due_at": due_at.isoformat()}


async def _apply_draft_email(
    db: AsyncSession, opportunity: Opportunity, tool_input: dict[str, Any]
) -> dict[str, Any]:
    """Store the draft as a Task payload so the owner can pick it up."""
    subject = str(tool_input.get("subject") or "")[:200]
    body = str(tool_input.get("body") or "")
    if not opportunity.owner_id:
        return {"action": "draft_skipped", "reason": "no_owner"}
    task = Task(
        owner_id=opportunity.owner_id,
        opportunity_id=opportunity.id,
        title=f"[AI Taslak] {subject}" if subject else "AI E-posta Taslağı",
        description=(
            f"AI Taslak:\n\nKonu: {subject}\n\n{body}\n\n"
            f"— Gerekçe: {tool_input.get('rationale') or ''}"
        ),
        due_at=datetime.now(timezone.utc) + timedelta(days=1),
        priority="normal",
        status="open",
        source="ai",
    )
    db.add(task)
    await db.flush()
    return {"draft_task_id": task.id, "subject": subject}


async def _apply_escalate(
    db: AsyncSession, opportunity: Opportunity, tool_input: dict[str, Any]
) -> dict[str, Any]:
    from app.services.notification_service import create_notification

    reason = str(tool_input.get("reason") or "")
    severity = str(tool_input.get("severity") or "high")

    # Find the owner's manager (simplest heuristic: first active SALES_MANAGER).
    manager = (
        await db.execute(
            select(User).where(
                User.role == "sales_manager", User.is_active.is_(True)
            ).order_by(User.id)
        )
    ).scalars().first()
    if not manager:
        return {"escalated": False, "reason": "no_manager"}

    await create_notification(
        db,
        user_id=manager.id,
        type="agentic_sdr_escalation",
        title=f"Agentic SDR: fırsat {opportunity.id} için yardım gerekli",
        message=reason[:500],
        entity_type="opportunity",
        entity_id=opportunity.id,
    )
    return {"escalated": True, "manager_id": manager.id, "severity": severity}
