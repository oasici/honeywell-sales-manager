"""RAG endpoint response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RagSearchResponse(BaseModel):
    query: str | None = None
    competitor: str | None = None
    items: list[Any] = []
    total: int | None = None

    model_config = {"extra": "allow"}


class RagAnswerResponse(BaseModel):
    question: str | None = None
    answer: str | None = None
    citations: list[Any] | None = None
    confidence: float | None = None
    used_collections: list[str] | None = None
    fallback_reason: str | None = None

    model_config = {"extra": "allow"}


class RagCollectionItem(BaseModel):
    name: str | None = None
    points_count: int | None = None

    model_config = {"extra": "allow"}


class RagCollectionsResponse(BaseModel):
    items: list[RagCollectionItem] = []
    total: int | None = None
    error: str | None = None

    model_config = {"extra": "allow"}


class RagReindexResponse(BaseModel):
    collection: str | None = None
    indexed: int | None = None
    deals_indexed: int | None = None
    interactions_indexed: int | None = None
    competitors_indexed: int | None = None

    model_config = {"extra": "allow"}
