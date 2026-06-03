"""Catalog-aware part-code extraction (audit F-A).

The regex / heuristic extractors only recognize *shaped* codes
(letter+digits, hyphenated). Real Honeywell catalogs also contain pure
numeric codes (``764744``) and short alphanumerics (``HDZWM2``) that no
pattern can safely guess without false positives (a bare ``764744`` looks
like a price or a year in free text).

This scanner sidesteps the pattern entirely: it matches text tokens
against the **actual catalog codes** (the uploaded spare-parts file). So
recall is "any code we actually sell" and false positives are ~zero — a
token only counts if, after normalization, it equals a real catalog code.

Used as an always-on augmentation in ``EmailProcessingService``: codes the
LLM missed — or that a Claude outage left to the (pattern-blind) regex
fallback — are still recovered, each with a best-effort line quantity
(flagged ``quantity_suspect`` when the quantity couldn't be read).
"""

from __future__ import annotations

import re

from app.services.part_catalog_resolver import _normalize

# Quantity with an explicit unit ("2 adet", "3 qty", "x5") is the strong
# signal; a bare integer on the line is the weak fallback.
_QTY_UNIT_RE = re.compile(
    r"(\d{1,6})\s*(?:adet|ad|tane|qty|pcs|pieces|pc|x)\b", re.IGNORECASE
)
_INT_RE = re.compile(r"\b(\d{1,6})\b")

# Don't try to match very short normalized tokens as codes — too collision
# prone. Real catalog codes are comfortably longer.
_MIN_NORM_LEN = 4


def _line_quantity(line: str, matched_text: str) -> tuple[int, bool]:
    """Best-effort quantity for a line, ignoring the matched code's digits.

    Returns ``(quantity, suspect)``; ``suspect`` is True when no quantity
    could be read (defaults to 1) so the line routes to review.
    """
    remainder = line.replace(matched_text, " ", 1)
    m = _QTY_UNIT_RE.search(remainder)
    if m:
        return int(m.group(1)), False
    m = _INT_RE.search(remainder)
    if m:
        return int(m.group(1)), False
    return 1, True


def scan_text_for_catalog_codes(
    text: str, norm_to_code: dict[str, str]
) -> list[dict]:
    """Find catalog codes present in ``text``.

    ``norm_to_code`` maps ``_normalize(code) -> canonical_code`` for the
    active catalog. Matching is line-oriented (RFQs list one part per
    line) and checks each token plus adjacent token pairs, so a spaced
    variant like ``HDZ WM2`` collapses to the catalog's ``HDZWM2``.
    Returns part dicts ``{part_code, quantity, urgency, source}`` (with
    ``quantity_suspect`` when the quantity was a guess), deduped by code.
    """
    if not text or not norm_to_code:
        return []

    out: list[dict] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        tokens = re.split(r"\s+", line)
        match_norm: str | None = None
        match_text: str | None = None
        for i, tok in enumerate(tokens):
            candidates = [(tok, tok)]
            if i + 1 < len(tokens):
                candidates.append((tok + tokens[i + 1], f"{tok} {tokens[i + 1]}"))
            for cand, original in candidates:
                norm = _normalize(cand)
                if len(norm) >= _MIN_NORM_LEN and norm in norm_to_code:
                    match_norm, match_text = norm, original
                    break
            if match_norm:
                break

        if not match_norm or match_norm in seen:
            continue
        seen.add(match_norm)
        qty, suspect = _line_quantity(line, match_text or "")
        row: dict = {
            "part_code": norm_to_code[match_norm],
            "quantity": qty,
            "urgency": "normal",
            "source": "catalog_scan",
        }
        if suspect:
            row["quantity_suspect"] = True
        out.append(row)
    return out
