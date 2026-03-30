"""5-strategy part matching engine for spare parts catalog lookup.

Strategies (cascade):
1. Exact code match (normalized) -> 100%
2. Prefix match (>=4 chars) -> 85%
3. Fuzzy code match (RapidFuzz) -> 75%+  [parallel]
4. Fuzzy name match (TR/EN) -> 50%+      [parallel]
5. Semantic search (sentence-transformers) -> 30%+  [parallel]

Strategies 3-5 run concurrently via asyncio.to_thread to avoid blocking
the event loop (RapidFuzz and numpy are CPU-bound).
"""

import asyncio
import logging
import re
import time
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spare_part import SparePart

logger = logging.getLogger(__name__)

TOP_N = 5
FUZZY_CODE_CUTOFF = 75.0
FUZZY_NAME_CUTOFF = 50.0
PREFIX_MIN_CHARS = 4
CACHE_TTL = 300

_catalog_cache: dict[str, Any] = {"parts": None, "ts": 0}


async def _get_cached_catalog(db: AsyncSession) -> list[SparePart]:
    """Return active spare parts with a simple time-based cache."""
    now = time.time()
    if _catalog_cache["parts"] is not None and (now - _catalog_cache["ts"]) < CACHE_TTL:
        return _catalog_cache["parts"]
    result = await db.execute(select(SparePart).where(SparePart.is_active.is_(True)))
    parts = list(result.scalars().all())
    _catalog_cache["parts"] = parts
    _catalog_cache["ts"] = now
    return parts


def _normalize_code(code: str) -> str:
    """Normalize a part code by removing dashes, spaces, and lowering."""
    return re.sub(r"[\s\-_./]", "", code).upper()


def _fuzzy_code_match(
    query_norm: str,
    catalog_normalized: list[tuple[SparePart, str]],
    catalog_model_normalized: list[tuple[SparePart, str]],
    exclude_ids: set[int],
) -> list[dict[str, Any]]:
    """Strategy 3: fuzzy match on honeywell_code and model_number (CPU-bound)."""
    matches: list[dict[str, Any]] = []
    for part, norm_code in catalog_normalized:
        if part.id in exclude_ids:
            continue
        score = fuzz.token_sort_ratio(query_norm, norm_code)
        if score >= FUZZY_CODE_CUTOFF:
            matches.append(_make_match(part, round(score, 1), "fuzzy_code"))

    found_ids = exclude_ids | {m["spare_part_id"] for m in matches}
    for part, norm_model in catalog_model_normalized:
        if part.id in found_ids:
            continue
        score = fuzz.token_sort_ratio(query_norm, norm_model)
        if score >= FUZZY_CODE_CUTOFF:
            matches.append(_make_match(part, round(score, 1), "fuzzy_model"))

    return matches


def _fuzzy_name_match(
    part_desc: str,
    catalog_normalized: list[tuple[SparePart, str]],
    exclude_ids: set[int],
) -> list[dict[str, Any]]:
    """Strategy 4: fuzzy match on name_tr and name_en (CPU-bound)."""
    matches: list[dict[str, Any]] = []
    desc_lower = part_desc.lower()
    for part, _ in catalog_normalized:
        if part.id in exclude_ids:
            continue
        name_candidates = [n for n in [part.name_tr, part.name_en] if n]
        best_name_score = 0.0
        for name in name_candidates:
            score = fuzz.token_sort_ratio(desc_lower, name.lower())
            best_name_score = max(best_name_score, score)

        if best_name_score >= FUZZY_NAME_CUTOFF:
            matches.append(
                _make_match(part, round(best_name_score, 1), "fuzzy_name"),
            )
    return matches


async def _semantic_match(
    search_text: str,
    db: AsyncSession,
    exclude_ids: set[int],
) -> list[dict[str, Any]]:
    """Strategy 5: semantic search via sentence-transformers."""
    try:
        from app.services.semantic_matcher import search_similar

        sem_results = await search_similar(search_text, db, top_k=TOP_N)
        matches: list[dict[str, Any]] = []
        for sr in sem_results:
            if sr["part_id"] not in exclude_ids:
                matches.append({
                    "spare_part_id": sr["part_id"],
                    "honeywell_code": sr["honeywell_code"],
                    "name_en": sr["name_en"],
                    "name_tr": sr["name_tr"],
                    "category": sr["category"],
                    "score": sr["score"],
                    "strategy": "semantic",
                })
        return matches
    except Exception as e:
        logger.debug("Semantic search unavailable: %s", e)
        return []


async def match_parts(
    db: AsyncSession,
    requested_parts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match requested parts to catalog using 5 strategies.

    Strategies 1-2 run sequentially (fast exact/prefix lookups).
    Strategies 3-5 run concurrently via asyncio.to_thread (CPU-bound).
    Results are merged by score, deduplicated by spare_part_id, top 5 returned.
    """
    catalog: list[SparePart] = await _get_cached_catalog(db)

    if not catalog:
        logger.warning("Spare parts catalog is empty")
        return [{"requested": part, "matches": []} for part in requested_parts]

    catalog_normalized: list[tuple[SparePart, str]] = [
        (part, _normalize_code(part.honeywell_code)) for part in catalog
    ]
    catalog_model_normalized: list[tuple[SparePart, str]] = [
        (part, _normalize_code(part.model_number))
        for part in catalog
        if part.model_number
    ]

    results: list[dict[str, Any]] = []

    for req in requested_parts:
        part_code = req.get("part_code", "") or ""
        part_desc = req.get("part_description", "") or ""
        query_norm = _normalize_code(part_code)

        matches: list[dict[str, Any]] = []

        # Strategy 1: Exact code match
        if query_norm:
            for part, norm_code in catalog_normalized:
                if norm_code == query_norm:
                    matches.append(_make_match(part, 100.0, "exact_code"))
            if not matches:
                for part, norm_model in catalog_model_normalized:
                    if norm_model == query_norm:
                        matches.append(_make_match(part, 100.0, "exact_model"))

        # Strategy 2: Prefix match (only without exact hits)
        if query_norm and len(query_norm) >= PREFIX_MIN_CHARS and not matches:
            existing_ids = {m["spare_part_id"] for m in matches}
            for part, norm_code in catalog_normalized:
                if norm_code.startswith(query_norm) and norm_code != query_norm:
                    matches.append(_make_match(part, 85.0, "prefix_code"))
            for part, norm_model in catalog_model_normalized:
                if part.id not in existing_ids and norm_model.startswith(query_norm) and norm_model != query_norm:
                    matches.append(_make_match(part, 85.0, "prefix_model"))

        # Strategies 3-5: run concurrently (CPU-bound via to_thread)
        existing_ids = {m["spare_part_id"] for m in matches}
        is_needs_more = len(matches) < TOP_N
        tasks = []

        if query_norm and is_needs_more:
            tasks.append(asyncio.to_thread(
                _fuzzy_code_match,
                query_norm,
                catalog_normalized,
                catalog_model_normalized,
                existing_ids,
            ))

        if part_desc and is_needs_more:
            tasks.append(asyncio.to_thread(
                _fuzzy_name_match,
                part_desc,
                catalog_normalized,
                existing_ids,
            ))

        is_needs_semantic = len(matches) < 3 or (matches and matches[0]["score"] < 80)
        search_text = part_desc or part_code
        if is_needs_semantic and search_text:
            tasks.append(_semantic_match(search_text, db, existing_ids))

        if tasks:
            parallel_results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in parallel_results:
                if isinstance(result, Exception):
                    logger.warning("Parallel strategy failed: %s", result)
                    continue
                if isinstance(result, list):
                    matches.extend(result)

        # Deduplicate by spare_part_id, keeping highest score
        seen: dict[int, dict[str, Any]] = {}
        for m in matches:
            pid = m["spare_part_id"]
            if pid not in seen or m["score"] > seen[pid]["score"]:
                seen[pid] = m
        matches = sorted(seen.values(), key=lambda m: m["score"], reverse=True)
        matches = matches[:TOP_N]

        results.append({"requested": req, "matches": matches})
        logger.debug(
            "Part '%s' / '%s': %d matches found",
            part_code,
            part_desc[:40] if part_desc else "",
            len(matches),
        )

    return results


def _make_match(part: SparePart, score: float, strategy: str) -> dict[str, Any]:
    """Build a match result dict from a SparePart."""
    return {
        "spare_part_id": part.id,
        "honeywell_code": part.honeywell_code,
        "model_number": part.model_number,
        "name_en": part.name_en,
        "name_tr": part.name_tr,
        "category": part.category,
        "score": score,
        "strategy": strategy,
    }
