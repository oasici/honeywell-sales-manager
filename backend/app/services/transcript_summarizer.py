"""Transcript summarizer (v3).

Upgrades over the previous prose-parsing version:

    - Claude tool-use (structured schema, zero JSON-parse flakiness).
    - AI Trust Layer: PII in the transcript is masked before reaching the
      vendor API and the response is re-hydrated on the way back.
    - Chunking: long transcripts (>8k chars) are split into overlapping
      windows, summarised per-chunk, then fused by a final merge call.
    - Emits Revenue Signals for competitor mentions / pricing concerns /
      objections / positive buying signals tied to the opportunity.
    - Persists CompetitorMention rows for downstream battle-card UI.
    - Keyword-pack detection runs regardless of AI availability so the
      rule-based path stays useful.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.competitor_mention import CompetitorMention
from app.models.engagement import KeywordPack, Transcript
from app.services.ai_trust import AITrustContext, audit_record, scrub, unscrub

logger = logging.getLogger(__name__)

CONTEXT_MAX_CHARS = 8000
CHUNK_OVERLAP = 400
MERGE_MAX_CHUNKS = 6  # hard cap to stay inside token budget


# ── Claude tool definition ──────────────────────────────────────────────────

_SUMMARY_TOOL = {
    "name": "summarise_sales_call",
    "description": (
        "Extract a structured sales-call summary from a transcript chunk. "
        "Write in Turkish, keep each field concise and action-oriented."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "3-6 cumlelik genel ozet.",
            },
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "owner": {
                            "type": "string",
                            "description": "Sorumlu kisi (bilinmiyorsa 'ekip').",
                        },
                        "due_hint": {
                            "type": "string",
                            "description": "Gorece tarih ipucu (bugun, 3 gun icinde, haftaya).",
                        },
                    },
                    "required": ["description"],
                },
            },
            "sentiment": {
                "type": "string",
                "enum": ["positive", "neutral", "negative"],
            },
            "key_topics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "En fazla 8 anahtar konu/keyword.",
            },
            "competitor_mentions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "snippet": {"type": "string"},
                        "sentiment": {
                            "type": "string",
                            "enum": ["positive", "neutral", "negative"],
                        },
                    },
                    "required": ["name"],
                },
            },
            "objections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Musterinin dile getirdigi itirazlar / endiseler.",
            },
            "pricing_concerns": {"type": "array", "items": {"type": "string"}},
            "positive_signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Pozitif satinalma sinyalleri.",
            },
            "next_meeting_proposed": {
                "type": "string",
                "description": "Bir sonraki gorusme icin onerilen tarih ifadesi (varsa).",
            },
        },
        "required": ["summary", "sentiment", "key_topics"],
    },
}


# ── Public entrypoint ───────────────────────────────────────────────────────


@dataclass
class SummariseResult:
    summary: str
    action_items: list[dict[str, str]]
    sentiment: str
    key_topics: list[str]
    competitor_mentions: list[dict[str, str]]
    objections: list[str]
    pricing_concerns: list[str]
    positive_signals: list[str]
    next_meeting_proposed: str | None
    method: str  # "ai" | "rule_based"

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "action_items": self.action_items,
            "sentiment": self.sentiment,
            "key_topics": self.key_topics,
            "competitor_mentions": self.competitor_mentions,
            "objections": self.objections,
            "pricing_concerns": self.pricing_concerns,
            "positive_signals": self.positive_signals,
            "next_meeting_proposed": self.next_meeting_proposed,
            "method": self.method,
        }


async def summarize_transcript(db: AsyncSession, transcript_id: int) -> dict[str, Any]:
    """End-to-end summarise + signal emission.

    Safe to re-run: rewrites ``Transcript.summary`` / action items /
    sentiment, inserts new CompetitorMention rows, emits signals for
    pricing concerns and objections tied to ``Transcript.opportunity_id``.
    """
    transcript = await db.get(Transcript, transcript_id)
    if not transcript:
        return {"error": "Transkript bulunamadi"}

    content = (transcript.content or "").strip()
    if not content:
        return {"error": "Transkript bos"}

    keyword_hits = await _detect_keyword_mentions(db, content)

    if settings.ANTHROPIC_API_KEY:
        ai_result = await _claude_summarise(transcript, content)
        if ai_result is not None:
            result = ai_result
        else:
            result = _rule_based_summarise(transcript, content, keyword_hits)
    else:
        result = _rule_based_summarise(transcript, content, keyword_hits)

    # Merge keyword-detected competitor mentions with AI output so nothing is
    # lost when the keyword pack sees something the model missed.
    seen = {m["name"].lower() for m in result.competitor_mentions}
    for hit in keyword_hits.get("competitors", []):
        if hit["name"].lower() not in seen:
            result.competitor_mentions.append(
                {"name": hit["name"], "snippet": hit["snippet"], "sentiment": "neutral"}
            )

    # Persist on the transcript row.
    transcript.summary = result.summary
    transcript.action_items_json = json.dumps(result.action_items, ensure_ascii=False)
    transcript.sentiment = result.sentiment
    transcript.keywords_found = json.dumps(result.key_topics, ensure_ascii=False)

    await _persist_competitor_mentions(
        db,
        transcript_id=transcript.id,
        opportunity_id=transcript.opportunity_id,
        mentions=result.competitor_mentions,
    )
    await _emit_transcript_signals(
        db,
        transcript=transcript,
        result=result,
    )
    await db.flush()

    payload = result.to_dict()
    payload["transcript_id"] = transcript.id
    return payload


# ── Claude path (chunked when needed) ───────────────────────────────────────


async def _claude_summarise(transcript: Transcript, content: str) -> SummariseResult | None:
    try:
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=30.0)
    except Exception as exc:  # pragma: no cover
        logger.warning("Claude init failed: %s", exc)
        return None

    chunks = _chunk_content(content, CONTEXT_MAX_CHARS, CHUNK_OVERLAP)[:MERGE_MAX_CHUNKS]

    partials: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        result = await _summarise_one_chunk(client, transcript, chunk, idx, len(chunks))
        if result:
            partials.append(result)

    if not partials:
        return None

    merged = _merge_partials(partials)
    return SummariseResult(method="ai", **merged)


async def _summarise_one_chunk(
    client: AsyncAnthropic,
    transcript: Transcript,
    chunk: str,
    index: int,
    total: int,
) -> dict[str, Any] | None:
    trust_enabled = bool(settings.FEATURE_AI_TRUST_LAYER)
    trust_ctx: AITrustContext | None = None
    safe_chunk = chunk
    if trust_enabled:
        safe_chunk, trust_ctx = scrub(chunk)

    system_prompt = (
        "Sen Honeywell satis ekibinin gorusme ozet uzmanisin. Transkripti "
        "analiz et, rakip markalari (Siemens, Johnson Controls, Schneider, "
        "ABB, Honeywell, Danfoss, Carrier, Trane, York, Mitsubishi vb.) "
        "mumkun oldugunca eksiksiz yakala, itirazlari ve fiyat endiselerini "
        "ayri ayri cikar. Yanitini SADECE summarise_sales_call aracini "
        "cagirarak ver."
    )

    user_message = (
        f"Gorusme basligi: {transcript.title}\n"
        f"Katilimcilar: {transcript.participants or 'Bilinmiyor'}\n"
        f"Sure: {transcript.duration_minutes or 'Bilinmiyor'} dk\n"
        f"Bolum {index + 1}/{total}\n"
        "────────\n"
        f"{safe_chunk}"
    )

    try:
        response = await client.messages.create(
            model=settings.AI_MODEL_NAME,
            max_tokens=min(settings.AI_MAX_TOKENS, 1024),
            system=system_prompt,
            tools=[_SUMMARY_TOOL],
            tool_choice={"type": "tool", "name": "summarise_sales_call"},
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:  # pragma: no cover - transport errors
        logger.warning("Claude transcript call failed: %s", exc)
        return None

    for block in response.content:
        if block.type == "tool_use" and block.name == "summarise_sales_call":
            payload = dict(block.input or {})
            if trust_ctx is not None and trust_ctx.is_dirty():
                payload = _unscrub_payload(payload, trust_ctx)
                logger.info(
                    "transcript.ai_trust.audit %s",
                    audit_record(trust_ctx, prompt=chunk, model=settings.AI_MODEL_NAME),
                )
            return _normalise_partial(payload)
    return None


def _normalise_partial(payload: dict[str, Any]) -> dict[str, Any]:
    sentiment = payload.get("sentiment")
    if sentiment not in {"positive", "neutral", "negative"}:
        sentiment = "neutral"
    return {
        "summary": (payload.get("summary") or "").strip(),
        "action_items": _coerce_action_items(payload.get("action_items") or []),
        "sentiment": sentiment,
        "key_topics": [str(t) for t in (payload.get("key_topics") or [])][:8],
        "competitor_mentions": [
            {
                "name": str(m.get("name") or "").strip(),
                "snippet": str(m.get("snippet") or "").strip(),
                "sentiment": m.get("sentiment") if m.get("sentiment") in {"positive", "neutral", "negative"} else "neutral",
            }
            for m in (payload.get("competitor_mentions") or [])
            if m.get("name")
        ],
        "objections": [str(o) for o in (payload.get("objections") or [])],
        "pricing_concerns": [str(p) for p in (payload.get("pricing_concerns") or [])],
        "positive_signals": [str(s) for s in (payload.get("positive_signals") or [])],
        "next_meeting_proposed": (payload.get("next_meeting_proposed") or None),
    }


def _coerce_action_items(raw: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            description = str(item.get("description") or "").strip()
            if not description:
                continue
            out.append(
                {
                    "description": description,
                    "owner": str(item.get("owner") or "ekip"),
                    "due_hint": str(item.get("due_hint") or ""),
                }
            )
        elif isinstance(item, str) and item.strip():
            out.append({"description": item.strip(), "owner": "ekip", "due_hint": ""})
    return out[:12]


def _unscrub_payload(value: Any, ctx: AITrustContext) -> Any:
    if isinstance(value, str):
        return unscrub(value, ctx)
    if isinstance(value, list):
        return [_unscrub_payload(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: _unscrub_payload(v, ctx) for k, v in value.items()}
    return value


def _merge_partials(partials: list[dict[str, Any]]) -> dict[str, Any]:
    if len(partials) == 1:
        return partials[0]

    summaries = [p["summary"] for p in partials if p.get("summary")]
    merged_summary = " ".join(summaries)
    if len(merged_summary) > 1200:
        merged_summary = merged_summary[:1197] + "…"

    def _flatten_unique(key: str) -> list:
        seen: set[str] = set()
        out: list = []
        for part in partials:
            for item in part.get(key) or []:
                marker = item if isinstance(item, str) else json.dumps(item, sort_keys=True)
                if marker in seen:
                    continue
                seen.add(marker)
                out.append(item)
        return out

    sentiments = [p.get("sentiment") for p in partials]
    if sentiments.count("negative") > sentiments.count("positive"):
        sentiment = "negative"
    elif sentiments.count("positive") > sentiments.count("negative"):
        sentiment = "positive"
    else:
        sentiment = "neutral"

    return {
        "summary": merged_summary or "Ozet olusturulamadi.",
        "action_items": _flatten_unique("action_items")[:12],
        "sentiment": sentiment,
        "key_topics": _flatten_unique("key_topics")[:8],
        "competitor_mentions": _flatten_unique("competitor_mentions"),
        "objections": _flatten_unique("objections"),
        "pricing_concerns": _flatten_unique("pricing_concerns"),
        "positive_signals": _flatten_unique("positive_signals"),
        "next_meeting_proposed": next(
            (p.get("next_meeting_proposed") for p in partials if p.get("next_meeting_proposed")),
            None,
        ),
    }


# ── Rule-based fallback ─────────────────────────────────────────────────────


def _rule_based_summarise(
    transcript: Transcript,
    content: str,
    keyword_hits: dict[str, list[dict[str, str]]],
) -> SummariseResult:
    sentences = [s.strip() for s in re.split(r"[.!?]+", content) if s.strip()]
    summary_sentences = sentences[:5]
    summary = ". ".join(summary_sentences)
    if summary and not summary.endswith("."):
        summary += "."
    summary = summary[:600] or "Ozet olusturulamadi."

    action_keywords = (
        "yapilacak", "gonderilecek", "hazirlanacak", "aranacak", "planlanacak",
        "kontrol edilecek", "takip", "follow up", "todo", "action",
        "yapmaliyiz", "gondermeliyiz", "teklif gonder", "randevu",
    )
    actions: list[dict[str, str]] = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(kw in lowered for kw in action_keywords):
            actions.append({"description": sentence, "owner": "ekip", "due_hint": ""})
    actions = actions[:8]

    objections = [
        s for s in sentences
        if re.search(r"\b(pahal[ıi]|bütçe|butce|rakip|alternatif|gec[ik]|gecikme|endise|sorun|problem|itiraz)\b", s.lower())
    ][:5]

    pricing_concerns = [
        s for s in sentences
        if re.search(r"\b(pahal[ıi]|indirim|iskonto|fiyat|bütçe|butce|marj)\b", s.lower())
    ][:5]

    positive_signals = [
        s for s in sentences
        if re.search(r"\b(ilgilen|almak isti|satın al|siparis|onay|kabul|mukemmel|harika|imzal)\b", s.lower())
    ][:5]

    content_lower = content.lower()
    positive_words = ("memnun", "guzel", "basarili", "iyi", "harika", "olumlu", "anlast")
    negative_words = ("sorun", "sikayet", "olumsuz", "kotu", "pahali", "gecikme", "iptal")
    positive_count = sum(content_lower.count(w) for w in positive_words)
    negative_count = sum(content_lower.count(w) for w in negative_words)
    if positive_count > negative_count:
        sentiment = "positive"
    elif negative_count > positive_count:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return SummariseResult(
        summary=summary,
        action_items=actions,
        sentiment=sentiment,
        key_topics=_extract_key_topics(content),
        competitor_mentions=keyword_hits.get("competitors", []),
        objections=objections,
        pricing_concerns=pricing_concerns,
        positive_signals=positive_signals,
        next_meeting_proposed=None,
        method="rule_based",
    )


def _extract_key_topics(content: str) -> list[str]:
    stop_words = {
        "bir", "bu", "su", "ve", "ile", "icin", "olan", "var", "yok",
        "ben", "sen", "biz", "siz", "ama", "fakat", "cunku", "eger",
        "the", "and", "for", "with", "this", "that", "from", "are",
        "was", "were", "have", "has", "her", "onun", "biz",
    }
    words = re.findall(r"[a-zçğıöşüâîû]+", content.lower())
    counts: dict[str, int] = {}
    for word in words:
        if len(word) <= 3 or word in stop_words:
            continue
        counts[word] = counts.get(word, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:8]]


# ── Keyword-pack detection (competitor, pricing, objection, positive) ───────


async def _detect_keyword_mentions(
    db: AsyncSession, content: str
) -> dict[str, list[dict[str, str]]]:
    """Scan content for keywords coming from active KeywordPacks."""
    packs = (
        await db.execute(
            select(KeywordPack).where(KeywordPack.is_active.is_(True))
        )
    ).scalars().all()

    hits: dict[str, list[dict[str, str]]] = {
        "competitors": [],
        "objection": [],
        "pricing": [],
        "positive": [],
    }
    lowered = content.lower()
    for pack in packs:
        try:
            keywords = json.loads(pack.keywords_json) if pack.keywords_json else []
        except json.JSONDecodeError:
            continue
        bucket = "competitors" if pack.category == "competitor" else pack.category
        bucket = bucket if bucket in hits else "competitors"
        for keyword in keywords:
            kw = str(keyword).lower().strip()
            if not kw:
                continue
            idx = lowered.find(kw)
            if idx < 0:
                continue
            snippet = content[max(0, idx - 60) : idx + len(kw) + 60]
            hits[bucket].append({"name": keyword, "snippet": snippet.strip()})
    return hits


# ── Persistence helpers ─────────────────────────────────────────────────────


async def _persist_competitor_mentions(
    db: AsyncSession,
    *,
    transcript_id: int,
    opportunity_id: int | None,
    mentions: list[dict[str, str]],
) -> None:
    if not mentions:
        return

    # Dedupe against existing rows for this transcript.
    existing = {
        m.competitor_name.lower()
        for m in (
            await db.execute(
                select(CompetitorMention).where(
                    CompetitorMention.source_entity_type == "transcript",
                    CompetitorMention.source_entity_id == transcript_id,
                )
            )
        ).scalars().all()
    }

    for mention in mentions:
        name = (mention.get("name") or "").strip()
        if not name or name.lower() in existing:
            continue
        db.add(
            CompetitorMention(
                competitor_name=name,
                source_entity_type="transcript",
                source_entity_id=transcript_id,
                opportunity_id=opportunity_id,
                context_snippet=(mention.get("snippet") or "")[:500],
                sentiment=mention.get("sentiment") or "neutral",
                detected_by="ai" if mention.get("sentiment") else "keyword",
            )
        )
        existing.add(name.lower())


async def _emit_transcript_signals(
    db: AsyncSession,
    *,
    transcript: Transcript,
    result: SummariseResult,
) -> None:
    """Translate transcript findings into canonical Revenue Signals."""
    from app.services.revenue_signal_service import emit_signal

    if transcript.opportunity_id is None:
        return

    opp_id = transcript.opportunity_id

    for concern in result.pricing_concerns[:3]:
        await emit_signal(
            db,
            signal_type="pricing_concern",
            source_entity_type="transcript",
            source_entity_id=transcript.id,
            opportunity_id=opp_id,
            severity="med",
            confidence=0.7,
            recommended_action=(
                "Görüşmede fiyat endişesi dile getirildi: "
                f"{concern[:140]}"
            ),
            metadata={"transcript_id": transcript.id, "detail": concern},
            event_key=f"pricing:{transcript.id}:{hash(concern) % 1_000_000}",
        )

    for objection in result.objections[:3]:
        await emit_signal(
            db,
            signal_type="objection_raised",
            source_entity_type="transcript",
            source_entity_id=transcript.id,
            opportunity_id=opp_id,
            severity="med",
            confidence=0.7,
            recommended_action=(
                "Müşteri itirazı yakalandı: " f"{objection[:140]}"
            ),
            metadata={"transcript_id": transcript.id, "detail": objection},
            event_key=f"objection:{transcript.id}:{hash(objection) % 1_000_000}",
        )

    for mention in result.competitor_mentions[:3]:
        name = (mention.get("name") or "").strip()
        if not name:
            continue
        severity = "high" if mention.get("sentiment") == "positive" else "med"
        await emit_signal(
            db,
            signal_type="competitor_mention",
            source_entity_type="transcript",
            source_entity_id=transcript.id,
            opportunity_id=opp_id,
            severity=severity,
            confidence=0.75,
            recommended_action=(
                f"Rakip algılandı: {name}. Battle card + farklılaşma mesajı hazırlayın."
            ),
            metadata={
                "transcript_id": transcript.id,
                "competitor": name,
                "snippet": mention.get("snippet"),
                "sentiment": mention.get("sentiment"),
            },
            event_key=f"competitor:{transcript.id}:{name.lower()}",
        )

    for signal in result.positive_signals[:2]:
        await emit_signal(
            db,
            signal_type="buying_signal",
            source_entity_type="transcript",
            source_entity_id=transcript.id,
            opportunity_id=opp_id,
            severity="low",
            confidence=0.75,
            recommended_action=(
                "Pozitif satınalma sinyali: teklifi hızlandırın."
            ),
            metadata={"transcript_id": transcript.id, "detail": signal},
            event_key=f"positive:{transcript.id}:{hash(signal) % 1_000_000}",
        )


# ── Content chunking ────────────────────────────────────────────────────────


def _chunk_content(text: str, window: int, overlap: int) -> list[str]:
    """Split ``text`` into overlapping windows so chunk edges keep context."""
    if len(text) <= window:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + window)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks
