"""Semantic part matching using sentence-transformers embeddings.

Uses paraphrase-multilingual-MiniLM-L12-v2 for multilingual embedding-based
search. Embeddings are cached to disk for fast lookup.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_model = None
_catalog_embeddings: np.ndarray | None = None
_catalog_ids: list[int] = []

EMBEDDINGS_DIR = "data/embeddings"
VECTORS_FILE = os.path.join(EMBEDDINGS_DIR, "vectors.npy")
IDS_FILE = os.path.join(EMBEDDINGS_DIR, "catalog_ids.json")
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def _get_model():
    """Lazy-load the sentence-transformer model."""
    global _model
    if _model is not None:
        return _model

    try:
        from sentence_transformers import SentenceTransformer
        os.environ.setdefault("TRANSFORMERS_CACHE", "data/models")
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Loaded semantic model: %s", MODEL_NAME)
        return _model
    except Exception as e:
        logger.warning("Failed to load semantic model: %s", e)
        return None


def _load_cache() -> bool:
    """Load cached embeddings from disk."""
    global _catalog_embeddings, _catalog_ids

    if not os.path.exists(VECTORS_FILE) or not os.path.exists(IDS_FILE):
        return False

    try:
        _catalog_embeddings = np.load(VECTORS_FILE)
        with open(IDS_FILE) as f:
            _catalog_ids = json.load(f)
        logger.info("Loaded %d cached part embeddings", len(_catalog_ids))
        return True
    except Exception as e:
        logger.warning("Failed to load embedding cache: %s", e)
        return False


async def build_embeddings(db) -> int:
    """Build embeddings for all active spare parts and cache to disk.

    Called after catalog import. Returns number of parts embedded.
    """
    global _catalog_embeddings, _catalog_ids

    model = _get_model()
    if model is None:
        return 0

    from sqlalchemy import select
    from app.models.spare_part import SparePart

    result = await db.execute(
        select(SparePart).where(SparePart.is_active.is_(True))
    )
    parts = result.scalars().all()

    if not parts:
        return 0

    # Build text for each part: combine all available text fields
    texts = []
    ids = []
    for part in parts:
        text_parts = []
        if part.honeywell_code:
            text_parts.append(part.honeywell_code)
        if part.name_tr:
            text_parts.append(part.name_tr)
        if part.name_en:
            text_parts.append(part.name_en)
        if part.description_tr:
            text_parts.append(part.description_tr)
        if part.description_en:
            text_parts.append(part.description_en)
        if part.category:
            text_parts.append(part.category)

        combined = " | ".join(text_parts)
        texts.append(combined)
        ids.append(part.id)

    # Encode
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)

    # Cache to disk
    os.makedirs(EMBEDDINGS_DIR, exist_ok=True)
    np.save(VECTORS_FILE, embeddings)
    with open(IDS_FILE, "w") as f:
        json.dump(ids, f)

    _catalog_embeddings = embeddings
    _catalog_ids = ids

    logger.info("Built and cached embeddings for %d parts", len(ids))
    return len(ids)


async def search_similar(
    query: str,
    db,
    top_k: int = 5,
    threshold: float = 0.30,
) -> list[dict[str, Any]]:
    """Search for parts semantically similar to the query text.

    Returns list of {part_id, score, honeywell_code, name_tr, name_en, category}
    """
    global _catalog_embeddings, _catalog_ids

    model = _get_model()
    if model is None:
        return []

    # Load cache if not in memory
    if _catalog_embeddings is None:
        if not _load_cache():
            # Try building from DB
            count = await build_embeddings(db)
            if count == 0:
                return []

    if _catalog_embeddings is None or len(_catalog_ids) == 0:
        return []

    # Encode query
    query_vec = model.encode([query], normalize_embeddings=True)

    # Cosine similarity (dot product on normalized vectors)
    scores = np.dot(_catalog_embeddings, query_vec.T).flatten()

    # Get top-k above threshold
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    from sqlalchemy import select
    from app.models.spare_part import SparePart

    for idx in top_indices:
        score = float(scores[idx])
        if score < threshold:
            break

        part_id = _catalog_ids[idx]
        result = await db.execute(
            select(SparePart).where(SparePart.id == part_id)
        )
        part = result.scalar_one_or_none()

        if part:
            results.append({
                "part_id": part.id,
                "honeywell_code": part.honeywell_code,
                "name_tr": part.name_tr,
                "name_en": part.name_en,
                "category": part.category,
                "score": round(score * 100, 1),
                "strategy": "semantic",
            })

    return results


def invalidate_cache():
    """Clear cached embeddings (call after catalog changes)."""
    global _catalog_embeddings, _catalog_ids
    _catalog_embeddings = None
    _catalog_ids = []

    for f in [VECTORS_FILE, IDS_FILE]:
        if os.path.exists(f):
            os.remove(f)

    logger.info("Embedding cache invalidated")
