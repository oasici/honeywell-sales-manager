"""Sequence text embedder (V8).

Produces a fixed-length, L2-normalised vector for an opportunity's
behavioural token sequence — a "transformer-shape" embedding without
the model weights. The interface is drop-in compatible with a real
embedder (sentence-transformers, OpenAI embeddings) so we can swap
the implementation without touching the similarity service.

Algorithm
---------
1. Build a feature list from the V6 token sequence:
   - every unigram token (e.g. ``meeting_logged``)
   - every bigram (e.g. ``meeting_logged>quote_sent``)
   - every "after" pair within a 3-event window (captures non-adjacent
     sequence dependencies, the closest we get to attention)
2. Hash each feature into [0, dim) buckets via deterministic sha1.
3. Increment the bucket; bigrams contribute 0.6× weight (sequence
   order is informative but not dominant).
4. L2-normalise so cosine similarity is meaningful out of the box.

The vector is **deterministic** for a given input — re-encoding the
same sequence yields the same vector. This is intentional so we
don't churn DB writes.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from typing import Iterable


VERSION = "v8-bigram-bow-256"
DEFAULT_DIM = 256
_BIGRAM_WEIGHT = 0.6
_LOOKAHEAD_WEIGHT = 0.4


def _hash_to_bucket(feature: str, dim: int) -> int:
    """Deterministic feature → bucket mapping."""
    # Feature-hashing bucket, not a security hash (Bandit B324).
    digest = hashlib.sha1(feature.encode("utf-8"), usedforsecurity=False).digest()
    # Take 4 bytes → uint → mod dim.
    return int.from_bytes(digest[:4], "big") % dim


def vocab_hash(tokens: Sequence[str]) -> str:
    """Short hash of the *sorted unique* token set.

    Lets downstream code detect when the input vocabulary drifted
    (new token added by the tokenizer) so embeddings can be
    invalidated en masse.
    """
    if not tokens:
        return "0" * 12
    canonical = ",".join(sorted({str(t) for t in tokens}))
    # Vocabulary-drift digest, not a security hash (Bandit B324).
    return hashlib.sha1(
        canonical.encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:12]


def _features(tokens: Sequence[str]) -> Iterable[tuple[str, float]]:
    """Yield (feature_string, weight) pairs for a token list."""
    n = len(tokens)
    for i, tok in enumerate(tokens):
        yield (tok, 1.0)
        if i + 1 < n:
            yield (f"{tok}>{tokens[i + 1]}", _BIGRAM_WEIGHT)
        # 3-event lookahead — captures non-adjacent dependencies
        # without quadratic blowup. ("meeting_logged" near
        # "quote_sent" two events later is still a meaningful pattern).
        for j in range(i + 2, min(i + 4, n)):
            yield (f"{tok}~{tokens[j]}", _LOOKAHEAD_WEIGHT)


def embed_tokens(tokens: Sequence[str], dim: int = DEFAULT_DIM) -> list[float]:
    """Return an ``dim``-length L2-normalised vector for ``tokens``.

    Empty input yields the zero vector — caller decides whether to
    skip writing it (we do, in ``upsert_text_embedding``).
    """
    if dim <= 0:
        raise ValueError("dim must be > 0")

    vec = [0.0] * dim
    if not tokens:
        return vec

    for feature, weight in _features(tokens):
        bucket = _hash_to_bucket(feature, dim)
        vec[bucket] += weight

    # L2 normalise.
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [round(v / norm, 6) for v in vec]
    return vec


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Pre-normalised vectors → dot product is cosine."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return round(sum(x * y for x, y in zip(a, b)), 4)
