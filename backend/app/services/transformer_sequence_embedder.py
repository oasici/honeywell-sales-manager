"""V12 transformer-based sequence embedder.

V8 introduced a 256-dim bigram-BoW *shape* embedding for opportunity
event sequences (`text_embedder.py`) — fast, dependency-free, and
deterministic. V12 augments that with a transformer-based encoder
that captures **semantic** similarity between event sequences ("cold
deal that warmed up" should be near "stalled deal that re-engaged"
even when the literal token sets diverge).

Design choices
--------------
- Reuses the **same** ``sentence-transformers`` model the spare
  parts catalog already loads (``paraphrase-multilingual-MiniLM-
  L12-v2``) — no new download, no new memory pressure when the
  feature flag flips on.
- Encodes a *humanised* version of the V6 token list ("meeting
  logged → quote sent → followup within 24h …") rather than the raw
  symbolic tokens, so the multilingual model can apply its semantic
  prior. The mapping is centralised in :func:`_humanise_tokens`.
- Output dim = 384 (the MiniLM family default) and L2-normalised so
  cosine similarity is the dot product.
- Fully **opt-in** via ``FEATURE_TRANSFORMER_SEQ_EMBEDDING``.
  Single-tenant deployments without the flag never load the model
  and never write to the new table — same UX as V8 when V8 was off.
- The encoder is a **module-level singleton** lazy-loaded on first
  use to keep cold-start latency at the first opp encode rather
  than at process boot.

Tests mock the model via ``set_test_model`` to keep CI fast.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)


VERSION = "v12-minilm-multilingual-384"
DEFAULT_DIM = 384


_model: Any | None = None
_test_model: Any | None = None


def _get_model() -> Any:
    """Lazy-load + cache the SentenceTransformer model.

    Returns the test stub when one was injected via ``set_test_model``
    (CI / unit tests). Otherwise loads ``paraphrase-multilingual-
    MiniLM-L12-v2`` — the same model used by ``embedding_service``,
    so the weights are already downloaded in the prod image.
    """
    if _test_model is not None:
        return _test_model
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover — exercised in CI
            raise RuntimeError(
                "sentence-transformers required for transformer sequence embedding"
            ) from exc
        _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        logger.info("Transformer sequence embedder loaded (%s)", VERSION)
    return _model


def set_test_model(model: Any | None) -> None:
    """Inject a stub model (tests only).

    Pass an object with ``encode(list[str]) -> np.ndarray`` semantics
    to bypass the real model. ``None`` resets to production behaviour.
    """
    global _test_model
    _test_model = model


# ─────────────────────── token humanisation ──────────────────────────


# V6 symbolic tokens → short English phrases the multilingual model
# can reason about. Keys are the canonical token names produced by
# ``sequence_tokenizer.tokenize``. Unknown tokens fall back to the
# tokenized form ``snake_case → "snake case"`` so a new tokenizer
# vocab doesn't break the encoder — it just gets weaker semantics
# for the new tokens until we map them here.
_TOKEN_PHRASES: dict[str, str] = {
    "meeting_logged": "in-person meeting completed",
    "call_logged": "phone call logged",
    "email_sent": "outbound email sent",
    "email_received": "inbound email received from buyer",
    "quote_sent": "quote sent to buyer",
    "quote_revised": "quote revised after feedback",
    "stage_advanced": "deal stage advanced",
    "stage_regressed": "deal stage moved backward",
    "no_response_7d": "no buyer response for one week",
    "no_response_14d": "no buyer response for two weeks",
    "competitor_mentioned": "competitor mentioned",
    "budget_concern": "budget concern surfaced",
    "discount_requested": "discount request",
    "high_discount_applied": "large discount applied",
    "decision_maker_added": "decision maker added to the deal",
    "stakeholder_added": "stakeholder added",
    "objection_raised": "objection raised",
    "objection_resolved": "objection resolved",
    "followup_within_24h_after_quote": "fast followup within 24 hours of quote",
    "deal_created": "deal opened",
    "deal_won": "deal closed won",
    "deal_lost": "deal closed lost",
}


def _humanise_token(token: str) -> str:
    if token in _TOKEN_PHRASES:
        return _TOKEN_PHRASES[token]
    return token.replace("_", " ")


def _humanise_tokens(tokens: Sequence[str]) -> str:
    """Render token sequence as a short narrative for the encoder."""
    if not tokens:
        return ""
    parts = [_humanise_token(t) for t in tokens]
    return " then ".join(parts)


# ─────────────────────── public API ──────────────────────────────────


def embed_tokens(tokens: Sequence[str]) -> list[float]:
    """Return a transformer-derived L2-normalised vector for ``tokens``.

    Empty input returns the zero vector (caller should skip writing
    it). Errors loading/running the model bubble up as ``RuntimeError``
    so callers can fall back to V8 BoW + LCS.
    """
    if not tokens:
        return [0.0] * DEFAULT_DIM
    text = _humanise_tokens(tokens)
    model = _get_model()
    raw = model.encode([text], normalize_embeddings=True, show_progress_bar=False)
    if hasattr(raw, "tolist"):
        vec = raw[0].tolist()
    else:  # plain list-of-list stub
        vec = list(raw[0])
    if len(vec) != DEFAULT_DIM:
        # Defensive — accept any dim the model returns, but record
        # the mismatch so the migration / config can be audited.
        logger.warning(
            "Transformer encoder returned dim=%d, expected %d", len(vec), DEFAULT_DIM
        )
    return [round(float(v), 6) for v in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity for two pre-normalised vectors (dot product).

    Falls back to the safe formula when one or both vectors aren't
    L2-unit length, so callers can pass raw vectors without first
    normalising them.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return round(dot / (na * nb), 4)
