"""Semantic vector search using pgvector + sentence-transformers.

Falls back to PostgreSQL ILIKE + pg_trgm if pgvector is not available.
Zero external paid dependencies — all runs locally.
"""

import logging
import hashlib
from functools import lru_cache

logger = logging.getLogger(__name__)

_model = None
_pgvector_available: bool | None = None


def _get_model():
    """Lazy-load sentence-transformers model (multilingual, ~90MB)."""
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        logger.info("Loaded sentence-transformers model for semantic search")
        return _model
    except ImportError:
        logger.warning("sentence-transformers not installed — semantic search disabled, using ILIKE fallback")
        return None
    except Exception as e:
        logger.warning("Failed to load sentence-transformers model: %s", e)
        return None


def embed_text(text: str) -> list[float] | None:
    """Generate embedding vector for text. Returns None if model unavailable."""
    model = _get_model()
    if model is None:
        return None
    try:
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()
    except Exception as e:
        logger.warning("Embedding generation failed: %s", e)
        return None


async def check_pgvector(db) -> bool:
    """Check if pgvector extension is available in PostgreSQL."""
    global _pgvector_available
    if _pgvector_available is not None:
        return _pgvector_available
    try:
        from sqlalchemy import text
        result = await db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
        _pgvector_available = result.scalar() is not None
        if not _pgvector_available:
            # Try to create it
            try:
                await db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await db.execute(text("COMMIT"))
                _pgvector_available = True
                logger.info("pgvector extension created successfully")
            except Exception:
                _pgvector_available = False
                logger.info("pgvector extension not available — using ILIKE fallback")
    except Exception:
        _pgvector_available = False
    return _pgvector_available


async def semantic_search(
    db,
    query: str,
    table: str = "transcripts",
    content_column: str = "content",
    limit: int = 10,
    filters: dict | None = None,
) -> list[dict]:
    """Search using semantic similarity if pgvector available, else ILIKE.

    Returns list of {id, title, snippet, score} dicts.
    """
    from sqlalchemy import text

    # Try semantic search first
    vec = embed_text(query)
    has_pgvector = await check_pgvector(db)

    if vec and has_pgvector:
        return await _vector_search(db, query, vec, table, content_column, limit, filters)

    # Fallback: ILIKE with pg_trgm similarity scoring
    return await _ilike_search(db, query, table, content_column, limit, filters)


async def _vector_search(db, query, vec, table, content_column, limit, filters):
    """pgvector cosine similarity search."""
    from sqlalchemy import text
    import json

    vec_str = json.dumps(vec)

    # Build WHERE clause
    where_parts = []
    params = {"vec": vec_str, "limit": limit}
    if filters:
        for i, (col, val) in enumerate(filters.items()):
            where_parts.append(f"{col} = :f{i}")
            params[f"f{i}"] = val

    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    # Check if embedding column exists; if not, fall back to ILIKE
    try:
        sql = f"""
            SELECT id, title, LEFT({content_column}, 300) as snippet,
                   1 - (embedding <=> :vec::vector) as score
            FROM {table}
            {where_clause}
            ORDER BY embedding <=> :vec::vector
            LIMIT :limit
        """
        result = await db.execute(text(sql), params)
        rows = result.fetchall()
        return [{"id": r.id, "title": r.title, "snippet": r.snippet, "score": round(float(r.score), 3)} for r in rows]
    except Exception as e:
        logger.debug("Vector search failed (embedding column may not exist): %s", e)
        return await _ilike_search(db, query, table, content_column, limit, filters)


async def _ilike_search(db, query, table, content_column, limit, filters):
    """Fallback: ILIKE search — compatible with both PostgreSQL and SQLite."""
    from sqlalchemy import text

    safe_q = query.replace("%", "\\%").replace("_", "\\_")

    where_parts = [f"({content_column} LIKE :search OR title LIKE :search)"]
    params = {"search": f"%{safe_q}%", "limit": limit}

    if filters:
        for i, (col, val) in enumerate(filters.items()):
            where_parts.append(f"{col} = :f{i}")
            params[f"f{i}"] = val

    where_clause = " AND ".join(where_parts)

    # Simple LIKE search — works on both PostgreSQL and SQLite
    sql = f"""
        SELECT id, title, SUBSTR({content_column}, 1, 300) as snippet, 0.5 as score
        FROM {table}
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT :limit
    """
    try:
        result = await db.execute(text(sql), params)
        rows = result.fetchall()
        return [{"id": r.id, "title": r.title, "snippet": r.snippet, "score": 0.5} for r in rows]
    except Exception as e:
        logger.warning("ILIKE search failed: %s", e)
        return []
