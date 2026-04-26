"""AI Action Generator — context-aware action recommendations using Claude or rule fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.core.circuit_breaker import CircuitOpenError
from app.core.claude_client import claude_messages_create
from app.core.config import settings
from app.models.activity_log import ActivityLog
from app.models.opportunity import Opportunity, Task
from app.models.revenue_signal import RevenueSignal
from app.services.dedupe_service import upsert_task

logger = logging.getLogger(__name__)

CONTEXT_MAX_CHARS = 6000
SIGNAL_LOOKBACK_COUNT = 30
ACTIVITY_LOOKBACK_COUNT = 20
DUE_OFFSET_DAYS = 3


async def generate_actions(
    db: AsyncSession,
    opportunity_id: int,
    max_actions: int = 5,
) -> list[dict]:
    """Generate context-aware action recommendations for an opportunity.

    1. Gather context: signals, deal health, activities, open tasks.
    2. If ANTHROPIC_API_KEY is set, use Claude tool-use for recommendations.
    3. Otherwise fall back to rule-based action generation.
    4. Create Task records for each recommended action.
    5. Return list of created actions with reasoning.
    """
    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if not opp:
        return []

    context = await _gather_context(db, opportunity_id)

    if settings.ANTHROPIC_API_KEY:
        actions = await _generate_via_claude(context, max_actions)
    else:
        actions = []

    if not actions:
        actions = _generate_via_rules(context, max_actions)

    created = []
    now = datetime.now(timezone.utc)
    for action in actions[:max_actions]:
        task = await upsert_task(
            db,
            owner_id=opp.owner_id,
            opportunity_id=opportunity_id,
            title=action["description"][:255],
            description=action.get("reasoning", ""),
            due_at=now + timedelta(days=DUE_OFFSET_DAYS),
            status="open",
            source="ai",
            priority=action.get("priority", "normal"),
            dedupe_window_days=7,
        )

        created.append({
            "task_id": task.id,
            "action_type": action.get("action_type", "general"),
            "priority": task.priority,
            "description": task.title,
            "reasoning": action.get("reasoning", ""),
        })

    return created


async def _gather_context(db: AsyncSession, opportunity_id: int) -> dict:
    """Collect all relevant data for the opportunity."""
    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()

    signals = (
        await db.execute(
            select(RevenueSignal)
            .where(RevenueSignal.opportunity_id == opportunity_id)
            .order_by(RevenueSignal.created_at.desc())
            .limit(SIGNAL_LOOKBACK_COUNT)
        )
    ).scalars().all()

    activities = (
        await db.execute(
            select(ActivityLog)
            .options(defer(ActivityLog.source_ref))
            .where(ActivityLog.opportunity_id == opportunity_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(ACTIVITY_LOOKBACK_COUNT)
        )
    ).scalars().all()

    open_tasks = (
        await db.execute(
            select(Task).where(
                and_(
                    Task.opportunity_id == opportunity_id,
                    Task.status == "open",
                )
            )
        )
    ).scalars().all()

    deal_health = None
    try:
        from app.services.deal_health_service import DealHealthService
        service = DealHealthService(db)
        deal_health = await service.compute_deal_health(opportunity_id)
    except Exception as exc:
        logger.warning("Deal health computation failed: %s", exc)

    return {
        "opportunity": opp,
        "signals": signals,
        "activities": activities,
        "open_tasks": open_tasks,
        "deal_health": deal_health,
    }


async def _generate_via_claude(context: dict, max_actions: int) -> list[dict]:
    """Use Claude tool-use to generate sales actions."""
    opp = context["opportunity"]
    if not opp:
        return []

    prompt_parts = [
        f"Firsat: {opp.title}",
        f"Asama: {opp.stage}",
        f"Tutar: {opp.amount} {opp.currency}",
        f"Durum: {opp.status}",
    ]

    if context["deal_health"]:
        dh = context["deal_health"]
        prompt_parts.append(f"Saglik Skoru: {dh.score}/100 ({dh.risk_level})")
        for ind in dh.indicators:
            prompt_parts.append(f"  - {ind.label}: {ind.score}/100 ({ind.description})")

    if context["signals"]:
        prompt_parts.append("\nSon Sinyaller:")
        for sig in context["signals"][:10]:
            prompt_parts.append(
                f"  - {sig.signal_type} (siddet: {sig.severity}, "
                f"guven: {sig.confidence})"
            )

    if context["activities"]:
        prompt_parts.append("\nSon Aktiviteler:")
        for act in context["activities"][:10]:
            prompt_parts.append(f"  - {act.activity_type}: {act.summary}")

    if context["open_tasks"]:
        prompt_parts.append(f"\nAcik Gorevler: {len(context['open_tasks'])} adet")
        for task in context["open_tasks"][:5]:
            prompt_parts.append(f"  - {task.title} ({task.priority})")

    # RAG: add similar historical deals for action context
    from app.services.vector_store import find_similar_deals

    rag_query = f"{opp.title} {opp.stage}"
    similar_deals = await find_similar_deals(rag_query, limit=5)
    if similar_deals:
        prompt_parts.append("\nBenzer Gecmis Firsatlar (referans):")
        for deal in similar_deals:
            prompt_parts.append(
                f"- {deal.get('title', '?')} "
                f"(Asama: {deal.get('stage')}, "
                f"Sonuc: {deal.get('outcome')}, "
                f"Risk: {deal.get('risk_level')})"
            )

    user_prompt = "\n".join(prompt_parts)[:CONTEXT_MAX_CHARS]

    tool_schema = {
        "name": "generate_sales_actions",
        "description": "Satis firsati icin onerilen aksiyonlari dondurur.",
        "input_schema": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action_type": {
                                "type": "string",
                                "enum": [
                                    "followup",
                                    "pricing_review",
                                    "competitor_analysis",
                                    "escalation",
                                    "status_update",
                                    "meeting",
                                    "proposal",
                                ],
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "normal", "high", "urgent"],
                            },
                            "description": {"type": "string"},
                            "reasoning": {"type": "string"},
                        },
                        "required": [
                            "action_type",
                            "priority",
                            "description",
                            "reasoning",
                        ],
                    },
                    "maxItems": max_actions,
                },
            },
            "required": ["actions"],
        },
    }

    try:
        response = await claude_messages_create(
            model=settings.AI_MODEL_NAME,
            max_tokens=settings.AI_MAX_TOKENS,
            system=(
                "Sen bir satis danismanisin. Verilen firsat verilerine gore "
                "en etkili aksiyonlari oner. Turkce yaz. Her aksiyon icin "
                "net bir aciklama ve gerekce ver."
            ),
            messages=[{"role": "user", "content": user_prompt}],
            tools=[tool_schema],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "generate_sales_actions":
                return block.input.get("actions", [])

    except CircuitOpenError as exc:
        logger.warning("Claude breaker open; falling back to rule-based actions: %s", exc)
        return []

    except Exception as exc:
        logger.error("Claude action generation failed: %s", exc)

    return []


def _generate_via_rules(context: dict, max_actions: int) -> list[dict]:
    """Rule-based fallback when Claude API is unavailable."""
    actions: list[dict] = []
    signals = context.get("signals", [])
    deal_health = context.get("deal_health")

    signal_types = {s.signal_type for s in signals}
    high_severity_types = {s.signal_type for s in signals if s.severity == "high"}

    if "no_touch" in high_severity_types:
        actions.append({
            "action_type": "followup",
            "priority": "urgent",
            "description": "Acil musteri takibi gerekli",
            "reasoning": (
                "Yuksek oncelikli temas eksikligi sinyali tespit edildi. "
                "Musteriye en kisa surede ulasilmali."
            ),
        })

    if "pricing_concern" in signal_types:
        actions.append({
            "action_type": "pricing_review",
            "priority": "high",
            "description": "Fiyat karsilastirma analizi hazirla",
            "reasoning": (
                "Fiyat endisesi sinyali mevcut. Rakip fiyatlarini "
                "ve maliyet analizini guncelle."
            ),
        })

    if "competitor" in signal_types:
        actions.append({
            "action_type": "competitor_analysis",
            "priority": "high",
            "description": "Rakip analizi raporu olustur",
            "reasoning": (
                "Rakip sinyali tespit edildi. Rakip urunleri ve "
                "avantajlarimizi karsilastiran bir rapor hazirla."
            ),
        })

    is_critical_health = deal_health and deal_health.score < 40
    if "deal_risk" in signal_types or is_critical_health:
        actions.append({
            "action_type": "escalation",
            "priority": "urgent",
            "description": "Yonetici escalation toplantisi planla",
            "reasoning": (
                "Firsat risk altinda (saglik skoru dusuk veya risk sinyali var). "
                "Yonetici ile birlikte kurtarma plani olusturun."
            ),
        })

    if "churn_risk" in signal_types:
        actions.append({
            "action_type": "followup",
            "priority": "high",
            "description": "Musteri kaybi onleme plani hazirla",
            "reasoning": (
                "Musteri kaybi riski tespit edildi. "
                "Memnuniyet gorusmesi ve ozel teklif hazirlayin."
            ),
        })

    if not actions:
        actions.append({
            "action_type": "status_update",
            "priority": "normal",
            "description": "Firsat durumunu guncelle",
            "reasoning": (
                "Belirgin bir risk sinyali yok. "
                "Firsat bilgilerini ve tahmini kapanis tarihini guncelle."
            ),
        })

    return actions[:max_actions]
