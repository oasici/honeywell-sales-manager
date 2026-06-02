"""Round-17 catalog cross-check + fuzzy match for parsed parts.

The LLM extracts part codes from email body / attachments using a
regex + Honeywell-prefix heuristic, but it has no way to know
whether the code actually exists in the catalog. Common failure
modes:

* OCR-style typos (``C7061A1O12`` with a letter O instead of zero)
* Customer abbreviation (``C7061`` instead of full ``C7061A1012``)
* Trailing whitespace / hyphens / hidden characters from Excel cells
* Genuinely unknown / discontinued parts

This module resolves a parsed code to a real ``SparePart`` row,
applying a confidence ladder:

  * **exact** — case-insensitive direct match
  * **normalized** — strip whitespace/hyphens and re-compare
  * **fuzzy_prefix** — code is a prefix of exactly one catalog row
  * **fuzzy_levenshtein** — edit distance ≤ 2 to exactly one row
  * **unknown** — nothing matched

The caller (``EmailProcessingService._apply_parsed_data`` and the
auto-quote path) reads the verdict and decides whether to auto-fill
the line item or route to review.

No external fuzzy library — we use a minimal Damerau-Levenshtein
implementation tuned for short tokens (part codes are typically
8-15 chars).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spare_part import SparePart

logger = logging.getLogger(__name__)

# A "structurally complete" code: a letter prefix followed by digits,
# carrying enough digits that a single-digit edit yields a *different real
# part* rather than a typo (e.g. …1011 vs …1012).
_FULL_CODE_RE = re.compile(r"^[a-z]+\d")


def _looks_like_full_code(norm: str) -> bool:
    return (
        bool(_FULL_CODE_RE.match(norm))
        and sum(c.isdigit() for c in norm) >= 3
        and len(norm) >= 6
    )


def _letters_only(s: str) -> list[str]:
    return [c for c in s if c.isalpha()]


@dataclass(frozen=True)
class CatalogResolution:
    """Verdict for a single part-code lookup.

    ``status`` is one of ``exact`` / ``normalized`` / ``fuzzy_prefix``
    / ``fuzzy_levenshtein`` / ``unknown``. The resolver populates
    ``part_id`` and ``canonical_code`` for everything except
    ``unknown``; review-queue UI can render the original code alongside
    the canonical one + status so the operator confirms or rejects.
    """

    input_code: str
    status: str
    canonical_code: str | None = None
    part_id: int | None = None
    edit_distance: int | None = None


def _normalize(code: str) -> str:
    """Lowercase + strip whitespace/hyphens/underscores."""
    return (
        (code or "")
        .strip()
        .lower()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )


def _damerau_levenshtein(a: str, b: str, *, cap: int = 3) -> int:
    """Optimal string-alignment (Damerau-Levenshtein restricted) distance.

    Supports the four standard edit operations: insert, delete,
    substitute, and adjacent-character transposition. Uses a full
    2D matrix because part codes are short (≤ 20 chars) — the
    memory cost is negligible and the implementation is easier to
    audit than rolling-row optimizations.

    Returns ``cap + 1`` early when the length delta alone already
    exceeds ``cap`` (cheapest possible distance is ``abs(la - lb)``).
    """
    la, lb = len(a), len(b)
    if abs(la - lb) > cap:
        return cap + 1
    if la == 0:
        return lb
    if lb == 0:
        return la

    # d[i][j] = edit distance between a[:i] and b[:j].
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j

    for i in range(1, la + 1):
        row_min = d[i][0]
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,        # deletion
                d[i][j - 1] + 1,        # insertion
                d[i - 1][j - 1] + cost,  # substitution
            )
            # Adjacent transposition (OSA variant — uses ``d[i-2][j-2]``).
            if (
                i > 1
                and j > 1
                and a[i - 1] == b[j - 2]
                and a[i - 2] == b[j - 1]
            ):
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
            if d[i][j] < row_min:
                row_min = d[i][j]
        if row_min > cap:
            return cap + 1
    return d[la][lb]


async def resolve_part_code(
    db: AsyncSession,
    code: str,
    *,
    tenant_id: int | None = None,
) -> CatalogResolution:
    """Resolve one parsed part code against the SparePart catalog.

    ``tenant_id`` is accepted for forward-compat: today the catalog
    is global (Honeywell parts are not per-tenant), but the
    signature lets us add tenant scoping later without rippling
    through the callers.
    """
    if not code or not code.strip():
        return CatalogResolution(input_code=code or "", status="unknown")
    raw = code.strip()
    norm = _normalize(raw)

    # 1. Exact (case-insensitive).
    stmt = select(SparePart.id, SparePart.honeywell_code).where(
        func.lower(SparePart.honeywell_code) == raw.lower()
    )
    row = (await db.execute(stmt)).first()
    if row:
        return CatalogResolution(
            input_code=raw,
            status="exact",
            canonical_code=row.honeywell_code,
            part_id=row.id,
        )

    # 2. Normalized comparison (strip hyphens/spaces).
    stmt = select(SparePart.id, SparePart.honeywell_code)
    rows = (await db.execute(stmt)).all()
    if not rows:
        return CatalogResolution(input_code=raw, status="unknown")

    # M2 — detect normalized-key collisions: two *distinct* catalog SKUs
    # that normalize to the same key. Auto-resolving to either is a coin
    # flip (the pre-fix dict-comprehension silently kept whichever sorted
    # last), so treat such keys as ambiguous and route to review.
    norm_to_rows: dict[str, list] = {}
    for r in rows:
        norm_to_rows.setdefault(_normalize(r.honeywell_code), []).append(r)

    colliding = {
        k
        for k, group in norm_to_rows.items()
        if len({x.honeywell_code for x in group}) > 1
    }
    if norm in colliding:
        logger.warning(
            "Catalog normalized-key collision for %r: codes %s — routing to "
            "review instead of guessing.",
            norm,
            sorted({x.honeywell_code for x in norm_to_rows[norm]}),
        )
        return CatalogResolution(input_code=raw, status="unknown")

    norm_to_row = {k: g[0] for k, g in norm_to_rows.items() if k not in colliding}
    if norm in norm_to_row:
        match = norm_to_row[norm]
        return CatalogResolution(
            input_code=raw,
            status="normalized",
            canonical_code=match.honeywell_code,
            part_id=match.id,
        )

    # 3. Unique prefix match (customer truncated the suffix).
    prefix_matches = [r for k, r in norm_to_row.items() if k.startswith(norm) and len(norm) >= 4]
    if len(prefix_matches) == 1:
        match = prefix_matches[0]
        return CatalogResolution(
            input_code=raw,
            status="fuzzy_prefix",
            canonical_code=match.honeywell_code,
            part_id=match.id,
        )

    # 4. Damerau-Levenshtein ≤ 2 with unique winner.
    best: tuple[int, SparePart | None] = (99, None)
    for k, r in norm_to_row.items():
        d = _damerau_levenshtein(norm, k, cap=2)
        if d < best[0]:
            best = (d, r)
        elif d == best[0]:
            # Tie — don't auto-resolve; return unknown so the operator picks.
            best = (d, None)
    if best[1] is not None and best[0] <= 2:
        match = best[1]
        cand_norm = _normalize(match.honeywell_code)
        # M1 — when the *input* is a structurally-complete code and the
        # near candidate differs only in its digits (identical letter
        # skeleton), the candidate is almost certainly a *different real
        # part* (…1011 vs …1012), not a typo. Refuse to suggest it. OCR
        # letter↔digit slips (e.g. "C7061A1O12" → "C7061A1012") change the
        # letter skeleton and are still resolved.
        if (
            _looks_like_full_code(norm)
            and norm != cand_norm
            and _letters_only(norm) == _letters_only(cand_norm)
        ):
            logger.info(
                "Levenshtein match %r→%r suppressed (full code, digit-only "
                "difference) — routing to review.",
                raw,
                match.honeywell_code,
            )
            return CatalogResolution(input_code=raw, status="unknown")
        return CatalogResolution(
            input_code=raw,
            status="fuzzy_levenshtein",
            canonical_code=match.honeywell_code,
            part_id=match.id,
            edit_distance=best[0],
        )

    return CatalogResolution(input_code=raw, status="unknown")


async def resolve_parsed_parts(
    db: AsyncSession,
    parts: list[dict],
    *,
    tenant_id: int | None = None,
) -> list[dict]:
    """Annotate a parsed-parts list with catalog resolution verdicts.

    Mutates each entry by adding ``catalog_status`` / ``catalog_part_id``
    / ``canonical_part_code``. Doesn't replace the original
    ``part_code`` — the operator (or the auto-quote logic) chooses
    whether to trust the resolver. Returns a new list.
    """
    out: list[dict] = []
    for entry in parts or []:
        new = dict(entry)
        code = new.get("part_code") or ""
        if not code:
            new["catalog_status"] = "no_code"
            out.append(new)
            continue
        verdict = await resolve_part_code(db, code, tenant_id=tenant_id)
        new["catalog_status"] = verdict.status
        new["canonical_part_code"] = verdict.canonical_code
        new["catalog_part_id"] = verdict.part_id
        if verdict.edit_distance is not None:
            new["catalog_edit_distance"] = verdict.edit_distance
        out.append(new)
    return out
