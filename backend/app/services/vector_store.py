"""Qdrant vector store service for RAG pattern — deals, interactions, competitors."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.circuit_breaker import qdrant_breaker
from app.core.config import settings

logger = logging.getLogger(__name__)

VECTOR_SIZE = 384

# Lazy singletons
_client: QdrantClient | None = None
_embedding_model = None  # Module-level singleton


def _get_client() -> QdrantClient:
    """Return a lazily-initialised Qdrant client.

    Reads ``QDRANT_API_KEY`` from settings; when it's empty (local
    docker-compose) the client is constructed without auth, which is
    what self-hosted Qdrant expects. Qdrant Cloud rejects unauth'd
    requests with 403, so prod must always have the key set.
    """
    global _client
    if _client is None:
        api_key = settings.QDRANT_API_KEY or None
        _client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=api_key,
            timeout=10,
        )
    return _client


def _ensure_collection(name: str, vector_size: int = VECTOR_SIZE) -> None:
    """Create collection if not exists."""
    client = _get_client()
    try:
        client.get_collection(name)
    except (UnexpectedResponse, Exception):
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )
        logger.info("Created Qdrant collection: %s", name)


def _get_embedding_model():
    """Lazy-load and cache the embedding model (singleton).

    On Render the RAG deps install in the background after the
    container starts (see ``scripts/start.sh``), so this function
    can be called *before* sentence-transformers is importable. We
    distinguish three states to make the failure mode legible:

      * ``$HOME/.rag_deps_installed`` exists → install is done; if
        the import still fails it's a real misconfiguration.
      * Marker file missing AND ``INSTALL_RAG_DEPS=1`` → install
        likely still in progress, surface as RAGNotReady so the API
        layer can return 503 + a Retry-After hint instead of 500.
      * ``INSTALL_RAG_DEPS`` unset → operator hasn't enabled RAG;
        the legacy "not available" RuntimeError stays.
    """
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        import os
        from pathlib import Path

        marker_path = Path(os.path.expanduser("~/.rag_deps_installed"))
        install_requested = os.environ.get("INSTALL_RAG_DEPS") == "1"

        if install_requested and not marker_path.exists():
            logger.info(
                "RAG deps install still in progress — sentence-transformers not yet importable"
            )
            raise RuntimeError(
                "RAG dependencies are still installing in the background; "
                "retry in a few minutes."
            )

        # Either the operator hasn't requested RAG (clean degraded
        # state) or the install completed but the import still fails
        # (genuine misconfiguration).
        logger.warning("sentence-transformers not installed — RAG unavailable")
        raise RuntimeError("sentence-transformers required for RAG")

    _embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    logger.info("Embedding model loaded and cached")
    return _embedding_model


def _get_embedding(text: str) -> list[float]:
    """Get embedding vector for text (uses cached model)."""
    model = _get_embedding_model()
    return model.encode(text[:2000]).tolist()


# ── Deals ──


async def store_deal(deal_data: dict[str, Any]) -> str:
    """Store a deal context in the deals collection."""
    if not settings.FEATURE_RAG:
        return ""
    if qdrant_breaker.is_open:
        logger.debug("Qdrant circuit open, skipping store_deal")
        return ""
    try:
        _ensure_collection(settings.QDRANT_COLLECTION_DEALS)
        client = _get_client()

        text = (
            f"{deal_data.get('title', '')} "
            f"{deal_data.get('stage', '')} "
            f"{deal_data.get('summary', '')}"
        )
        embedding = _get_embedding(text)
        point_id = hashlib.md5(
            f"deal_{deal_data.get('id', '')}".encode(),
        ).hexdigest()

        client.upsert(
            collection_name=settings.QDRANT_COLLECTION_DEALS,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "deal_id": deal_data.get("id"),
                        "title": deal_data.get("title", ""),
                        "stage": deal_data.get("stage", ""),
                        "amount": deal_data.get("amount", 0),
                        "outcome": deal_data.get("outcome", "active"),
                        "risk_level": deal_data.get("risk_level", "unknown"),
                        "customer_name": deal_data.get("customer_name", ""),
                        "signal_summary": deal_data.get("signal_summary", ""),
                    },
                ),
            ],
        )
        qdrant_breaker._on_success()
        return point_id
    except Exception as exc:
        qdrant_breaker._on_failure()
        logger.warning("Qdrant store_deal failed: %s", exc)
        return ""


async def find_similar_deals(
    query_text: str,
    limit: int = 5,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Find similar deals from Qdrant."""
    if not settings.FEATURE_RAG:
        return []
    if qdrant_breaker.is_open:
        logger.debug("Qdrant circuit open, skipping find_similar_deals")
        return []
    try:
        _ensure_collection(settings.QDRANT_COLLECTION_DEALS)
        client = _get_client()
        embedding = _get_embedding(query_text)

        qdrant_filter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                if value is not None:
                    conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=value),
                        ),
                    )
            if conditions:
                qdrant_filter = models.Filter(must=conditions)

        results = client.query_points(
            collection_name=settings.QDRANT_COLLECTION_DEALS,
            query=embedding,
            limit=limit,
            query_filter=qdrant_filter,
        )

        qdrant_breaker._on_success()
        return [{"score": r.score, **r.payload} for r in results.points]
    except Exception as exc:
        qdrant_breaker._on_failure()
        logger.warning("Qdrant find_similar_deals failed: %s", exc)
        return []


# ── Interactions ──


async def store_interaction(interaction_data: dict[str, Any]) -> str:
    """Store a customer interaction (email, transcript, note) in vector DB."""
    if not settings.FEATURE_RAG:
        return ""
    if qdrant_breaker.is_open:
        logger.debug("Qdrant circuit open, skipping store_interaction")
        return ""
    try:
        _ensure_collection(settings.QDRANT_COLLECTION_INTERACTIONS)
        client = _get_client()

        text = interaction_data.get("content", "")
        if not text:
            return ""
        embedding = _get_embedding(text[:2000])
        point_id = hashlib.md5(
            f"interaction_{interaction_data.get('id', '')}_{interaction_data.get('type', '')}".encode(),
        ).hexdigest()

        client.upsert(
            collection_name=settings.QDRANT_COLLECTION_INTERACTIONS,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "interaction_id": interaction_data.get("id"),
                        "type": interaction_data.get("type", ""),
                        "customer_id": interaction_data.get("customer_id"),
                        "opportunity_id": interaction_data.get("opportunity_id"),
                        "sentiment": interaction_data.get("sentiment", "neutral"),
                        "summary": text[:500],
                    },
                ),
            ],
        )
        qdrant_breaker._on_success()
        return point_id
    except Exception as exc:
        qdrant_breaker._on_failure()
        logger.warning("Qdrant store_interaction failed: %s", exc)
        return ""


async def find_similar_interactions(
    query_text: str,
    limit: int = 5,
    customer_id: int | None = None,
) -> list[dict[str, Any]]:
    """Find similar past interactions."""
    if not settings.FEATURE_RAG:
        return []
    if qdrant_breaker.is_open:
        logger.debug("Qdrant circuit open, skipping find_similar_interactions")
        return []
    try:
        _ensure_collection(settings.QDRANT_COLLECTION_INTERACTIONS)
        client = _get_client()
        embedding = _get_embedding(query_text[:2000])

        qdrant_filter = None
        if customer_id:
            qdrant_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="customer_id",
                        match=models.MatchValue(value=customer_id),
                    ),
                ],
            )

        results = client.query_points(
            collection_name=settings.QDRANT_COLLECTION_INTERACTIONS,
            query=embedding,
            limit=limit,
            query_filter=qdrant_filter,
        )

        qdrant_breaker._on_success()
        return [{"score": r.score, **r.payload} for r in results.points]
    except Exception as exc:
        qdrant_breaker._on_failure()
        logger.warning("Qdrant find_similar_interactions failed: %s", exc)
        return []


# ── Competitor Intelligence ──


async def store_competitor_intel(intel_data: dict[str, Any]) -> str:
    """Store competitor intelligence in vector DB."""
    if not settings.FEATURE_RAG:
        return ""
    if qdrant_breaker.is_open:
        logger.debug("Qdrant circuit open, skipping store_competitor_intel")
        return ""
    try:
        _ensure_collection(settings.QDRANT_COLLECTION_COMPETITORS)
        client = _get_client()

        text = f"{intel_data.get('competitor', '')} {intel_data.get('content', '')}"
        embedding = _get_embedding(text[:2000])
        point_id = hashlib.md5(
            f"comp_{intel_data.get('competitor', '')}_{intel_data.get('source', '')}_{intel_data.get('date', '')}".encode(),
        ).hexdigest()

        client.upsert(
            collection_name=settings.QDRANT_COLLECTION_COMPETITORS,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "competitor": intel_data.get("competitor", ""),
                        "source": intel_data.get("source", ""),
                        "source_url": intel_data.get("source_url", ""),
                        "content_snippet": intel_data.get("content", "")[:500],
                        "category": intel_data.get("category", "general"),
                        "date": intel_data.get("date", ""),
                    },
                ),
            ],
        )
        qdrant_breaker._on_success()
        return point_id
    except Exception as exc:
        qdrant_breaker._on_failure()
        logger.warning("Qdrant store_competitor_intel failed: %s", exc)
        return ""


async def find_competitor_intel(
    competitor_name: str,
    query: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Find competitor intelligence."""
    if not settings.FEATURE_RAG:
        return []
    if qdrant_breaker.is_open:
        logger.debug("Qdrant circuit open, skipping find_competitor_intel")
        return []
    try:
        _ensure_collection(settings.QDRANT_COLLECTION_COMPETITORS)
        client = _get_client()

        search_text = f"{competitor_name} {query}" if query else competitor_name
        embedding = _get_embedding(search_text)

        qdrant_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="competitor",
                    match=models.MatchValue(value=competitor_name),
                ),
            ],
        )

        results = client.query_points(
            collection_name=settings.QDRANT_COLLECTION_COMPETITORS,
            query=embedding,
            limit=limit,
            query_filter=qdrant_filter,
        )

        qdrant_breaker._on_success()
        return [{"score": r.score, **r.payload} for r in results.points]
    except Exception as exc:
        qdrant_breaker._on_failure()
        logger.warning("Qdrant find_competitor_intel failed: %s", exc)
        return []
