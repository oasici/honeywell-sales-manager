"""5-strategy part matching engine for spare parts catalog lookup.

Strategies (cascade):
1. Exact code match (normalized) → 100%
2. Prefix match (≥4 chars) → 85%
3. Fuzzy code match (RapidFuzz) → 75%+
4. Fuzzy name match (TR/EN) → 50%+
5. Semantic search (sentence-transformers) → 30%+  [HuggingFace]
"""

import logging
import re
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


def _normalize_code(code: str) -> str:
    """Normalize a part code by removing dashes, spaces, and lowering."""
    return re.sub(r"[\s\-_./]", "", code).upper()


async def match_parts(
    db: AsyncSession, requested_parts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Match requested parts to catalog using 4 strategies.

    For each requested part, returns top 5 matches with scores.

    Strategies (cascade):
    1. Exact code match (normalized) -> 100% score
    2. Prefix match (code starts with query, >= 4 chars) -> 85% score
    3. Fuzzy code match (RapidFuzz token_sort_ratio) -> 75%+ cutoff
    4. Fuzzy name match (on name_tr + name_en) -> 50%+ cutoff
    """
    # Load all active spare parts from DB
    stmt = select(SparePart).where(SparePart.is_active.is_(True))
    result = await db.execute(stmt)
    catalog: list[SparePart] = list(result.scalars().all())

    if not catalog:
        logger.warning("Spare parts catalog is empty")
        return [{"requested": part, "matches": []} for part in requested_parts]

    # Pre-compute normalized codes for the catalog
    catalog_normalized: list[tuple[SparePart, str]] = [
        (part, _normalize_code(part.honeywell_code)) for part in catalog
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

        # Strategy 2: Prefix match (only if we don't already have exact)
        if query_norm and len(query_norm) >= PREFIX_MIN_CHARS and not matches:
            for part, norm_code in catalog_normalized:
                if norm_code.startswith(query_norm) and norm_code != query_norm:
                    matches.append(_make_match(part, 85.0, "prefix_code"))

        # Strategy 3: Fuzzy code match
        if query_norm and len(matches) < TOP_N:
            existing_ids = {m["spare_part_id"] for m in matches}
            for part, norm_code in catalog_normalized:
                if part.id in existing_ids:
                    continue
                score = fuzz.token_sort_ratio(query_norm, norm_code)
                if score >= FUZZY_CODE_CUTOFF:
                    matches.append(
                        _make_match(part, round(score * 0.75 / 100 * 100, 1), "fuzzy_code")
                    )

        # Strategy 4: Fuzzy name match
        if part_desc and len(matches) < TOP_N:
            existing_ids = {m["spare_part_id"] for m in matches}
            desc_lower = part_desc.lower()
            for part, _ in catalog_normalized:
                if part.id in existing_ids:
                    continue
                # Match against both Turkish and English names
                name_candidates = [
                    n for n in [part.name_tr, part.name_en] if n
                ]
                best_name_score = 0.0
                for name in name_candidates:
                    score = fuzz.token_sort_ratio(desc_lower, name.lower())
                    best_name_score = max(best_name_score, score)

                if best_name_score >= FUZZY_NAME_CUTOFF:
                    matches.append(
                        _make_match(
                            part,
                            round(best_name_score * 0.50 / 100 * 100, 1),
                            "fuzzy_name",
                        )
                    )

        # Strategy 5: Semantic search (HuggingFace sentence-transformers)
        if len(matches) < 3 or (matches and matches[0]["score"] < 80):
            search_text = part_desc or part_code
            if search_text:
                existing_ids = {m["spare_part_id"] for m in matches}
                try:
                    from app.services.semantic_matcher import search_similar
                    sem_results = await search_similar(search_text, db, top_k=TOP_N)
                    for sr in sem_results:
                        if sr["part_id"] not in existing_ids:
                            matches.append({
                                "spare_part_id": sr["part_id"],
                                "honeywell_code": sr["honeywell_code"],
                                "name_en": sr["name_en"],
                                "name_tr": sr["name_tr"],
                                "category": sr["category"],
                                "score": sr["score"],
                                "strategy": "semantic",
                            })
                except Exception as e:
                    logger.debug("Semantic search unavailable: %s", e)

        # Sort by score descending, take top N
        matches.sort(key=lambda m: m["score"], reverse=True)
        matches = matches[:TOP_N]

        results.append({"requested": req, "matches": matches})
        logger.debug(
            "Part '%s' / '%s': %d matches found",
            part_code,
            part_desc[:40],
            len(matches),
        )

    return results


def _make_match(part: SparePart, score: float, strategy: str) -> dict[str, Any]:
    """Build a match result dict from a SparePart."""
    return {
        "spare_part_id": part.id,
        "honeywell_code": part.honeywell_code,
        "name_en": part.name_en,
        "name_tr": part.name_tr,
        "category": part.category,
        "score": score,
        "strategy": strategy,
    }
