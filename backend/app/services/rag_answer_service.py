"""RAG-augmented answer service (V11).

Retrieve-then-generate pattern: fetch top-K snippets from Qdrant,
build a structured Claude prompt that includes them as context, and
return a typed envelope with answer + citations + confidence.

Failure modes:
- ``FEATURE_RAG=false``           → returns disabled-style envelope
- ``ANTHROPIC_API_KEY`` missing   → falls back to retrieval-only
- Claude breaker open             → falls back to retrieval-only
- Empty retrieval                 → returns "I don't have enough context"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable

from app.core.circuit_breaker import CircuitOpenError
from app.core.claude_client import claude_messages_create
from app.core.config import settings
from app.services.llm_json import parse_claude_json

logger = logging.getLogger(__name__)


_MAX_CONTEXT_CHARS = 8000  # safety cap for the Claude prompt


@dataclass
class RagAnswer:
    answer: str
    citations: list[dict[str, Any]]
    confidence: float
    used_collections: list[str]
    fallback_reason: str | None = None


_SYSTEM_PROMPT = (
    "You are an enterprise sales analyst. Answer the question using "
    "ONLY the provided context. If the context is insufficient, say so "
    "clearly in Turkish. Always return JSON: "
    '{"answer": "...", "confidence": 0.0-1.0, '
    '"used_citation_ids": [int]}. '
    "Answer in the same language as the question."
)


# ─────────────────────── retrieval ──────────────────────────────────


async def _retrieve(
    *,
    question: str,
    scope: Iterable[str],
    limit: int,
    customer_id: int | None,
    competitor: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Pull snippets from Qdrant collections per scope. Returns (rows, used_collections)."""
    from app.services.vector_store import (
        find_competitor_intel,
        find_similar_deals,
        find_similar_interactions,
    )

    rows: list[dict[str, Any]] = []
    used: list[str] = []
    scope_set = set(scope)

    if "deals" in scope_set:
        deal_rows = await find_similar_deals(question, limit=limit)
        for r in deal_rows:
            rows.append({"source": "deal", "score": r.get("score", 0.0), **r})
        used.append("deals")

    if "interactions" in scope_set:
        inter_rows = await find_similar_interactions(question, limit=limit, customer_id=customer_id)
        for r in inter_rows:
            rows.append({"source": "interaction", "score": r.get("score", 0.0), **r})
        used.append("interactions")

    if "competitors" in scope_set:
        comp_name = competitor or _extract_competitor_hint(question)
        if comp_name:
            comp_rows = await find_competitor_intel(comp_name, query=question, limit=limit)
            for r in comp_rows:
                rows.append({"source": "competitor", "score": r.get("score", 0.0), **r})
            used.append("competitors")

    rows.sort(key=lambda r: -float(r.get("score", 0.0)))
    return rows, used


def _extract_competitor_hint(text: str) -> str | None:
    """Cheap heuristic — pick a known competitor name from the question."""
    if not text:
        return None
    needle = text.lower()
    for c in ("siemens", "schneider", "abb", "johnson controls", "mitsubishi", "rockwell"):
        if c in needle:
            return c.title()
    return None


# ─────────────────────── prompt build ───────────────────────────────


def _build_prompt(question: str, rows: list[dict[str, Any]]) -> str:
    """Assemble the user prompt with numbered citations."""
    lines = [f"Question: {question}", "", "Context:"]
    consumed = 0
    for i, r in enumerate(rows[:8], start=1):
        snippet = (
            r.get("summary")
            or r.get("content_snippet")
            or r.get("title")
            or ""
        )
        snippet = str(snippet).strip()
        if not snippet:
            continue
        meta = []
        if r.get("source") == "deal":
            meta.append(f"deal #{r.get('deal_id')}")
            if r.get("outcome"):
                meta.append(f"outcome={r['outcome']}")
            if r.get("stage"):
                meta.append(f"stage={r['stage']}")
        elif r.get("source") == "interaction":
            meta.append(f"interaction #{r.get('interaction_id')}")
            if r.get("type"):
                meta.append(f"type={r['type']}")
        elif r.get("source") == "competitor":
            meta.append(f"competitor={r.get('competitor', '')}")
            if r.get("source_url"):
                meta.append(f"src={r['source_url']}")
        block = f"[{i}] ({', '.join(meta)}) {snippet[:600]}"
        if consumed + len(block) > _MAX_CONTEXT_CHARS:
            break
        lines.append(block)
        consumed += len(block)
    lines.append("")
    lines.append("Answer in JSON.")
    return "\n".join(lines)


# ─────────────────────── public entry point ─────────────────────────


_DEFAULT_SCOPE = ("deals", "interactions", "competitors")


async def answer_question(
    *,
    question: str,
    scope: Iterable[str] | None = None,
    limit: int = 5,
    customer_id: int | None = None,
    competitor: str | None = None,
) -> RagAnswer:
    if not question or not question.strip():
        return RagAnswer(
            answer="",
            citations=[],
            confidence=0.0,
            used_collections=[],
            fallback_reason="empty_question",
        )

    if not settings.FEATURE_RAG:
        return RagAnswer(
            answer="RAG sistemi bu deployment'ta kapalı.",
            citations=[],
            confidence=0.0,
            used_collections=[],
            fallback_reason="feature_disabled",
        )

    rows, used = await _retrieve(
        question=question,
        scope=scope or _DEFAULT_SCOPE,
        limit=limit,
        customer_id=customer_id,
        competitor=competitor,
    )

    citations = [
        {
            "id": i + 1,
            "source": r.get("source"),
            "score": round(float(r.get("score", 0.0)), 3),
            "snippet": (r.get("summary") or r.get("content_snippet") or r.get("title") or "")[:300],
            "metadata": {k: v for k, v in r.items() if k not in {"score", "source", "summary", "content_snippet", "title"}},
        }
        for i, r in enumerate(rows[:8])
    ]

    if not rows:
        return RagAnswer(
            answer="Bu soruyu yanıtlamak için yeterli geçmiş veri yok.",
            citations=[],
            confidence=0.0,
            used_collections=used,
            fallback_reason="empty_retrieval",
        )

    if not settings.ANTHROPIC_API_KEY:
        return RagAnswer(
            answer="Claude yapılandırılmadığı için sadece geri çağrılan kaynaklar listeleniyor.",
            citations=citations,
            confidence=round(min(1.0, len(rows) / 5.0), 2),
            used_collections=used,
            fallback_reason="claude_not_configured",
        )

    prompt = _build_prompt(question, rows)
    try:
        response = await claude_messages_create(
            model=settings.AI_MODEL_NAME,
            max_tokens=600,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except CircuitOpenError as exc:
        logger.warning("RAG answer: Claude breaker open (%s)", exc)
        return RagAnswer(
            answer="Claude şu anda devre dışı; sadece geri çağrılan kaynaklar mevcut.",
            citations=citations,
            confidence=round(min(1.0, len(rows) / 5.0), 2),
            used_collections=used,
            fallback_reason="claude_breaker_open",
        )
    except Exception as exc:
        logger.warning("RAG answer: Claude call failed (%s)", exc)
        return RagAnswer(
            answer="Claude çağrısı başarısız oldu; sadece kaynaklar gösteriliyor.",
            citations=citations,
            confidence=round(min(1.0, len(rows) / 5.0), 2),
            used_collections=used,
            fallback_reason="claude_error",
        )

    body = response.content[0].text if response.content else None
    parsed = parse_claude_json(body)
    if parsed is None or "answer" not in parsed:
        return RagAnswer(
            answer="Yapılandırılmış cevap üretilemedi; kaynaklara bakın.",
            citations=citations,
            confidence=0.3,
            used_collections=used,
            fallback_reason="parse_failed",
        )

    confidence = float(parsed.get("confidence") or 0.5)
    used_ids = parsed.get("used_citation_ids") or []
    if isinstance(used_ids, list):
        kept_citations = [c for c in citations if c["id"] in set(used_ids)]
    else:
        kept_citations = citations

    return RagAnswer(
        answer=str(parsed["answer"])[:4000],
        citations=kept_citations or citations,
        confidence=max(0.0, min(1.0, confidence)),
        used_collections=used,
    )
