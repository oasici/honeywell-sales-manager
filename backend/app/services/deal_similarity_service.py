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

from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity
from app.models.sequence_v2 import Stakeholder
from app.models.v5_similarity import DealSimilarityLink, OpportunityEmbedding

logger = logging.getLogger(__name__)


EMBEDDING_VERSION = "v5-structured-1"
EMBEDDING_DIM = 8


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
    digest = hashlib.md5(industry.lower().encode("utf-8")).hexdigest()
    # First 4 hex chars → [0..1]
    return int(digest[:4], 16) / 0xFFFF


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ─────────────────────── embedding builder ──────────────────────────


async def build_embedding(
    db: AsyncSession, *, opportunity_id: int
) -> list[float] | None:
    """Build the 8-dim feature vector for one opportunity.

    Returns ``None`` when the opportunity is missing or has no OFD row
    yet (caller can decide to skip vs. retry later).
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

    return [
        _amount_score(opp.amount),
        _size_score(getattr(opp, "employee_count", None)),
        momentum,
        stakeholder_norm,
        followup,
        buyer_engagement,
        discount,
        _industry_hash(getattr(opp, "industry", None)),
    ]


async def upsert_embedding(
    db: AsyncSession, *, opportunity_id: int
) -> OpportunityEmbedding | None:
    vec = await build_embedding(db, opportunity_id=opportunity_id)
    if vec is None:
        return None
    existing = await db.get(OpportunityEmbedding, opportunity_id)
    if existing is None:
        row = OpportunityEmbedding(
            opportunity_id=opportunity_id,
            embedding_json=json.dumps(vec),
            dim=EMBEDDING_DIM,
            version=EMBEDDING_VERSION,
        )
        db.add(row)
        await db.flush()
        return row
    existing.embedding_json = json.dumps(vec)
    existing.dim = EMBEDDING_DIM
    existing.version = EMBEDDING_VERSION
    existing.generated_at = datetime.now(timezone.utc)
    await db.flush()
    return existing


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


async def refresh_similarity_links(
    db: AsyncSession, *, opportunity_id: int, top_k: int = 5, min_score: float = 0.7
) -> int:
    """Refresh the top-K similar deals for ``opportunity_id``.

    Drops existing links for this opp and writes the new top-K set.
    Returns the number of links written.
    """
    own = await db.get(OpportunityEmbedding, opportunity_id)
    if own is None:
        return 0
    own_vec = json.loads(own.embedding_json)

    others = (
        await db.execute(
            select(OpportunityEmbedding).where(
                OpportunityEmbedding.opportunity_id != opportunity_id
            )
        )
    ).scalars().all()

    scored: list[tuple[int, float]] = []
    for other in others:
        try:
            other_vec = json.loads(other.embedding_json)
        except (json.JSONDecodeError, TypeError):
            continue
        score = cosine_similarity(own_vec, other_vec)
        if score >= min_score:
            scored.append((int(other.opportunity_id), score))
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

    for sim_id, score in top:
        db.add(
            DealSimilarityLink(
                opportunity_id=opportunity_id,
                similar_opportunity_id=sim_id,
                similarity_score=score,
                similarity_reason_json=json.dumps(
                    {"embedding_version": EMBEDDING_VERSION, "method": "cosine"}
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
