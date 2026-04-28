"""Persistence helpers for V12 transformer sequence embeddings.

Kept separate from the encoder so the encoder module stays
import-free of the SQLAlchemy stack — that lets us unit-test the
encoder with a stubbed model and zero DB.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v12_transformer_seq_embedding import (
    OpportunityTransformerSeqEmbedding,
)
from app.services import transformer_sequence_embedder
from app.services.text_embedder import vocab_hash

logger = logging.getLogger(__name__)


async def upsert_transformer_seq_embedding(
    db: AsyncSession, *, opportunity_id: int, tokens: Sequence[str]
) -> OpportunityTransformerSeqEmbedding | None:
    """Create or update the transformer embedding for ``opportunity_id``.

    Empty token lists are skipped (caller decides whether to clear an
    existing row — we don't, by design: the previous embedding stays
    queryable until the deal accumulates events again).

    Returns the row on success, ``None`` when the encoder can't be
    loaded (e.g. ``sentence-transformers`` missing) — the caller can
    log + continue, the V8 BoW path keeps working.
    """
    if not tokens:
        return None

    try:
        vec = transformer_sequence_embedder.embed_tokens(tokens)
    except RuntimeError as exc:
        logger.warning(
            "transformer encoder unavailable for opp %s: %s", opportunity_id, exc
        )
        return None

    payload = json.dumps(vec)
    vh = vocab_hash(tokens)

    existing = await db.get(OpportunityTransformerSeqEmbedding, opportunity_id)
    if existing is None:
        row = OpportunityTransformerSeqEmbedding(
            opportunity_id=opportunity_id,
            embedding_json=payload,
            dim=len(vec),
            version=transformer_sequence_embedder.VERSION,
            vocab_hash=vh,
        )
        db.add(row)
        await db.flush()
        return row

    existing.embedding_json = payload
    existing.dim = len(vec)
    existing.version = transformer_sequence_embedder.VERSION
    existing.vocab_hash = vh
    await db.flush()
    return existing


async def backfill_transformer_seq_embeddings(
    db: AsyncSession,
    *,
    opportunity_ids: Sequence[int] | None = None,
) -> dict[str, int]:
    """Bulk encode opportunities into the transformer table.

    When ``opportunity_ids`` is None we walk every row in
    ``opportunity_embeddings`` (the V5 structured embedding) — that
    set is the canonical "deals worth comparing". Tokens are pulled
    via the same helper used by the similarity service so the V12
    encoding stays consistent with what the blend will see at read
    time.

    Returns ``{"processed": N, "written": M, "skipped": K}``.
    """
    from app.models.v5_intelligence import OpportunityEmbedding
    from app.services.deal_similarity_service import _tokens_for_opp

    if opportunity_ids is None:
        rows = (
            await db.execute(select(OpportunityEmbedding.opportunity_id))
        ).scalars().all()
        opportunity_ids = [int(r) for r in rows]

    processed = 0
    written = 0
    skipped = 0
    for opp_id in opportunity_ids:
        processed += 1
        tokens = await _tokens_for_opp(db, opportunity_id=int(opp_id))
        if not tokens:
            skipped += 1
            continue
        result = await upsert_transformer_seq_embedding(
            db, opportunity_id=int(opp_id), tokens=tokens
        )
        if result is None:
            skipped += 1
        else:
            written += 1

    return {"processed": processed, "written": written, "skipped": skipped}
