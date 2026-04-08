"""v2 AI endpoints — summaries, pipeline suggestions, signal extraction.

All guarded by feature flags. AI calls use Claude with fallback.
Every AI action is logged to audit trail.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.email_request import EmailRequest
from app.models.enums import UserRole
from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal, Task
from app.models.quote import Quote
from app.models.user import User
from app.services.audit_service import log_action

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI (v2)"])

# Summary cache: hash(entity_type+entity_id) → {"summary":..., "ts":...}
_summary_cache: dict[str, dict] = {}
SUMMARY_CACHE_TTL = 300  # 5 minutes
CONTEXT_MAX_CHARS = 8000  # expanded from 3000


def _require_ai_summaries():
    if not settings.FEATURE_AI_SUMMARIES:
        raise HTTPException(status_code=404, detail="Not found")


def _require_ai_suggestions():
    if not settings.FEATURE_AI_PIPELINE_SUGGESTIONS:
        raise HTTPException(status_code=404, detail="Not found")


# ── Schemas ──

class SummarizeRequest(BaseModel):
    entity_type: str  # opportunity | quote | customer | email
    entity_id: int
    focus: str | None = None  # optional focus area

class PipelineSuggestRequest(BaseModel):
    opportunity_id: int

class ExtractSignalsRequest(BaseModel):
    opportunity_id: int | None = None
    email_id: int | None = None


# ── AI Helper ──

async def _call_claude(system_prompt: str, user_prompt: str) -> str | None:
    """Call Claude API. Returns text or None on failure."""
    if not settings.ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=settings.AI_MODEL_NAME,
            max_tokens=settings.AI_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text if response.content else None
    except Exception as e:
        logger.error("Claude API error: %s", e)
        return None


# ══════════════════════════════════════════
# 1. SUMMARIZE
# ══════════════════════════════════════════

@router.post("/summarize")
async def summarize(
    body: SummarizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_summaries),
):
    """One-click summary with LRU cache (5min TTL) and 8K context window."""
    import time

    # Check cache
    cache_key = hashlib.md5(f"{body.entity_type}:{body.entity_id}:{body.focus or ''}".encode()).hexdigest()
    cached = _summary_cache.get(cache_key)
    if cached and (time.time() - cached["ts"]) < SUMMARY_CACHE_TTL:
        return {"summary": cached["summary"], "sources": cached["sources"], "cached": True}

    context_text = ""
    sources = []

    if body.entity_type == "opportunity":
        opp = (await db.execute(select(Opportunity).where(Opportunity.id == body.entity_id))).scalar_one_or_none()
        if not opp:
            raise NotFoundException("Firsat bulunamadi")

        # Gather context
        events = (await db.execute(
            select(OpportunityEvent).where(OpportunityEvent.opportunity_id == opp.id)
            .order_by(OpportunityEvent.occurred_at.desc()).limit(20)
        )).scalars().all()

        quotes = (await db.execute(
            select(Quote).where(Quote.opportunity_id == opp.id)
        )).scalars().all()

        context_text = f"Firsat: {opp.title}\nAsama: {opp.stage}\nTutar: {opp.amount} {opp.currency}\n"
        context_text += f"Musteri: {opp.customer.name if opp.customer else 'Bilinmiyor'}\n"
        context_text += f"Son guncelleme: {opp.updated_at}\n\n"
        context_text += "Olaylar:\n" + "\n".join(f"- {e.event_type}: {e.description}" for e in events) + "\n\n"
        context_text += f"Teklifler: {len(quotes)} adet\n"
        for q in quotes:
            context_text += f"- {q.quote_number} ({q.status}) {q.grand_total} {q.currency}\n"
            sources.append({"type": "quote", "id": q.id, "label": q.quote_number})

    elif body.entity_type == "email":
        email = (await db.execute(select(EmailRequest).where(EmailRequest.id == body.entity_id))).scalar_one_or_none()
        if not email:
            raise NotFoundException("Email bulunamadi")
        context_text = f"Gonderen: {email.from_address}\nKonu: {email.subject}\n\n{email.body_text or ''}"
        sources.append({"type": "email", "id": email.id, "label": email.subject})

    elif body.entity_type == "quote":
        quote = (await db.execute(select(Quote).where(Quote.id == body.entity_id))).scalar_one_or_none()
        if not quote:
            raise NotFoundException("Teklif bulunamadi")
        context_text = f"Teklif: {quote.quote_number}\nDurum: {quote.status}\nToplam: {quote.grand_total} {quote.currency}\nKalem sayisi: {len(quote.items or [])}"
        sources.append({"type": "quote", "id": quote.id, "label": quote.quote_number})

    else:
        raise BadRequestException("Gecersiz entity_type. Desteklenen: opportunity, email, quote")

    if not context_text:
        return {"summary": "Ozetlenecek veri bulunamadi.", "sources": []}

    focus_instruction = f"\nOdak noktasi: {body.focus}" if body.focus else ""
    summary = await _call_claude(
        system_prompt="Sen bir satis asistanisin. Turkce, kisa ve aksiyona yonelik ozetler uretirsin. Teknik detay verme, is sonuclarina odaklan.",
        user_prompt=f"Asagidaki satis verisini 3-5 cumleyle ozetle:{focus_instruction}\n\n{context_text[:CONTEXT_MAX_CHARS]}",
    )

    if not summary:
        # Fallback: basit özet
        summary = f"{body.entity_type.capitalize()} #{body.entity_id} icin ozet olusturulamadi (AI servisi mevcut degil)."

    await log_action(db, user_id=current_user.id, action="ai_summarize", entity_type=body.entity_type, entity_id=body.entity_id)

    # Write to cache
    _summary_cache[cache_key] = {"summary": summary, "sources": sources, "ts": time.time()}
    # Evict old entries (max 500)
    if len(_summary_cache) > 500:
        oldest = sorted(_summary_cache, key=lambda k: _summary_cache[k]["ts"])[:100]
        for k in oldest:
            _summary_cache.pop(k, None)

    return {"summary": summary, "sources": sources, "cached": False}


# ══════════════════════════════════════════
# 2. SUGGEST PIPELINE UPDATE
# ══════════════════════════════════════════

@router.post("/suggest-pipeline-update")
async def suggest_pipeline_update(
    body: PipelineSuggestRequest,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_suggestions),
):
    """AI-powered pipeline stage + next step suggestions."""
    opp = (await db.execute(select(Opportunity).where(Opportunity.id == body.opportunity_id))).scalar_one_or_none()
    if not opp:
        raise NotFoundException("Firsat bulunamadi")

    now = datetime.now(timezone.utc)
    updated = opp.updated_at.replace(tzinfo=timezone.utc) if opp.updated_at and opp.updated_at.tzinfo is None else opp.updated_at
    days_stale = (now - updated).days if updated else 0

    # Rule-based suggestions (always available, no AI needed)
    suggestions = []
    factors = []

    # Rotting check
    if days_stale > 14 and opp.stage not in ("closed_won", "closed_lost"):
        factors.append({"factor": "no_touch", "detail": f"{days_stale} gundur guncelleme yok", "severity": "high"})
        suggestions.append("Musteri ile iletisime gecin veya firsati kapatmayi degerlendirin.")

    # Stage progression
    quote_count = (await db.execute(
        select(func.count(Quote.id)).where(Quote.opportunity_id == opp.id)
    )).scalar() or 0
    sent_count = (await db.execute(
        select(func.count(Quote.id)).where(Quote.opportunity_id == opp.id, Quote.status == "sent")
    )).scalar() or 0

    if opp.stage == "prospecting" and quote_count > 0:
        suggestions.append("Teklif hazirlanmis — asamayi 'qualified' veya 'proposal' olarak guncelleyin.")
        factors.append({"factor": "stage_mismatch", "detail": f"{quote_count} teklif var ama asama hala prospecting", "severity": "med"})

    if opp.stage == "proposal" and sent_count > 0:
        suggestions.append("Teklif gonderilmis — asamayi 'negotiation' olarak guncelleyin.")
        factors.append({"factor": "sent_quote", "detail": f"{sent_count} teklif gonderildi", "severity": "low"})

    if not opp.amount:
        suggestions.append("Firsat tutari girilmemis — pipeline coverage hesabi icin tutar ekleyin.")
        factors.append({"factor": "missing_amount", "detail": "Tutar bos", "severity": "med"})

    if not opp.close_date:
        suggestions.append("Tahmini kapanis tarihi eklenmemis — forecast icin tarih girin.")
        factors.append({"factor": "missing_close_date", "detail": "Kapanis tarihi bos", "severity": "med"})

    # AI enhancement (if available)
    suggested_stage = None
    if settings.ANTHROPIC_API_KEY and factors:
        ai_response = await _call_claude(
            system_prompt="Sen bir satis pipeline yonetim asistanisin. Kisa ve net oneriler ver.",
            user_prompt=f"Firsat: {opp.title}, Asama: {opp.stage}, Tutar: {opp.amount}, {days_stale} gundur dokunulmamis, {quote_count} teklif var ({sent_count} gonderildi). Bir sonraki asama ne olmali? Tek kelime cevap ver: prospecting/qualified/proposal/negotiation/closed_won/closed_lost",
        )
        if ai_response:
            cleaned = ai_response.strip().lower().replace(".", "")
            valid_stages = {"prospecting", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"}
            if cleaned in valid_stages:
                suggested_stage = cleaned

    await log_action(db, user_id=current_user.id, action="ai_suggest", entity_type="opportunity", entity_id=opp.id)

    return {
        "opportunity_id": opp.id,
        "current_stage": opp.stage,
        "suggested_stage": suggested_stage,
        "suggested_next_steps": suggestions,
        "factors": factors,
    }


# ══════════════════════════════════════════
# 3. EXTRACT SIGNALS
# ══════════════════════════════════════════

SIGNAL_KEYWORDS = {
    "pricing_concern": ["fiyat", "pahali", "butce", "indirim", "ucuz", "maliyet", "expensive", "budget", "discount", "cost"],
    "competitor": ["rakip", "alternatif", "baska firma", "competitor", "alternative"],
    "objection": ["endise", "sorun", "risk", "gecikme", "concern", "issue", "delay", "problem"],
    "positive": ["memnun", "guzel", "hizli", "basarili", "satisfied", "great", "fast", "excellent"],
}


@router.post("/extract-signals")
async def extract_signals(
    body: ExtractSignalsRequest,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_suggestions),
):
    """Extract risk/insight signals from opportunity emails or specific email."""
    texts = []
    opp_id = body.opportunity_id

    if body.email_id:
        email = (await db.execute(select(EmailRequest).where(EmailRequest.id == body.email_id))).scalar_one_or_none()
        if email:
            texts.append(f"{email.subject or ''} {email.body_text or ''}")
            if not opp_id and email.opportunity_id:
                opp_id = email.opportunity_id

    if opp_id and not texts:
        # Get recent emails linked to this opportunity's customer
        opp = (await db.execute(select(Opportunity).where(Opportunity.id == opp_id))).scalar_one_or_none()
        if opp and opp.customer_id:
            emails = (await db.execute(
                select(EmailRequest).where(EmailRequest.customer_id == opp.customer_id)
                .order_by(EmailRequest.created_at.desc()).limit(10)
            )).scalars().all()
            for e in emails:
                texts.append(f"{e.subject or ''} {e.body_text or ''}")

    if not texts or not opp_id:
        return {"signals": [], "message": "Sinyal cikarilacak veri bulunamadi"}

    combined_text = " ".join(texts)
    extracted_signals = []
    method = "keyword"

    # Strategy 1: Claude AI extraction (if API key available)
    if settings.ANTHROPIC_API_KEY:
        ai_signals = await _call_claude(
            system_prompt=(
                "Sen bir satis sinyali tespit asistanisin. Verilen email/gorusme metninden "
                "su sinyal turlerini cikar: pricing_concern, competitor, objection, positive. "
                "Her sinyal icin JSON array formatinda cevap ver: "
                '[{"type":"pricing_concern","severity":"high","evidence":"ilgili cumle"}]. '
                "Hicbir sinyal yoksa bos array don: []"
            ),
            user_prompt=combined_text[:4000],
        )
        if ai_signals:
            try:
                parsed = json.loads(ai_signals.strip())
                if isinstance(parsed, list):
                    for s in parsed:
                        signal = OpportunitySignal(
                            opportunity_id=opp_id,
                            signal_type=s.get("type", "objection"),
                            severity=s.get("severity", "med"),
                            evidence=s.get("evidence", "AI tespit"),
                            source_type="ai",
                        )
                        db.add(signal)
                        extracted_signals.append({
                            "signal_type": signal.signal_type,
                            "severity": signal.severity,
                            "evidence": signal.evidence,
                        })
                    method = "ai"
            except (json.JSONDecodeError, TypeError):
                pass  # Fall through to keyword

    # Strategy 2: Keyword fallback (always runs if AI found nothing)
    if not extracted_signals:
        combined_lower = combined_text.lower()
        for signal_type, keywords in SIGNAL_KEYWORDS.items():
            matched = [kw for kw in keywords if kw in combined_lower]
            if matched:
                severity = "high" if len(matched) >= 3 else "med" if len(matched) >= 2 else "low"
                signal = OpportunitySignal(
                    opportunity_id=opp_id,
                    signal_type=signal_type,
                    severity=severity,
                    evidence=f"Eslesen anahtar kelimeler: {', '.join(matched)}",
                    source_type="keyword",
                )
                db.add(signal)
                extracted_signals.append({
                    "signal_type": signal_type,
                    "severity": severity,
                    "evidence": signal.evidence,
                })
        method = "keyword"

    await db.flush()
    await log_action(db, user_id=current_user.id, action="ai_extract_signals", entity_type="opportunity", entity_id=opp_id)

    return {"opportunity_id": opp_id, "signals": extracted_signals, "method": method}


# ══════════════════════════════════════════
# 4. SIGNALS CRUD (read)
# ══════════════════════════════════════════

@router.get("/signals/{opportunity_id}")
async def get_signals(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all signals for an opportunity."""
    signals = (await db.execute(
        select(OpportunitySignal).where(OpportunitySignal.opportunity_id == opportunity_id)
        .order_by(OpportunitySignal.created_at.desc())
    )).scalars().all()

    return {
        "opportunity_id": opportunity_id,
        "signals": [
            {
                "id": s.id,
                "signal_type": s.signal_type,
                "severity": s.severity,
                "evidence": s.evidence,
                "source_type": s.source_type,
                "is_resolved": s.is_resolved,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in signals
        ],
    }


# ══════════════════════════════════════════
# 5. TASKS CRUD
# ══════════════════════════════════════════

class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    opportunity_id: int | None = None
    due_at: str | None = None  # ISO datetime
    priority: str = "normal"

class TaskUpdate(BaseModel):
    status: str | None = None  # open | done | dismissed
    title: str | None = None
    due_at: str | None = None


@router.get("/tasks")
async def list_tasks(
    status: str = "open",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tasks for current user."""
    query = select(Task).where(Task.owner_id == current_user.id)
    if status:
        query = query.where(Task.status == status)
    query = query.order_by(Task.due_at.asc().nullslast(), Task.created_at.desc())

    tasks = (await db.execute(query)).scalars().all()
    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "opportunity_id": t.opportunity_id,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "status": t.status,
                "source": t.source,
                "priority": t.priority,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ],
    }


@router.post("/tasks", status_code=201)
async def create_task(
    body: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a task (manual or from AI suggestion)."""
    task = Task(
        owner_id=current_user.id,
        opportunity_id=body.opportunity_id,
        title=body.title,
        description=body.description,
        due_at=datetime.fromisoformat(body.due_at) if body.due_at else None,
        priority=body.priority,
        source="manual",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    return {"id": task.id, "title": task.title, "status": task.status}


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: int,
    body: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update task status or details."""
    task = (await db.execute(
        select(Task).where(Task.id == task_id, Task.owner_id == current_user.id)
    )).scalar_one_or_none()
    if not task:
        raise NotFoundException("Gorev bulunamadi")

    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "due_at" and value:
            setattr(task, field, datetime.fromisoformat(value))
        else:
            setattr(task, field, value)

    await db.flush()
    return {"id": task.id, "status": task.status}
