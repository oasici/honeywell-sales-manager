"""v2 AI endpoints — summaries, pipeline suggestions, signal extraction.

All guarded by feature flags. AI calls use Claude with fallback.
Every AI action is logged to audit trail.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import asyncio
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.rate_limit import (
    enforce_ai_rate_limit,
    enforce_tenant_ai_rate_limit,
)
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.enums import UserRole
from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal, Task
from app.services.dedupe_service import upsert_opportunity_signal, upsert_task
from app.models.quote import Quote
from app.models.user import User
from app.services.audit_service import log_action
from app.services.tenant_context import assert_same_tenant, is_cross_tenant
from app.api.v1.opportunities import _last_activity_max_by_opportunity_ids, _opportunity_staleness_days


def _assert_or_404(record, current_user, *, message: str) -> None:
    """R4-TEN-24 — guard rail for AI helpers that load records by id.

    The AI endpoints below feed loaded entities (Customer, Opportunity,
    EmailRequest) directly into Claude prompts. A missing tenant check
    here would let a manager from tenant A trigger AI generation
    against tenant B's data and exfiltrate the response. We collapse
    cross-tenant probes to the same 404 the "doesn't exist" branch
    raises so this surface can't be used for tenant enumeration either.
    """
    try:
        assert_same_tenant(record, current_user, exception_cls=NotFoundException)
    except NotFoundException:
        raise NotFoundException(message)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ai",
    tags=["AI (v2)"],
    # Per-tenant cap evaluated first, per-user cap second. Both must
    # pass; per-tenant is no-op outside multi-tenant deployments.
    dependencies=[
        Depends(enforce_tenant_ai_rate_limit),
        Depends(enforce_ai_rate_limit),
    ],
)

# Summary cache: hash(entity_type+entity_id) → {"summary":..., "ts":...}
_summary_cache: dict[str, dict] = {}
SUMMARY_CACHE_TTL = 300  # 5 minutes
CONTEXT_MAX_CHARS = 8000  # expanded from 3000

# Claude guardrails (production hardening)
CLAUDE_TIMEOUT_S = 18
CLAUDE_RETRIES = 2
_claude_cb = {
    "fail_count": 0,
    "open_until": 0.0,  # monotonic time
}
CLAUDE_CB_OPEN_AFTER = 6  # consecutive failures
CLAUDE_CB_COOLDOWN_S = 60


def _require_ai_summaries():
    if not settings.FEATURE_AI_SUMMARIES:
        raise HTTPException(status_code=404, detail="Not found")


def _require_ai_suggestions():
    if not settings.FEATURE_AI_PIPELINE_SUGGESTIONS:
        raise HTTPException(status_code=404, detail="Not found")

def _require_tasks():
    if not settings.FEATURE_TASKS:
        raise HTTPException(status_code=404, detail="Not found")


# ── Schemas ──

class SummarizeRequest(BaseModel):
    entity_type: str  # opportunity | quote | customer | email
    entity_id: int
    focus: str | None = None  # optional focus area
    force: bool = False  # bypass cache (manual refresh)


class SummarizeChangesRequest(BaseModel):
    """Last-N-days change digest (opportunity | customer)."""

    entity_type: str  # opportunity | customer
    entity_id: int
    days: int = Field(default=7, ge=1, le=90)
    force: bool = False

class PipelineSuggestRequest(BaseModel):
    opportunity_id: int

class ExtractSignalsRequest(BaseModel):
    opportunity_id: int | None = None
    email_id: int | None = None


class DealRiskRequest(BaseModel):
    opportunity_id: int


class EmailDraftRequest(BaseModel):
    email_id: int | None = None
    draft_type: str = "reply"  # reply | compose
    tone: str = "professional"  # professional | friendly | formal
    template_context: dict | None = None  # for compose mode


class GenerateActionsRequest(BaseModel):
    opportunity_id: int
    max_actions: int = Field(default=5, ge=1, le=20)


class MeetingPrepRequest(BaseModel):
    customer_id: int


# ── AI Helper ──

async def _call_claude(system_prompt: str, user_prompt: str) -> str | None:
    """Call Claude API. Returns text or None on failure."""
    if not settings.ANTHROPIC_API_KEY:
        return None
    now = time.monotonic()
    if _claude_cb["open_until"] > now:
        logger.warning("Claude circuit open; skipping call")
        return None
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        last_err: Exception | None = None
        for attempt in range(CLAUDE_RETRIES + 1):
            started = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    client.messages.create(
                        model=settings.AI_MODEL_NAME,
                        max_tokens=settings.AI_MAX_TOKENS,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_prompt}],
                    ),
                    timeout=CLAUDE_TIMEOUT_S,
                )
                _claude_cb["fail_count"] = 0
                dt_ms = int((time.monotonic() - started) * 1000)
                logger.info("Claude ok in %sms (attempt=%s)", dt_ms, attempt + 1)
                return response.content[0].text if response.content else None
            except Exception as e:
                last_err = e
                _claude_cb["fail_count"] += 1
                dt_ms = int((time.monotonic() - started) * 1000)
                logger.warning("Claude fail in %sms (attempt=%s): %s", dt_ms, attempt + 1, e)

                if _claude_cb["fail_count"] >= CLAUDE_CB_OPEN_AFTER:
                    _claude_cb["open_until"] = time.monotonic() + CLAUDE_CB_COOLDOWN_S
                    logger.error("Claude circuit opened for %ss", CLAUDE_CB_COOLDOWN_S)
                    break

                # simple backoff
                if attempt < CLAUDE_RETRIES:
                    await asyncio.sleep(0.6 * (attempt + 1))

        logger.error("Claude API failed after retries: %s", last_err)
        return None
    except Exception as e:
        logger.error("Claude API error: %s", e)
        return None


def _generate_fallback_summary(entity_type: str, entity_id: int, context_text: str) -> str:
    """Generate a rule-based summary from context when Claude is unavailable."""
    lines = [l.strip() for l in context_text.strip().split("\n") if l.strip()]
    if not lines:
        return f"{entity_type.capitalize()} #{entity_id} icin veri bulunamadi."

    # Extract key-value pairs from context
    kv: dict[str, str] = {}
    for line in lines:
        if ":" in line and not line.startswith("-"):
            key, _, val = line.partition(":")
            kv[key.strip().lower()] = val.strip()

    if entity_type == "opportunity":
        title = kv.get("firsat", f"#{entity_id}")
        stage = kv.get("asama", "bilinmiyor")
        amount = kv.get("tutar", "-")
        customer = kv.get("musteri", "-")
        events_count = sum(1 for l in lines if l.startswith("- "))
        quotes_count = kv.get("teklifler", "0").split(" ")[0]
        return (
            f"Firsat '{title}' su anda '{stage}' asamasinda, tutar: {amount}. "
            f"Musteri: {customer}. Toplam {events_count} etkinlik ve {quotes_count} teklif kaydi mevcut. "
            f"Pipeline ilerlemesi ve musteri iletisimi takip edilmelidir."
        )
    if entity_type == "email":
        sender = kv.get("gonderen", "-")
        subject = kv.get("konu", "-")
        return (
            f"'{subject}' konulu e-posta {sender} tarafindan gonderilmistir. "
            f"Icerik analiz edilmis ve parca talepleri tespit edilmistir."
        )
    if entity_type == "quote":
        qnum = kv.get("teklif", f"#{entity_id}")
        status = kv.get("durum", "-")
        total = kv.get("toplam", "-")
        return (
            f"Teklif {qnum} durumu '{status}', toplam tutar: {total}. "
            f"Teklif detaylari ve kalem bilgileri mevcuttur."
        )
    if entity_type == "customer":
        name = kv.get("musteri", f"#{entity_id}")
        company = kv.get("sirket", "-")
        quote_line = kv.get("teklifler", "0")
        opp_line = kv.get("firsatlar", "0")
        email_line = kv.get("son emailler", "0")
        return (
            f"Musteri '{name}' ({company}) ile toplam {quote_line} teklif, "
            f"{opp_line} firsat ve {email_line} email kaydi mevcuttur. "
            f"Musteri iliskisi aktif olarak takip edilmektedir."
        )
    return f"{entity_type.capitalize()} #{entity_id} icin ozet bilgiler derlenmistir."


# ══════════════════════════════════════════
# 1. SUMMARIZE
# ══════════════════════════════════════════

@router.post("/summarize")
async def summarize(
    body: SummarizeRequest,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_summaries),
):
    """One-click summary with cache + guard rails (Sprint 6 baseline)."""
    import time

    # Cost guardrail: allow operators to hard-disable LLM calls.
    if os.environ.get("AI_ENABLED", "true").lower() != "true":
        raise HTTPException(status_code=503, detail="AI devre disi")

    raw_key = f"v2:{body.entity_type}:{body.entity_id}:{body.focus or ''}"
    cache_key = f"ai:summary:{hashlib.md5(raw_key.encode()).hexdigest()}"

    # Rate limit (best-effort): protect AI endpoint from abuse.
    # Prefer Redis to work in multi-worker deployments.
    try:
        from app.core.redis_client import get_redis

        r = get_redis()
        if r:
            minute = int(time.time() // 60)
            rl_key = f"ratelimit:ai_summarize:{current_user.id}:{minute}"
            count = await r.incr(rl_key)
            if count == 1:
                await r.expire(rl_key, 70)
            if count > 30:
                raise HTTPException(status_code=429, detail="Cok fazla istek (AI summarize)")
    except HTTPException:
        raise
    except Exception:
        pass

    if not body.force:
        # Try Redis cache first (shared across workers)
        try:
            from app.core.redis_client import get_redis
            r = get_redis()
            if r:
                cached_json = await r.get(cache_key)
                if cached_json:
                    cached = json.loads(cached_json)
                    return {
                        "summary": cached["summary"],
                        "sources": cached["sources"],
                        "generated_at": cached.get("generated_at"),
                        "cached": True,
                    }
        except Exception:
            pass

    if not body.force:
        # In-memory fallback
        cached = _summary_cache.get(cache_key)
        if cached and (time.time() - cached["ts"]) < SUMMARY_CACHE_TTL:
            return {
                "summary": cached["summary"],
                "sources": cached["sources"],
                "generated_at": cached.get("generated_at"),
                "cached": True,
            }

    from app.services.summary_service import SummaryService

    service = SummaryService(db)
    result = await service.summarize(body.entity_type, body.entity_id, focus=body.focus)

    await log_action(db, user_id=current_user.id, action="ai_summarize", entity_type=body.entity_type, entity_id=body.entity_id)

    sources: list[dict | str] = []
    for s in result.sources or []:
        if isinstance(s, dict):
            sources.append(
                {
                    "type": str(s.get("type", "")),
                    "id": int(s.get("id", 0)),
                    "label": str(s.get("label", "")),
                }
            )
        else:
            sources.append(str(s))

    # Write to Redis cache (shared) + in-memory fallback
    cache_data = {"summary": result.summary, "sources": sources, "generated_at": result.generated_at}
    try:
        from app.core.redis_client import get_redis
        r = get_redis()
        if r:
            await r.setex(cache_key, SUMMARY_CACHE_TTL, json.dumps(cache_data))
    except Exception:
        pass
    _summary_cache[cache_key] = {**cache_data, "ts": time.time()}
    if len(_summary_cache) > 500:
        oldest = sorted(_summary_cache, key=lambda k: _summary_cache[k]["ts"])[:100]
        for k in oldest:
            _summary_cache.pop(k, None)

    return {
        "summary": result.summary,
        "sources": sources,
        "generated_at": result.generated_at,
        "cached": False,
    }


@router.post("/summarize/changes")
async def summarize_changes(
    body: SummarizeChangesRequest,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_summaries),
):
    """Sprint 6 — digest of what changed on the account/opportunity in the last N days."""
    import time

    if os.environ.get("AI_ENABLED", "true").lower() != "true":
        raise HTTPException(status_code=503, detail="AI devre disi")

    raw_key = f"v2:changes:{body.entity_type}:{body.entity_id}:{body.days}"
    cache_key = f"ai:summary:changes:{hashlib.md5(raw_key.encode()).hexdigest()}"

    try:
        from app.core.redis_client import get_redis

        r = get_redis()
        if r:
            minute = int(time.time() // 60)
            rl_key = f"ratelimit:ai_summarize_changes:{current_user.id}:{minute}"
            count = await r.incr(rl_key)
            if count == 1:
                await r.expire(rl_key, 70)
            if count > 30:
                raise HTTPException(status_code=429, detail="Cok fazla istek (AI degisim ozeti)")
    except HTTPException:
        raise
    except Exception:
        pass

    if not body.force:
        try:
            from app.core.redis_client import get_redis

            r = get_redis()
            if r:
                cached_json = await r.get(cache_key)
                if cached_json:
                    cached = json.loads(cached_json)
                    return {
                        "summary": cached["summary"],
                        "sources": cached["sources"],
                        "generated_at": cached.get("generated_at"),
                        "cached": True,
                        "days": body.days,
                    }
        except Exception:
            pass

    if not body.force:
        cached = _summary_cache.get(cache_key)
        if cached and (time.time() - cached["ts"]) < SUMMARY_CACHE_TTL:
            return {
                "summary": cached["summary"],
                "sources": cached["sources"],
                "generated_at": cached.get("generated_at"),
                "cached": True,
                "days": body.days,
            }

    from app.services.summary_service import SummaryService

    service = SummaryService(db)
    result = await service.summarize_changes(body.entity_type, body.entity_id, days=body.days)

    await log_action(
        db,
        user_id=current_user.id,
        action="ai_summarize_changes",
        entity_type=body.entity_type,
        entity_id=body.entity_id,
    )

    sources: list[dict] = []
    for s in result.sources or []:
        if isinstance(s, dict):
            sources.append(
                {
                    "type": str(s.get("type", "")),
                    "id": int(s.get("id", 0)),
                    "label": str(s.get("label", "")),
                }
            )

    cache_data = {"summary": result.summary, "sources": sources, "generated_at": result.generated_at}
    try:
        from app.core.redis_client import get_redis

        r = get_redis()
        if r:
            await r.setex(cache_key, SUMMARY_CACHE_TTL, json.dumps(cache_data))
    except Exception:
        pass
    _summary_cache[cache_key] = {**cache_data, "ts": time.time()}
    if len(_summary_cache) > 500:
        oldest = sorted(_summary_cache, key=lambda k: _summary_cache[k]["ts"])[:100]
        for k in oldest:
            _summary_cache.pop(k, None)

    return {
        "summary": result.summary,
        "sources": sources,
        "generated_at": result.generated_at,
        "cached": False,
        "days": body.days,
    }


@router.post("/meeting-prep")
async def meeting_prep(
    body: MeetingPrepRequest,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_summaries),
):
    """Sprint 3 — Account Intelligence: toplantı öncesi kısa brifing (PII maskeli)."""
    import time

    try:
        from app.core.redis_client import get_redis

        r = get_redis()
        if r:
            minute = int(time.time() // 60)
            rl_key = f"ratelimit:ai_meeting_prep:{current_user.id}:{minute}"
            count = await r.incr(rl_key)
            if count == 1:
                await r.expire(rl_key, 70)
            if count > 20:
                raise HTTPException(status_code=429, detail="Cok fazla istek (AI meeting prep)")
    except HTTPException:
        raise
    except Exception:
        pass

    cust = (
        await db.execute(select(Customer).where(Customer.id == body.customer_id))
    ).scalar_one_or_none()
    if not cust:
        raise NotFoundException("Musteri bulunamadi")
    _assert_or_404(cust, current_user, message="Musteri bulunamadi")

    from app.services.account_aggregate_service import AccountAggregateService
    from app.services.summary_service import redact_pii

    svc = AccountAggregateService(db)
    await svc.ensure_fresh(body.customer_id, current_user, refresh=False)
    ctx = await svc.build_meeting_prep_context(body.customer_id, current_user)
    ctx = redact_pii(ctx)

    prep = await _call_claude(
        system_prompt=(
            "Satis temsilcisinin toplanti hazirlik asistanisin. Turkce, 5-7 numarali kisa madde. "
            "Email, telefon ve kisisel veri yazma."
        ),
        user_prompt=(
            ctx
            + "\n\nGorev: Bu musteriyle yapilacak toplantiya hazirlik. "
            "Odak: riskler, acik firsatlar, net sorular, sonraki adim onerisi."
        )[:CONTEXT_MAX_CHARS],
    )
    if not prep:
        rs = await svc.risk_summary(body.customer_id, current_user)
        prep = (
            f"{cust.name} ile toplanti — hazirlik notlari (otomatik):\n"
            f"1) Risk seviyesi: {rs.get('risk_level')}, cozulmemis yuksek sinyal: {rs.get('unresolved_high_signals')}.\n"
            f"2) Acik firsatlari board uzerinden gozden gecirin.\n"
            f"3) Son aktivite ve teklif durumunu teyit edin.\n"
            f"4) Net sonraki adim ve tarih onerin.\n"
        )
    prep = redact_pii(prep)[:2000]

    await log_action(
        db,
        user_id=current_user.id,
        action="ai_meeting_prep",
        entity_type="customer",
        entity_id=body.customer_id,
    )

    return {"prep": prep, "customer_id": body.customer_id}


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
    _assert_or_404(opp, current_user, message="Firsat bulunamadi")

    last_activity_map = await _last_activity_max_by_opportunity_ids(db, [opp.id])
    last_activity_at = last_activity_map.get(opp.id)
    days_stale = _opportunity_staleness_days(opp, last_activity_at)

    # Rule-based suggestions (always available, no AI needed)
    suggestions = []
    factors = []

    # Rotting check
    if days_stale > 14 and opp.stage not in ("closed_won", "closed_lost"):
        factors.append(
            {
                "factor": "no_touch",
                "detail": f"{days_stale} gundur dokunulmamis (son aktivite veya kayit guncellemesi)",
                "severity": "high",
            }
        )
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

    # Always provide baseline suggestions if none triggered
    if not suggestions:
        stage_order = ["prospecting", "qualified", "proposal", "negotiation", "closed_won"]
        current_idx = stage_order.index(opp.stage) if opp.stage in stage_order else -1
        if current_idx >= 0 and current_idx < len(stage_order) - 1:
            next_stage_label = stage_order[current_idx + 1]
            suggestions.append(f"Firsat '{next_stage_label}' asamasina ilerletilmeye uygun gorunuyor.")
        suggestions.append("Musteri ile son durumu dogrulayin ve pipeline guncellemeyi degerlendirin.")
        factors.append({"factor": "review", "detail": f"Asama: {opp.stage}, {quote_count} teklif mevcut", "severity": "info"})

    # AI enhancement (if available)
    suggested_stage = None
    if settings.ANTHROPIC_API_KEY:
        ai_response = await _call_claude(
            system_prompt="Sen bir satis pipeline yonetim asistanisin. Kisa ve net oneriler ver.",
            user_prompt=f"Firsat: {opp.title}, Asama: {opp.stage}, Tutar: {opp.amount}, {days_stale} gundur dokunulmamis, {quote_count} teklif var ({sent_count} gonderildi). Bir sonraki asama ne olmali? Tek kelime cevap ver: prospecting/qualified/proposal/negotiation/closed_won/closed_lost",
        )
        if ai_response:
            cleaned = ai_response.strip().lower().replace(".", "")
            valid_stages = {"prospecting", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"}
            if cleaned in valid_stages:
                suggested_stage = cleaned

    # Rule-based stage suggestion fallback when AI is unavailable
    if suggested_stage is None:
        stage_progression = {
            "prospecting": "qualified",
            "qualified": "proposal",
            "proposal": "negotiation",
            "negotiation": "closed_won",
        }
        if opp.stage == "prospecting" and quote_count > 0:
            suggested_stage = "proposal"
        elif opp.stage in stage_progression:
            suggested_stage = stage_progression[opp.stage]

    await log_action(db, user_id=current_user.id, action="ai_suggest", entity_type="opportunity", entity_id=opp.id)

    # Flatten factors to strings for frontend compatibility
    factor_strings = [f.get("detail", f.get("factor", "")) for f in factors if isinstance(f, dict)]

    return {
        "opportunity_id": opp.id,
        "current_stage": opp.stage,
        "suggested_stage": suggested_stage or opp.stage,
        "suggested_next_steps": suggestions,
        "factors": factor_strings,
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
        # R4-TEN-24: drop the email row when it belongs to a different
        # tenant. We swallow the cross-tenant attempt instead of raising
        # so this endpoint behaves the same as the existing "email not
        # found" path (which also returns the empty-signals response).
        if email and not is_cross_tenant(email, current_user):
            texts.append(f"{email.subject or ''} {email.body_text or ''}")
            if not opp_id and email.opportunity_id:
                opp_id = email.opportunity_id

    if opp_id and not texts:
        # Get recent emails linked to this opportunity's customer
        opp = (await db.execute(select(Opportunity).where(Opportunity.id == opp_id))).scalar_one_or_none()
        # R4-TEN-24: drop the opp when cross-tenant; skip the customer
        # email enumeration entirely so we don't fan out to foreign-
        # tenant rows via the customer_id back-reference.
        if opp and not is_cross_tenant(opp, current_user) and opp.customer_id:
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
                        signal = await upsert_opportunity_signal(
                            db,
                            opportunity_id=opp_id,
                            signal_type=s.get("type", "objection"),
                            severity=s.get("severity", "med"),
                            evidence=s.get("evidence", "AI tespit"),
                            source_type="ai",
                            source_id=body.email_id,
                        )
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
                signal = await upsert_opportunity_signal(
                    db,
                    opportunity_id=opp_id,
                    signal_type=signal_type,
                    severity=severity,
                    evidence=f"Eslesen anahtar kelimeler: {', '.join(matched)}",
                    source_type="keyword",
                    source_id=body.email_id,
                )
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

    # Round-11 R11-API-1 — canonical pagination envelope. Previous
    # `{opportunity_id, signals: [...]}` shape forced the SPA into a
    # per-endpoint branch. Legacy keys preserved until callers migrate.
    items = [
        {
            "id": s.id,
            "opportunity_id": s.opportunity_id,
            "signal_type": s.signal_type,
            "severity": s.severity,
            "evidence": s.evidence,
            "source_type": s.source_type,
            "is_resolved": s.is_resolved,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in signals
    ]
    total = len(items)
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
        # Legacy aliases — kept until SPA callers migrate.
        "opportunity_id": opportunity_id,
        "signals": items,
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
    _flag=Depends(_require_tasks),
):
    """List tasks for current user."""
    query = select(Task).where(Task.owner_id == current_user.id)
    if status:
        query = query.where(Task.status == status)
    query = query.order_by(Task.due_at.asc().nullslast(), Task.created_at.desc())

    tasks = (await db.execute(query)).scalars().all()
    # Round-11 R11-API-1 — canonical pagination envelope. Legacy
    # `tasks` key preserved until SPA callers migrate.
    items = [
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
    ]
    total = len(items)
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
        # Legacy alias.
        "tasks": items,
    }


@router.post("/tasks", status_code=201)
async def create_task(
    body: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_tasks),
):
    """Create a task (manual or from AI suggestion)."""
    task = await upsert_task(
        db,
        owner_id=current_user.id,
        opportunity_id=body.opportunity_id,
        title=body.title,
        description=body.description,
        due_at=datetime.fromisoformat(body.due_at) if body.due_at else None,
        priority=body.priority,
        source="manual",
        status="open",
        dedupe_window_days=1,
    )

    return {"id": task.id, "title": task.title, "status": task.status}


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: int,
    body: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_tasks),
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


# ══════════════════════════════════════════
# 6. GENERATE ACTIONS (AI Action Generator)
# ══════════════════════════════════════════

def _require_revenue_cockpit():
    if not settings.FEATURE_REVENUE_COCKPIT:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/generate-actions")
async def generate_actions_endpoint(
    body: GenerateActionsRequest,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_revenue_cockpit),
):
    """AI-powered action generation for an opportunity."""
    from app.services.ai_action_generator import generate_actions

    actions = await generate_actions(db, body.opportunity_id, body.max_actions)
    await log_action(
        db,
        user_id=current_user.id,
        action="ai_generate_actions",
        entity_type="opportunity",
        entity_id=body.opportunity_id,
    )
    return {"actions": actions, "count": len(actions)}


# ══════════════════════════════════════════
# 7. DEAL RISK ASSESSMENT
# ══════════════════════════════════════════


def _require_ai_deal_risk():
    if not settings.FEATURE_AI_DEAL_RISK:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/deal-risk/{opportunity_id}")
async def deal_risk_endpoint(
    opportunity_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_deal_risk),
):
    """AI-powered deal risk assessment with explainable factors."""
    from app.services.ai_deal_risk_service import assess_deal_risk

    result = await assess_deal_risk(db, opportunity_id)
    if "error" in result:
        raise NotFoundException(result["error"])

    await log_action(
        db,
        user_id=current_user.id,
        action="ai_deal_risk",
        entity_type="opportunity",
        entity_id=opportunity_id,
    )
    return result


# ══════════════════════════════════════════
# 8. COMPETITIVE INTELLIGENCE DASHBOARD
# ══════════════════════════════════════════


def _require_ai_predictions():
    if not settings.FEATURE_AI_PREDICTIONS:
        raise HTTPException(status_code=404, detail="Not found")


# ══════════════════════════════════════════
# 8. PREDICT CLOSE PROBABILITY
# ══════════════════════════════════════════


@router.post("/predict-close/{opportunity_id}")
async def predict_close(
    opportunity_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_predictions),
):
    """AI-powered close probability prediction for an opportunity."""
    from app.services.ai_deal_risk_service import predict_close_probability

    result = await predict_close_probability(db, opportunity_id)
    if "error" in result:
        raise NotFoundException(result["error"])

    await log_action(
        db,
        user_id=current_user.id,
        action="ai_predict_close",
        entity_type="opportunity",
        entity_id=opportunity_id,
    )
    return {"data": result}


# ══════════════════════════════════════════
# 9. PREDICT CHURN RISK
# ══════════════════════════════════════════


@router.post("/predict-churn/{customer_id}")
async def predict_churn(
    customer_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_predictions),
):
    """AI-powered churn risk prediction for a customer."""
    from app.services.customer_health_service import CustomerHealthService

    # N15-AUTH-4 — scope churn prediction to the caller's tenant; the
    # ``predict-churn`` endpoint must never reveal foreign-tenant customers.
    service = CustomerHealthService(db)
    result = await service.predict_churn_risk(
        customer_id, tenant_id=current_user.tenant_id,
    )
    if "error" in result:
        raise NotFoundException(result["error"])

    await log_action(
        db,
        user_id=current_user.id,
        action="ai_predict_churn",
        entity_type="customer",
        entity_id=customer_id,
    )
    return {"data": result}


# ══════════════════════════════════════════
# 10. COMPETITIVE INTELLIGENCE DASHBOARD
# ══════════════════════════════════════════


def _require_ai_competitive_intel():
    if not settings.FEATURE_AI_COMPETITIVE_INTEL:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/competitive-intel")
async def competitive_intel_dashboard(
    days: int = 90,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_ai_competitive_intel),
):
    """Competitive intelligence dashboard — aggregate competitor mention data."""
    from app.services.competitive_intel_service import get_competitor_dashboard

    result = await get_competitor_dashboard(db, days=days)
    return result


@router.post("/crawl-competitors")
async def crawl_competitors_endpoint(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    _flag=Depends(_require_ai_competitive_intel),
):
    """Manually trigger competitor web crawling. Manager only."""
    from app.services.competitor_crawler import crawl_all_competitors

    result = await crawl_all_competitors()
    return {"data": result}


@router.post("/crawl-competitor/{competitor_name}")
async def crawl_single_competitor(
    competitor_name: str,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    _flag=Depends(_require_ai_competitive_intel),
):
    """Crawl a single competitor's websites."""
    from app.services.competitor_crawler import crawl_competitor

    results = await crawl_competitor(competitor_name)

    if settings.FEATURE_RAG:
        try:
            from app.services.vector_store import store_competitor_intel

            for r in results:
                await store_competitor_intel(r)
        except Exception:
            pass

    return {"data": {"competitor": competitor_name, "results": results}}


# ══════════════════════════════════════════
# 11. RAG STATUS
# ══════════════════════════════════════════


@router.get("/rag/status")
async def rag_status(
    current_user: User = Depends(get_current_user),
):
    """Check RAG system status (Qdrant collections)."""
    from app.services.vector_store import _get_client

    if not settings.FEATURE_RAG:
        return {"data": {"enabled": False}}
    try:
        client = _get_client()
        collections = client.get_collections().collections
        return {
            "data": {
                "enabled": True,
                "collections": [
                    {"name": c.name, "points_count": c.points_count}
                    for c in collections
                ],
            },
        }
    except Exception as exc:
        return {"data": {"enabled": True, "error": str(exc)}}


# ══════════════════════════════════════════
# 12. EMAIL DRAFT REPLY
# ══════════════════════════════════════════

_TONE_INSTRUCTIONS: dict[str, str] = {
    "professional": "Use a professional and polite tone.",
    "friendly": "Use a warm, friendly but still professional tone.",
    "formal": "Use a very formal, business-appropriate tone.",
}

_EMAIL_DRAFT_FALLBACK = (
    "Sayin Yetkili,\n\n"
    "Mesajiniz icin tesekkur ederiz. En kisa surede size donecegiz.\n\n"
    "Saygilarimla,\nHoneywell Turkey Satis Ekibi"
)


@router.post("/email/draft-reply")
async def draft_email_reply(
    body: EmailDraftRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate AI-powered email draft using Claude."""
    from app.models.customer import Customer

    context_parts: list[str] = []

    if body.email_id:
        email_result = await db.execute(
            select(EmailRequest).where(EmailRequest.id == body.email_id)
        )
        email = email_result.scalar_one_or_none()
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        # R4-TEN-24: hard-block cross-tenant draft generation. Same 404
        # response as "email not found" so the API can't be used to
        # enumerate which email IDs exist in foreign tenants.
        try:
            assert_same_tenant(email, current_user, exception_cls=NotFoundException)
        except NotFoundException:
            raise HTTPException(status_code=404, detail="Email not found")
        context_parts.append(f"Original email subject: {email.subject}")
        context_parts.append(f"From: {email.from_address}")
        context_parts.append(f"Body:\n{(email.body_text or '')[:2000]}")

        if email.customer_id:
            cust_result = await db.execute(
                select(Customer).where(Customer.id == email.customer_id)
            )
            customer = cust_result.scalar_one_or_none()
            # R4-TEN-24: even when the email passed the tenant check, the
            # cross-loaded customer_id is just an integer on the email row
            # and could in theory point at a foreign-tenant Customer (data
            # corruption, manual edit, etc). Assert against the requesting
            # user, not the email, so the AI prompt can never include
            # cross-tenant customer data.
            if customer and not is_cross_tenant(customer, current_user):
                context_parts.append(f"Customer: {customer.name} ({customer.company})")

    if body.template_context:
        for k, v in body.template_context.items():
            context_parts.append(f"{k}: {v}")

    tone_instruction = _TONE_INSTRUCTIONS.get(body.tone, _TONE_INSTRUCTIONS["professional"])
    system_prompt = (
        f"You are a Honeywell Turkey sales representative writing an email {body.draft_type}.\n"
        f"{tone_instruction}\n"
        "Write in the same language as the received email (Turkish or English).\n"
        "Be concise, address the customer's questions, and include clear next steps.\n"
        "Return ONLY the email body text, no subject line or headers."
    )
    user_prompt = (
        "\n".join(context_parts)
        if context_parts
        else "Write a general sales follow-up email."
    )

    draft = await _call_claude(system_prompt=system_prompt, user_prompt=user_prompt)
    if not draft:
        draft = _EMAIL_DRAFT_FALLBACK

    await log_action(
        db,
        user_id=current_user.id,
        action="ai_email_draft",
        entity_type="email",
        entity_id=body.email_id,
    )

    detected_language = "tr" if any(c in draft for c in "şçğüöıİŞÇĞÜÖI") else "en"
    return {
        "draft": draft,
        "draft_type": body.draft_type,
        "tone": body.tone,
        "detected_language": detected_language,
    }
