"""Incremental embedding service for spare parts catalog.

Instead of rebuilding ALL embeddings after every import, this service
only re-embeds new or modified parts by tracking content hashes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spare_part import SparePart

logger = logging.getLogger(__name__)

_embedding_model = None  # Module-level singleton


def _get_embedding_model():
    """Lazy-load and cache the embedding model (singleton)."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            logger.info("Embedding model loaded and cached (embedding_service)")
        except ImportError:
            logger.error("sentence-transformers not installed — embeddings unavailable")
            raise RuntimeError("sentence-transformers required for embeddings")
    return _embedding_model


EMBEDDINGS_DIR = Path("data/embeddings")
CATALOG_FILE = EMBEDDINGS_DIR / "catalog_ids.json"
VECTORS_FILE = EMBEDDINGS_DIR / "vectors.npy"
HASHES_FILE = EMBEDDINGS_DIR / "part_hashes.json"


def _part_text(part: SparePart) -> str:
    """Build searchable text for a spare part."""
    parts = [
        part.honeywell_code or "",
        part.model_number or "",
        part.name_en or "",
        part.name_tr or "",
        part.description_en or "",
        part.description_tr or "",
        part.category or "",
    ]
    return " ".join(p for p in parts if p).strip()


def _hash_part(part: SparePart) -> str:
    """Hash part content to detect changes."""
    text = _part_text(part)
    return hashlib.md5(text.encode()).hexdigest()


async def update_embeddings_incremental(db: AsyncSession) -> dict:
    """Only re-embed new or modified parts. Returns stats dict."""
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing hashes
    existing_hashes: dict[int, str] = {}
    if HASHES_FILE.exists():
        with open(HASHES_FILE) as f:
            existing_hashes = {int(k): v for k, v in json.load(f).items()}

    # Get all active parts
    result = await db.execute(
        select(SparePart).where(SparePart.is_active.is_(True)),
    )
    all_parts = result.scalars().all()

    # Find new/modified parts
    new_parts = []
    current_hashes: dict[int, str] = {}
    for part in all_parts:
        h = _hash_part(part)
        current_hashes[part.id] = h
        if existing_hashes.get(part.id) != h:
            new_parts.append(part)

    if not new_parts:
        logger.info("No embedding changes needed")
        return {"new": 0, "total": len(all_parts)}

    # Load cached model
    try:
        model = _get_embedding_model()
    except (ImportError, RuntimeError):
        logger.warning("sentence-transformers not installed, skipping embeddings")
        return {"error": "sentence-transformers not installed", "new": len(new_parts)}

    # Load existing vectors or create empty
    existing_vectors: dict[int, np.ndarray] = {}
    if VECTORS_FILE.exists() and CATALOG_FILE.exists():
        vectors = np.load(VECTORS_FILE)
        with open(CATALOG_FILE) as f:
            ids = json.load(f)
        for i, pid in enumerate(ids):
            if pid in current_hashes:  # Still active
                existing_vectors[pid] = vectors[i]

    # Embed only new/modified parts
    texts = [_part_text(p) for p in new_parts]
    new_vectors = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    for i, part in enumerate(new_parts):
        existing_vectors[part.id] = new_vectors[i]

    # Rebuild full arrays (only active parts)
    all_ids = sorted(existing_vectors.keys())
    all_vectors = np.array([existing_vectors[pid] for pid in all_ids])

    # Save
    np.save(VECTORS_FILE, all_vectors)
    with open(CATALOG_FILE, "w") as f:
        json.dump(all_ids, f)
    with open(HASHES_FILE, "w") as f:
        json.dump(current_hashes, f)

    logger.info(
        "Embeddings updated: %d new/modified, %d total",
        len(new_parts),
        len(all_ids),
    )
    return {"new": len(new_parts), "total": len(all_ids)}
