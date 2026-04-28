"""NL search service (V9).

Cosine-similarity search over the V8 text embeddings, plus a hybrid
mode that blends embedding score with keyword match. Closes the V2
ConversationSearch (Salesforce mapping #6) gap from text-match-only
to genuine semantic search.

Three corpora are supported:
- ``opportunities`` — uses ``opportunity_text_embeddings`` (V8)
- ``transcripts`` — uses ``transcript_embeddings`` (V9)
- ``emails`` — uses ``email_embeddings`` (V9)

The query embedder is the same V8 ``text_embedder`` so the vector
space is shared. Empty queries short-circuit to ``[]``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_request import EmailRequest
from app.models.engagement import Transcript
from app.models.opportunity import Opportunity
from app.models.v5_similarity import OpportunityEmbedding  # noqa: F401 — wire later
from app.models.v8_text_embedding import OpportunityTextEmbedding
from app.models.v9_nl_search import EmailEmbedding, TranscriptEmbedding
from app.services import text_embedder

logger = logging.getLogger(__name__)


# ─────────────────────── helpers ─────────────────────────────────────


_TOKEN_RE = re.compile(r"[a-zçğıöşü0-9_]+", re.IGNORECASE)


def _tokenize_query(query: str) -> list[str]:
    """Lowercase token split — same vocabulary the embedder hashes over."""
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(query)]


def _embed_query(query: str) -> list[float]:
    return text_embedder.embed_tokens(_tokenize_query(query))


def _keyword_score(query: str, text: str | None) -> float:
    """Cheap lexical overlap as a 0..1 signal for the hybrid blend."""
    if not text:
        return 0.0
    q_tokens = set(_tokenize_query(query))
    if not q_tokens:
        return 0.0
    t_tokens = set(_tokenize_query(text))
    if not t_tokens:
        return 0.0
    return round(len(q_tokens & t_tokens) / len(q_tokens), 4)


@dataclass
class SearchHit:
    entity_type: str
    entity_id: int
    title: str
    snippet: str | None
    embedding_score: float
    keyword_score: float
    blended_score: float


def _blend(emb: float, kw: float, *, w_emb: float = 0.7, w_kw: float = 0.3) -> float:
    return round(w_emb * emb + w_kw * kw, 4)


# ─────────────────────── corpus searchers ────────────────────────────


async def _search_opportunities(
    db: AsyncSession, *, query_vec: list[float], query_text: str, limit: int
) -> list[SearchHit]:
    rows = (
        await db.execute(
            select(OpportunityTextEmbedding, Opportunity)
            .join(
                Opportunity,
                Opportunity.id == OpportunityTextEmbedding.opportunity_id,
            )
        )
    ).all()
    hits: list[SearchHit] = []
    for emb, opp in rows:
        try:
            vec = json.loads(emb.embedding_json)
        except (json.JSONDecodeError, TypeError):
            continue
        emb_score = text_embedder.cosine(query_vec, vec)
        kw_score = _keyword_score(query_text, opp.title)
        blended = _blend(emb_score, kw_score)
        hits.append(
            SearchHit(
                entity_type="opportunity",
                entity_id=int(opp.id),
                title=opp.title or f"Opportunity #{opp.id}",
                snippet=None,
                embedding_score=emb_score,
                keyword_score=kw_score,
                blended_score=blended,
            )
        )
    hits.sort(key=lambda h: -h.blended_score)
    return hits[:limit]


async def _search_transcripts(
    db: AsyncSession, *, query_vec: list[float], query_text: str, limit: int
) -> list[SearchHit]:
    rows = (
        await db.execute(
            select(TranscriptEmbedding, Transcript).join(
                Transcript, Transcript.id == TranscriptEmbedding.transcript_id
            )
        )
    ).all()
    hits: list[SearchHit] = []
    for emb, tr in rows:
        try:
            vec = json.loads(emb.embedding_json)
        except (json.JSONDecodeError, TypeError):
            continue
        emb_score = text_embedder.cosine(query_vec, vec)
        body = (tr.summary or "") + " " + (tr.content or "")
        kw_score = _keyword_score(query_text, body)
        blended = _blend(emb_score, kw_score)
        hits.append(
            SearchHit(
                entity_type="transcript",
                entity_id=int(tr.id),
                title=tr.title or f"Transcript #{tr.id}",
                snippet=(tr.summary or tr.content or "")[:200] if (tr.summary or tr.content) else None,
                embedding_score=emb_score,
                keyword_score=kw_score,
                blended_score=blended,
            )
        )
    hits.sort(key=lambda h: -h.blended_score)
    return hits[:limit]


async def _search_emails(
    db: AsyncSession, *, query_vec: list[float], query_text: str, limit: int
) -> list[SearchHit]:
    rows = (
        await db.execute(
            select(EmailEmbedding, EmailRequest).join(
                EmailRequest, EmailRequest.id == EmailEmbedding.email_request_id
            )
        )
    ).all()
    hits: list[SearchHit] = []
    for emb, em in rows:
        try:
            vec = json.loads(emb.embedding_json)
        except (json.JSONDecodeError, TypeError):
            continue
        emb_score = text_embedder.cosine(query_vec, vec)
        kw_score = _keyword_score(
            query_text,
            (getattr(em, "subject", None) or "") + " " + (getattr(em, "body", None) or ""),
        )
        blended = _blend(emb_score, kw_score)
        hits.append(
            SearchHit(
                entity_type="email",
                entity_id=int(em.id),
                title=getattr(em, "subject", None) or f"Email #{em.id}",
                snippet=None,
                embedding_score=emb_score,
                keyword_score=kw_score,
                blended_score=blended,
            )
        )
    hits.sort(key=lambda h: -h.blended_score)
    return hits[:limit]


# ─────────────────────── public entry point ──────────────────────────


_DEFAULT_SCOPES = ("opportunities", "transcripts", "emails")


async def semantic_search(
    db: AsyncSession,
    *,
    query: str,
    scopes: Iterable[str] | None = None,
    limit_per_scope: int = 10,
) -> list[dict]:
    """Run a hybrid semantic + keyword search.

    Returns a flat list of dicts (not SearchHit objects) sorted by
    ``blended_score`` desc so the API layer can serialise straight
    through.
    """
    if not query or not query.strip():
        return []
    query_vec = _embed_query(query)
    if not any(v != 0 for v in query_vec):
        # Empty token vocabulary → fall back to keyword-only.
        query_vec = []

    scopes_set = set(scopes or _DEFAULT_SCOPES)
    all_hits: list[SearchHit] = []
    if "opportunities" in scopes_set:
        all_hits += await _search_opportunities(
            db, query_vec=query_vec, query_text=query, limit=limit_per_scope
        )
    if "transcripts" in scopes_set:
        all_hits += await _search_transcripts(
            db, query_vec=query_vec, query_text=query, limit=limit_per_scope
        )
    if "emails" in scopes_set:
        all_hits += await _search_emails(
            db, query_vec=query_vec, query_text=query, limit=limit_per_scope
        )

    all_hits.sort(key=lambda h: -h.blended_score)
    return [
        {
            "entity_type": h.entity_type,
            "entity_id": h.entity_id,
            "title": h.title,
            "snippet": h.snippet,
            "embedding_score": h.embedding_score,
            "keyword_score": h.keyword_score,
            "blended_score": h.blended_score,
        }
        for h in all_hits
        if h.blended_score > 0
    ]


# ─────────────────────── embedding upserts ───────────────────────────


async def upsert_transcript_embedding(
    db: AsyncSession, *, transcript_id: int
) -> TranscriptEmbedding | None:
    tr = await db.get(Transcript, transcript_id)
    if tr is None:
        return None
    body = (tr.summary or "") + " " + (tr.content or "")
    tokens = _tokenize_query(body)
    if not tokens:
        return None
    vec = text_embedder.embed_tokens(tokens)
    if not any(v != 0 for v in vec):
        return None

    row = await db.get(TranscriptEmbedding, transcript_id)
    payload = json.dumps(vec)
    vh = text_embedder.vocab_hash(tokens)
    if row is None:
        row = TranscriptEmbedding(
            transcript_id=transcript_id,
            embedding_json=payload,
            dim=text_embedder.DEFAULT_DIM,
            version=text_embedder.VERSION,
            vocab_hash=vh,
        )
        db.add(row)
    else:
        row.embedding_json = payload
        row.dim = text_embedder.DEFAULT_DIM
        row.version = text_embedder.VERSION
        row.vocab_hash = vh
    await db.flush()
    return row


async def upsert_email_embedding(
    db: AsyncSession, *, email_request_id: int
) -> EmailEmbedding | None:
    em = await db.get(EmailRequest, email_request_id)
    if em is None:
        return None
    body = (
        (getattr(em, "subject", None) or "")
        + " "
        + (getattr(em, "body", None) or "")
        + " "
        + (getattr(em, "raw_text", None) or "")
    )
    tokens = _tokenize_query(body)
    if not tokens:
        return None
    vec = text_embedder.embed_tokens(tokens)
    if not any(v != 0 for v in vec):
        return None

    row = await db.get(EmailEmbedding, email_request_id)
    payload = json.dumps(vec)
    vh = text_embedder.vocab_hash(tokens)
    if row is None:
        row = EmailEmbedding(
            email_request_id=email_request_id,
            embedding_json=payload,
            dim=text_embedder.DEFAULT_DIM,
            version=text_embedder.VERSION,
            vocab_hash=vh,
        )
        db.add(row)
    else:
        row.embedding_json = payload
        row.dim = text_embedder.DEFAULT_DIM
        row.version = text_embedder.VERSION
        row.vocab_hash = vh
    await db.flush()
    return row
