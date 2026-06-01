"""Deal similarity service (V5).

Per-opportunity structured-feature embedding + cosine similarity.

This is the rule-based MVP — we hand-craft a feature vector from the
existing ``OpportunityFeaturesDaily`` row + opportunity dimensions
rather than running a learned encoder. The interface is stable so we
can swap in an LLM/text embedding later by replacing
``build_embedding`` and incrementing ``EMBEDDING_VERSION``.

Vector layout (8 dims, all normalized to ~[0,1]):
    0  amount_band_score        (deal size bucket)
    1  size_band_score          (employee count bucket)
    2  momentum_norm            (momentum_score / 100)
    3  stakeholder_norm         (stakeholder_count / 8, capped)
    4  followup_norm            (1 - clamp(days_since_rep_touch/14))
    5  buyer_engagement_norm    (buyer_reply_count_14d / 5, capped)
    6  discount_norm            (latest_discount_pct / 50, capped)
    7  industry_hash_norm       (stable hash of industry → [0,1])
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.buyer_state_history import BuyerStateHistory
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity
from app.models.sequence_v2 import Stakeholder
from app.models.v5_objection import Objection
from app.models.v5_similarity import DealSimilarityLink, OpportunityEmbedding

logger = logging.getLogger(__name__)


EMBEDDING_VERSION = "v6-trajectory-1"
EMBEDDING_DIM = 12


# ─────────────────────── helper buckets ──────────────────────────────


_AMOUNT_BUCKETS: tuple[tuple[float, float], ...] = (
    (50_000, 0.2),
    (200_000, 0.4),
    (1_000_000, 0.7),
    (float("inf"), 1.0),
)


def _amount_score(amount: float | None) -> float:
    if amount is None or amount <= 0:
        return 0.0
    for upper, score in _AMOUNT_BUCKETS:
        if amount < upper:
            return score
    return 1.0


def _size_score(employee_count: int | None) -> float:
    if employee_count is None or employee_count <= 0:
        return 0.0
    if employee_count < 50:
        return 0.25
    if employee_count < 500:
        return 0.6
    return 1.0


def _industry_hash(industry: str | None) -> float:
    if not industry:
        return 0.0
    digest = hashlib.md5(
        industry.lower().encode("utf-8"), usedforsecurity=False
    ).hexdigest()
    # First 4 hex chars → [0..1]
    return int(digest[:4], 16) / 0xFFFF


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ─────────────────────── embedding builder ──────────────────────────


async def build_embedding(
    db: AsyncSession, *, opportunity_id: int
) -> list[float] | None:
    """Build the V6 12-dim feature vector for one opportunity.

    Layout: 8 V5 point-in-time dims + 4 V6 trajectory dims:

    - dim 8  ``stage_velocity_norm``  — clamp(stage_velocity_days / 30)
    - dim 9  ``momentum_trend_norm``  — Δmomentum mean over last 14d → [0,1]
    - dim 10 ``buyer_state_changes_norm`` — distinct buyer_states / 5
    - dim 11 ``objection_density_norm`` — open_objections / 5

    Returns ``None`` when the opportunity is missing.
    """
    opp = await db.get(Opportunity, opportunity_id)
    if opp is None:
        return None
    ofd = (
        await db.execute(
            select(OpportunityFeaturesDaily)
            .where(OpportunityFeaturesDaily.opportunity_id == opportunity_id)
            .order_by(OpportunityFeaturesDaily.snapshot_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    sh_count = (
        await db.execute(
            select(func.count(Stakeholder.id)).where(
                Stakeholder.opportunity_id == opportunity_id
            )
        )
    ).scalar() or 0

    momentum = float(ofd.momentum_score) / 100.0 if ofd and ofd.momentum_score else 0.0
    days_since = float(ofd.days_since_last_rep_touch) if ofd else 999.0
    followup = 1.0 - _clamp(days_since / 14.0)
    buyer_engagement = _clamp(float(ofd.buyer_reply_count_14d if ofd else 0) / 5.0)
    discount = _clamp(float(ofd.latest_discount_pct or 0) / 50.0) if ofd else 0.0
    stakeholder_norm = _clamp(float(sh_count) / 8.0)

    # ── V6 trajectory dims ──
    stage_velocity_norm = (
        _clamp(float(ofd.stage_velocity_days) / 30.0)
        if ofd and ofd.stage_velocity_days is not None
        else 0.0
    )

    # 14-day momentum trend: mean(Δmomentum) → centred at 0.5 because
    # 0 means "no change", positive means improving, negative declining.
    recent_ofd = (
        await db.execute(
            select(OpportunityFeaturesDaily.momentum_score)
            .where(OpportunityFeaturesDaily.opportunity_id == opportunity_id)
            .order_by(OpportunityFeaturesDaily.snapshot_date.desc())
            .limit(14)
        )
    ).scalars().all()
    deltas = [
        (recent_ofd[i] or 0) - (recent_ofd[i + 1] or 0)
        for i in range(len(recent_ofd) - 1)
        if recent_ofd[i] is not None and recent_ofd[i + 1] is not None
    ]
    if deltas:
        mean_delta = sum(deltas) / len(deltas)
        # Normalize: ±20 momentum points → [0, 1]
        momentum_trend_norm = _clamp(0.5 + (mean_delta / 40.0))
    else:
        momentum_trend_norm = 0.5

    # buyer_state_changes_norm — diversity of buyer states seen in history
    state_count = (
        await db.execute(
            select(func.count(func.distinct(BuyerStateHistory.state))).where(
                BuyerStateHistory.opportunity_id == opportunity_id
            )
        )
    ).scalar() or 0
    buyer_state_changes_norm = _clamp(float(state_count) / 5.0)

    # objection_density_norm — open objections / 5 (capped)
    open_obj = (
        await db.execute(
            select(func.count(Objection.id))
            .where(Objection.opportunity_id == opportunity_id)
            .where(Objection.resolved_flag.is_(False))
        )
    ).scalar() or 0
    objection_density_norm = _clamp(float(open_obj) / 5.0)

    return [
        _amount_score(opp.amount),
        _size_score(getattr(opp, "employee_count", None)),
        momentum,
        stakeholder_norm,
        followup,
        buyer_engagement,
        discount,
        _industry_hash(getattr(opp, "industry", None)),
        # V6 trajectory dims
        stage_velocity_norm,
        momentum_trend_norm,
        buyer_state_changes_norm,
        objection_density_norm,
    ]


async def upsert_embedding(
    db: AsyncSession, *, opportunity_id: int
) -> OpportunityEmbedding | None:
    vec = await build_embedding(db, opportunity_id=opportunity_id)
    if vec is None:
        return None
    existing = await db.get(OpportunityEmbedding, opportunity_id)
    if existing is None:
        # Round-15 Sprint 15o cohort 5 — opportunity_embeddings.tenant_id NOT NULL.
        from app.models.opportunity import Opportunity
        opp_tenant_id = (
            await db.execute(
                select(Opportunity.tenant_id).where(Opportunity.id == opportunity_id)
            )
        ).scalar_one_or_none()
        row = OpportunityEmbedding(
            opportunity_id=opportunity_id,
            tenant_id=opp_tenant_id,
            embedding_json=json.dumps(vec),
            dim=EMBEDDING_DIM,
            version=EMBEDDING_VERSION,
        )
        db.add(row)
        await db.flush()
    else:
        existing.embedding_json = json.dumps(vec)
        existing.dim = EMBEDDING_DIM
        existing.version = EMBEDDING_VERSION
        existing.generated_at = datetime.now(timezone.utc)
        await db.flush()
        row = existing

    # V8: also upsert the text embedding so the similarity blend has
    # the third component available. Best-effort — failure here
    # doesn't roll back the structured embedding write.
    try:
        await upsert_text_embedding(db, opportunity_id=opportunity_id)
    except Exception as exc:
        logger.warning("v8 text embedding upsert failed opp=%s: %s", opportunity_id, exc)
    return row


async def upsert_text_embedding(
    db: AsyncSession, *, opportunity_id: int
) -> "OpportunityTextEmbedding | None":
    """V8: upsert the bigram-BoW text embedding for one opportunity."""
    from app.models.v8_text_embedding import OpportunityTextEmbedding
    from app.services import text_embedder

    tokens = await _tokens_for_opp(db, opportunity_id=opportunity_id)
    vec = text_embedder.embed_tokens(tokens)
    if not any(v != 0 for v in vec):
        # Empty token list → don't pollute the table with zero vectors.
        return None

    row = await db.get(OpportunityTextEmbedding, opportunity_id)
    payload = json.dumps(vec)
    vh = text_embedder.vocab_hash(tokens)
    if row is None:
        # Round-15 Sprint 15r cohort 8 — tenant_id NOT NULL.
        from app.models.opportunity import Opportunity
        opp_tenant_id = (
            await db.execute(
                select(Opportunity.tenant_id).where(Opportunity.id == opportunity_id)
            )
        ).scalar_one_or_none()
        row = OpportunityTextEmbedding(
            opportunity_id=opportunity_id,
            tenant_id=opp_tenant_id,
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
        row.generated_at = datetime.now(timezone.utc)
    await db.flush()
    return row


# ─────────────────────── similarity ───────────────────────────────────


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return round(dot / (norm_a * norm_b), 4)


async def _tokens_for_opp(db: AsyncSession, *, opportunity_id: int) -> list[str]:
    """Recompute V6 sequence tokens for an opportunity (best-effort)."""
    from datetime import timedelta

    from app.models.sales_event_shadow import SalesEventShadow
    from app.services.sequence_tokenizer import TokenizerContext, tokenize

    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    events = list(
        (
            await db.execute(
                select(SalesEventShadow)
                .where(SalesEventShadow.opportunity_id == opportunity_id)
                .where(SalesEventShadow.event_ts >= cutoff)
                .order_by(SalesEventShadow.event_ts.asc())
            )
        ).scalars()
    )
    if not events:
        return []

    sh_count = (
        await db.execute(
            select(func.count(Stakeholder.id)).where(
                Stakeholder.opportunity_id == opportunity_id
            )
        )
    ).scalar() or 0

    ofd = (
        await db.execute(
            select(OpportunityFeaturesDaily)
            .where(OpportunityFeaturesDaily.opportunity_id == opportunity_id)
            .order_by(OpportunityFeaturesDaily.snapshot_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    ctx = TokenizerContext(
        stakeholder_count=int(sh_count),
        decision_maker_count=int(ofd.decision_maker_count) if ofd else 0,
        latest_discount_pct=float(ofd.latest_discount_pct)
        if ofd and ofd.latest_discount_pct
        else None,
    )
    return list(tokenize(events, ctx))


async def refresh_similarity_links(
    db: AsyncSession, *, opportunity_id: int, top_k: int = 5, min_score: float = 0.7
) -> int:
    """Refresh the top-K similar deals for ``opportunity_id``.

    V12 (when ``FEATURE_TRANSFORMER_SEQ_EMBEDDING`` is on and both
    sides have a transformer vector): 4-component blend.
      ``final = 0.4·cos_struct + 0.15·LCS + 0.25·cos_text + 0.2·cos_xfm``

    V8 (when text vectors exist but transformer doesn't): 3-component blend.
      ``final = 0.5·cos_struct + 0.2·LCS + 0.3·cos_text``

    V7 fallback (only structured + LCS): ``blend_similarity`` with
    re-normalised weights summing to 1.
    """
    from app.core.config import settings
    from app.models.v8_text_embedding import OpportunityTextEmbedding
    from app.models.v12_transformer_seq_embedding import (
        OpportunityTransformerSeqEmbedding,
    )
    from app.services import text_embedder, transformer_sequence_embedder
    from app.services.sequence_similarity import blend_similarity, lcs_ratio

    own = await db.get(OpportunityEmbedding, opportunity_id)
    if own is None:
        return 0
    own_vec = json.loads(own.embedding_json)
    own_tokens = await _tokens_for_opp(db, opportunity_id=opportunity_id)
    own_text = await db.get(OpportunityTextEmbedding, opportunity_id)
    own_text_vec = json.loads(own_text.embedding_json) if own_text else None

    own_xfm_vec: list[float] | None = None
    if settings.FEATURE_TRANSFORMER_SEQ_EMBEDDING:
        own_xfm = await db.get(OpportunityTransformerSeqEmbedding, opportunity_id)
        if own_xfm is not None:
            try:
                own_xfm_vec = json.loads(own_xfm.embedding_json)
            except (json.JSONDecodeError, TypeError):
                own_xfm_vec = None

    others = (
        await db.execute(
            select(OpportunityEmbedding).where(
                OpportunityEmbedding.opportunity_id != opportunity_id
            )
        )
    ).scalars().all()

    scored: list[tuple[int, float, float, float, float, float]] = []
    for other in others:
        try:
            other_vec = json.loads(other.embedding_json)
        except (json.JSONDecodeError, TypeError):
            continue
        cos = cosine_similarity(own_vec, other_vec)
        if cos < min_score:
            continue
        other_tokens = await _tokens_for_opp(
            db, opportunity_id=int(other.opportunity_id)
        )
        seq = lcs_ratio(own_tokens, other_tokens)
        text_cos = 0.0
        if own_text_vec is not None:
            other_text = await db.get(
                OpportunityTextEmbedding, int(other.opportunity_id)
            )
            if other_text is not None:
                try:
                    other_text_vec = json.loads(other_text.embedding_json)
                    text_cos = text_embedder.cosine(own_text_vec, other_text_vec)
                except (json.JSONDecodeError, TypeError):
                    text_cos = 0.0

        xfm_cos = 0.0
        if own_xfm_vec is not None:
            other_xfm = await db.get(
                OpportunityTransformerSeqEmbedding, int(other.opportunity_id)
            )
            if other_xfm is not None:
                try:
                    other_xfm_vec = json.loads(other_xfm.embedding_json)
                    xfm_cos = transformer_sequence_embedder.cosine(
                        own_xfm_vec, other_xfm_vec
                    )
                except (json.JSONDecodeError, TypeError):
                    xfm_cos = 0.0

        if own_xfm_vec is not None and xfm_cos > 0.0:
            # V12 4-component blend.
            blended = round(
                0.4 * cos + 0.15 * seq + 0.25 * text_cos + 0.2 * xfm_cos, 4
            )
        elif own_text_vec is not None and text_cos > 0.0:
            # V8 3-component blend.
            blended = round(0.5 * cos + 0.2 * seq + 0.3 * text_cos, 4)
        else:
            # V7 fallback (re-normalised to sum=1).
            blended = blend_similarity(cos, seq)
        scored.append(
            (int(other.opportunity_id), blended, cos, seq, text_cos, xfm_cos)
        )
    scored.sort(key=lambda x: -x[1])
    top = scored[:top_k]

    # Refresh existing links for this opp.
    existing = (
        await db.execute(
            select(DealSimilarityLink).where(
                DealSimilarityLink.opportunity_id == opportunity_id
            )
        )
    ).scalars().all()
    for link in existing:
        await db.delete(link)
    await db.flush()

    # Round-15 Sprint 15q cohort 7 — deal_similarity_links.tenant_id NOT NULL.
    # One parent-opp lookup per refresh pass.
    link_tenant_id = (
        await db.execute(
            select(Opportunity.tenant_id).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()

    for sim_id, score, cos, seq, text_cos, xfm_cos in top:
        db.add(
            DealSimilarityLink(
                opportunity_id=opportunity_id,
                tenant_id=link_tenant_id,
                similar_opportunity_id=sim_id,
                similarity_score=score,
                similarity_reason_json=json.dumps(
                    {
                        "embedding_version": EMBEDDING_VERSION,
                        "method": "cosine+lcs+text+xfm"
                        if xfm_cos > 0.0
                        else "cosine+lcs+text",
                        "cosine_score": cos,
                        "sequence_score": seq,
                        "text_score": text_cos,
                        "transformer_score": xfm_cos,
                    }
                ),
            )
        )
    await db.flush()
    return len(top)


async def list_similar(
    db: AsyncSession, *, opportunity_id: int, limit: int = 5
) -> list[dict]:
    rows = (
        await db.execute(
            select(DealSimilarityLink)
            .where(DealSimilarityLink.opportunity_id == opportunity_id)
            .order_by(DealSimilarityLink.similarity_score.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "similar_opportunity_id": r.similar_opportunity_id,
            "similarity_score": r.similarity_score,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
