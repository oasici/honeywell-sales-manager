"""LCS-ratio sequence similarity (V7).

Pure function — no DB access, easy to unit-test. Used by
``deal_similarity_service.refresh_similarity_links`` to blend
structured cosine similarity with sequence-order similarity, so two
deals with similar numeric stats but very different event histories
no longer score as ``1.0``.

Algorithm
---------
Longest Common Subsequence (LCS) over the V6 token list, normalized
by the longer sequence length. ``LCS / max(len(a), len(b))`` returns
[0, 1] where 1 means identical token order.

We deliberately use LCS (subsequence) rather than longest common
substring — buyer journeys often have the right tokens in the right
order even when other events interleave (e.g.
``[meeting, quote, followup]`` vs ``[meeting, email, quote, followup]``
should be near-identical, not partial matches).
"""

from __future__ import annotations

from collections.abc import Sequence


def lcs_length(a: Sequence[str], b: Sequence[str]) -> int:
    """Standard O(n·m) DP for longest common subsequence length."""
    if not a or not b:
        return 0
    n, m = len(a), len(b)
    # Single rolling row keeps memory at O(min(n, m)).
    if m < n:
        a, b = b, a
        n, m = m, n
    prev = [0] * (m + 1)
    curr = [0] * (m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev, curr = curr, prev
        # Reset the row we're about to write into.
        for j in range(m + 1):
            curr[j] = 0
    return prev[m]


def lcs_ratio(a: Sequence[str], b: Sequence[str]) -> float:
    """Normalized LCS in [0.0, 1.0]. Empty inputs return 0.0."""
    if not a or not b:
        return 0.0
    longer = max(len(a), len(b))
    if longer == 0:
        return 0.0
    return round(lcs_length(a, b) / longer, 4)


def blend_similarity(
    cosine_score: float,
    sequence_score: float,
    *,
    cosine_weight: float = 0.7,
    sequence_weight: float = 0.3,
) -> float:
    """Convex combination of cosine + LCS-ratio scores.

    Defaults bias toward the structured cosine because it covers more
    feature types (industry, amount band, stakeholder count etc.);
    sequence adds journey-shape signal on top.
    """
    total = cosine_weight + sequence_weight
    if total <= 0:
        return 0.0
    cw = cosine_weight / total
    sw = sequence_weight / total
    return round(cw * cosine_score + sw * sequence_score, 4)
