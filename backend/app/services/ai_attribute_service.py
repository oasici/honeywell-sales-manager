"""AI attribute service.

Plan adoption — Phase 2 / Sprint 8. Persists admin-defined AI-populated
fields. Generation uses the existing summary_service prompt machinery
+ the project's Claude client. When ANTHROPIC_API_KEY is unset the
generator returns a deterministic placeholder so the rest of the
pipeline stays exercised in CI / offline.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import CircuitOpenError
from app.core.claude_client import claude_messages_create
from app.core.config import settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.ai_attribute import (
    AI_ATTR_DATA_TYPES,
    AI_ATTR_ENTITIES,
    AiAttributeDefinition,
    AiAttributeValue,
)
from app.models.user import User

logger = logging.getLogger(__name__)


def _def_dict(d: AiAttributeDefinition) -> dict[str, Any]:
    return {
        "id": d.id,
        "tenant_id": d.tenant_id,
        "entity_type": d.entity_type,
        "key": d.key,
        "label": d.label,
        "description": d.description,
        "data_type": d.data_type,
        "prompt_template": d.prompt_template,
        "is_active": bool(d.is_active),
        "refresh_hours": d.refresh_hours,
        "created_by": d.created_by,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


def _value_dict(v: AiAttributeValue) -> dict[str, Any]:
    payload = (
        v.value_text
        if v.value_text is not None
        else v.value_number
        if v.value_number is not None
        else v.value_bool
        if v.value_bool is not None
        else (json.loads(v.value_list_json) if v.value_list_json else None)
    )
    return {
        "id": v.id,
        "definition_id": v.definition_id,
        "entity_type": v.entity_type,
        "entity_id": v.entity_id,
        "value": payload,
        "confidence": v.confidence,
        "model_name": v.model_name,
        "trace_id": v.trace_id,
        "generated_at": v.generated_at.isoformat() if v.generated_at else None,
    }


# ── Definition CRUD ──

async def list_definitions(
    db: AsyncSession,
    current_user: User,
    entity_type: str | None = None,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    stmt = select(AiAttributeDefinition).where(
        (AiAttributeDefinition.tenant_id == current_user.tenant_id)
        | (AiAttributeDefinition.tenant_id.is_(None))
    )
    if entity_type:
        stmt = stmt.where(AiAttributeDefinition.entity_type == entity_type)
    if active_only:
        stmt = stmt.where(AiAttributeDefinition.is_active.is_(True))
    rows = (await db.execute(stmt.order_by(AiAttributeDefinition.label.asc()))).scalars().all()
    return [_def_dict(r) for r in rows]


async def create_definition(
    db: AsyncSession,
    current_user: User,
    *,
    entity_type: str,
    key: str,
    label: str,
    description: str | None,
    data_type: str,
    prompt_template: str,
    refresh_hours: int = 24,
) -> dict[str, Any]:
    if entity_type not in AI_ATTR_ENTITIES:
        raise BadRequestException(f"Geçersiz entity_type: {entity_type}")
    if data_type not in AI_ATTR_DATA_TYPES:
        raise BadRequestException(f"Geçersiz data_type: {data_type}")

    definition = AiAttributeDefinition(
        tenant_id=current_user.tenant_id,
        entity_type=entity_type,
        key=key,
        label=label,
        description=description,
        data_type=data_type,
        prompt_template=prompt_template,
        refresh_hours=max(1, min(refresh_hours, 24 * 30)),
        created_by=current_user.id,
    )
    db.add(definition)
    await db.flush()
    return _def_dict(definition)


async def update_definition(
    db: AsyncSession,
    current_user: User,
    definition_id: int,
    **fields: Any,
) -> dict[str, Any]:
    definition = await _load_definition(db, definition_id, current_user)

    if "label" in fields and fields["label"]:
        definition.label = fields["label"]
    if "description" in fields:
        definition.description = fields["description"]
    if "prompt_template" in fields and fields["prompt_template"]:
        definition.prompt_template = fields["prompt_template"]
    if "is_active" in fields and fields["is_active"] is not None:
        definition.is_active = bool(fields["is_active"])
    if "refresh_hours" in fields and fields["refresh_hours"]:
        definition.refresh_hours = max(1, min(int(fields["refresh_hours"]), 24 * 30))

    await db.flush()
    return _def_dict(definition)


async def _load_definition(
    db: AsyncSession, definition_id: int, current_user: User
) -> AiAttributeDefinition:
    definition = (
        await db.execute(
            select(AiAttributeDefinition).where(
                and_(
                    AiAttributeDefinition.id == definition_id,
                    (AiAttributeDefinition.tenant_id == current_user.tenant_id)
                    | (AiAttributeDefinition.tenant_id.is_(None)),
                )
            )
        )
    ).scalar_one_or_none()
    if definition is None:
        raise NotFoundException("Tanim bulunamadi")
    return definition


# ── Value CRUD ──

async def list_values(
    db: AsyncSession,
    current_user: User,
    *,
    entity_type: str,
    entity_id: int,
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(AiAttributeValue).where(
                and_(
                    AiAttributeValue.entity_type == entity_type,
                    AiAttributeValue.entity_id == entity_id,
                    (AiAttributeValue.tenant_id == current_user.tenant_id)
                    | (AiAttributeValue.tenant_id.is_(None)),
                )
            )
        )
    ).scalars().all()
    return [_value_dict(r) for r in rows]


async def generate_value(
    db: AsyncSession,
    current_user: User,
    *,
    definition_id: int,
    entity_id: int,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the LLM (or the offline placeholder) and persist the result."""
    definition = await _load_definition(db, definition_id, current_user)

    raw_text = await _run_generation(definition, entity_id, context or {})
    value_text, value_number, value_bool, value_list_json = _coerce_to_typed(
        definition.data_type, raw_text
    )

    existing = (
        await db.execute(
            select(AiAttributeValue).where(
                and_(
                    AiAttributeValue.definition_id == definition.id,
                    AiAttributeValue.entity_type == definition.entity_type,
                    AiAttributeValue.entity_id == entity_id,
                )
            )
        )
    ).scalar_one_or_none()

    trace_id = secrets.token_hex(8)
    if existing is None:
        existing = AiAttributeValue(
            tenant_id=current_user.tenant_id,
            definition_id=definition.id,
            entity_type=definition.entity_type,
            entity_id=entity_id,
            value_text=value_text,
            value_number=value_number,
            value_bool=value_bool,
            value_list_json=value_list_json,
            confidence=0.6 if settings.ANTHROPIC_API_KEY else 0.0,
            model_name="claude" if settings.ANTHROPIC_API_KEY else "offline",
            trace_id=trace_id,
            generated_at=datetime.now(timezone.utc),
        )
        db.add(existing)
    else:
        existing.value_text = value_text
        existing.value_number = value_number
        existing.value_bool = value_bool
        existing.value_list_json = value_list_json
        existing.confidence = 0.6 if settings.ANTHROPIC_API_KEY else 0.0
        existing.model_name = "claude" if settings.ANTHROPIC_API_KEY else "offline"
        existing.trace_id = trace_id
        existing.generated_at = datetime.now(timezone.utc)

    await db.flush()
    return _value_dict(existing)


async def _run_generation(
    definition: AiAttributeDefinition,
    entity_id: int,
    context: dict[str, Any],
) -> str:
    """Hand the prompt to Claude. Falls back to a placeholder when the
    API key is unset (development / CI / offline)."""
    rendered_prompt = definition.prompt_template
    rendered_prompt = rendered_prompt.replace("{{entity_id}}", str(entity_id))
    if context:
        rendered_prompt += "\n\nKullanılabilir bağlam:\n" + json.dumps(
            context, ensure_ascii=False
        )

    if not settings.ANTHROPIC_API_KEY:
        return f"[offline placeholder] {definition.label} #{entity_id}"

    try:
        result = await claude_messages_create(
            messages=[{"role": "user", "content": rendered_prompt}],
            max_tokens=400,
            temperature=0.2,
        )
        text_blocks = result.get("content") or []
        text = ""
        for block in text_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")
        return text.strip() or f"[empty response] {definition.label}"
    except CircuitOpenError:
        logger.warning("AI attribute circuit open — returning placeholder")
        return f"[circuit open] {definition.label} #{entity_id}"
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("AI attribute generation failed: %s", exc)
        return f"[error] {definition.label} #{entity_id}"


def _coerce_to_typed(
    data_type: str, text: str
) -> tuple[str | None, float | None, bool | None, str | None]:
    if data_type == "number":
        try:
            return None, float(text.strip().replace(",", ".")), None, None
        except (TypeError, ValueError):
            return text, None, None, None
    if data_type == "boolean":
        lowered = text.strip().lower()
        if lowered in ("true", "1", "yes", "evet", "on"):
            return None, None, True, None
        if lowered in ("false", "0", "no", "hayir", "off"):
            return None, None, False, None
        return text, None, None, None
    if data_type == "list_text":
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return None, None, None, json.dumps(parsed, ensure_ascii=False)
        except (TypeError, ValueError):
            pass
        items = [s.strip() for s in text.split(",") if s.strip()]
        return None, None, None, json.dumps(items, ensure_ascii=False)
    return text, None, None, None
