"""V11 RAG endpoints — search + answer + collection management.

All routes mounted under ``/api/v1/rag/``. Gated by ``FEATURE_RAG``.

* Search:
    POST /rag/search/deals
    POST /rag/search/interactions
    POST /rag/search/competitors

* Generation:
    POST /rag/answer

* Ops:
    GET  /rag/collections           (alias of /ai/rag/status, richer payload)
    POST /rag/reindex/{name}        (manager-only, kicks off backfill)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.rate_limit import enforce_ai_rate_limit
from app.models.enums import UserRole
from app.models.user import User
from app.services import rag_answer_service, rag_backfill_service
from app.schemas.common import ItemsResponse
from app.schemas.round16_aggregates import RagQueryResponse, RagReindexResponse

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/rag", tags=["RAG"])


def _require_rag():
    if not settings.FEATURE_RAG:
        raise HTTPException(status_code=404, detail="Not found")


def _manager_only(user: User) -> None:
    if user.role not in (UserRole.SALES_MANAGER.value, UserRole.OPERATIONS.value):
        raise HTTPException(status_code=403, detail="Yetkisiz")


# ─────────────────────── search payloads ────────────────────────────


class DealSearchPayload(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(5, ge=1, le=25)
    filters: dict[str, Any] | None = None


class InteractionSearchPayload(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(5, ge=1, le=25)
    customer_id: int | None = None


class CompetitorSearchPayload(BaseModel):
    competitor: str = Field(..., min_length=1, max_length=120)
    query: str = Field("", max_length=500)
    limit: int = Field(5, ge=1, le=25)


@router.post(
    "/search/deals",
    # Round-4 R4-RL-3 — vector search + embedding gen is expensive;
    # /answer also burns the Anthropic budget.
    dependencies=[Depends(enforce_ai_rate_limit)],
    response_model=ItemsResponse,
)
async def search_deals(
    payload: DealSearchPayload,
    current_user: User = Depends(get_current_user),
    _flag=Depends(_require_rag),
):
    from app.services.vector_store import find_similar_deals

    rows = await find_similar_deals(payload.query, limit=payload.limit, filters=payload.filters)
    return {"query": payload.query, "items": rows, "total": len(rows)}


@router.post(
    "/search/interactions",
    dependencies=[Depends(enforce_ai_rate_limit)],
    response_model=ItemsResponse,
)
async def search_interactions(
    payload: InteractionSearchPayload,
    current_user: User = Depends(get_current_user),
    _flag=Depends(_require_rag),
):
    from app.services.vector_store import find_similar_interactions

    rows = await find_similar_interactions(
        payload.query, limit=payload.limit, customer_id=payload.customer_id
    )
    return {"query": payload.query, "items": rows, "total": len(rows)}


@router.post(
    "/search/competitors",
    dependencies=[Depends(enforce_ai_rate_limit)],
    response_model=ItemsResponse,
)
async def search_competitors(
    payload: CompetitorSearchPayload,
    current_user: User = Depends(get_current_user),
    _flag=Depends(_require_rag),
):
    from app.services.vector_store import find_competitor_intel

    rows = await find_competitor_intel(payload.competitor, query=payload.query, limit=payload.limit)
    return {"competitor": payload.competitor, "items": rows, "total": len(rows)}


# ─────────────────────── answer ────────────────────────────────────


class RagAnswerPayload(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    scope: list[str] | None = None
    limit: int = Field(5, ge=1, le=15)
    customer_id: int | None = None
    competitor: str | None = None


@router.post(
    "/answer",
    dependencies=[Depends(enforce_ai_rate_limit)],
    response_model=RagQueryResponse,
)
async def rag_answer(
    payload: RagAnswerPayload,
    current_user: User = Depends(get_current_user),
    _flag=Depends(_require_rag),
):
    result = await rag_answer_service.answer_question(
        question=payload.question,
        scope=payload.scope,
        limit=payload.limit,
        customer_id=payload.customer_id,
        competitor=payload.competitor,
    )
    return {
        "question": payload.question,
        "answer": result.answer,
        "citations": result.citations,
        "confidence": result.confidence,
        "used_collections": result.used_collections,
        "fallback_reason": result.fallback_reason,
    }


# ─────────────────────── collections / reindex ──────────────────────


@router.get("/collections", response_model=ItemsResponse)
async def list_collections(
    current_user: User = Depends(get_current_user),
    _flag=Depends(_require_rag),
):
    from app.services.vector_store import _get_client

    try:
        client = _get_client()
        items = client.get_collections().collections
        return {
            "items": [
                {"name": c.name, "points_count": getattr(c, "points_count", None)}
                for c in items
            ],
            "total": len(items),
        }
    except Exception as exc:
        logger.warning("rag.list_collections failed: %s", exc)
        return {"items": [], "total": 0, "error": str(exc)}


_VALID_BACKFILL_NAMES = {"deals", "interactions", "competitors", "all"}


@router.post("/reindex/{name}", response_model=RagReindexResponse)
async def reindex_collection(
    name: str,
    since_hours: int | None = Query(None, ge=1, le=720),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_rag),
):
    _manager_only(current_user)
    if name not in _VALID_BACKFILL_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown collection: {name}")

    from datetime import datetime, timedelta, timezone

    since = (
        datetime.now(timezone.utc) - timedelta(hours=since_hours)
        if since_hours
        else None
    )

    if name == "deals":
        count = await rag_backfill_service.backfill_deals(db, since=since)
        return {"collection": "deals", "indexed": count}
    if name == "interactions":
        count = await rag_backfill_service.backfill_interactions(db, since=since)
        return {"collection": "interactions", "indexed": count}
    if name == "competitors":
        count = await rag_backfill_service.backfill_competitors(db, since=since)
        return {"collection": "competitors", "indexed": count}
    # name == "all"
    result = await rag_backfill_service.run_full_backfill(db, since=since)
    return {
        "collection": "all",
        "deals_indexed": result.deals_indexed,
        "interactions_indexed": result.interactions_indexed,
        "competitors_indexed": result.competitors_indexed,
    }
