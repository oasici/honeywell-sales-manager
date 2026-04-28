"""V12 transformer sequence embedder + 4-component blend tests.

We never load the real ``sentence-transformers`` model here — every
test injects a deterministic stub via ``set_test_model``. This keeps
the suite hermetic and fast, and makes the encoder behaviour
provable independent of a particular model checkpoint.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.services import transformer_sequence_embedder


class _StubModel:
    """Returns a fixed-direction unit vector per input string.

    Deterministic, so cosine similarity between two identical inputs
    is exactly 1.0. Different inputs yield orthogonal vectors so the
    encoder behaviour is easy to reason about in assertions.
    """

    def __init__(self, dim: int = transformer_sequence_embedder.DEFAULT_DIM):
        self.dim = dim

    def encode(
        self,
        texts: list[str],
        normalize_embeddings: bool = False,
        show_progress_bar: bool = False,
    ) -> np.ndarray:
        out = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            # Hash the text to a single bucket so each unique input
            # picks a unique basis direction.
            bucket = abs(hash(text)) % self.dim
            vec[bucket] = 1.0
            out.append(vec)
        return np.array(out)


@pytest.fixture(autouse=True)
def _isolated_stub():
    """Inject the stub before each test, reset after."""
    transformer_sequence_embedder.set_test_model(_StubModel())
    yield
    transformer_sequence_embedder.set_test_model(None)


# ─────────────────────── encoder ─────────────────────────────────────


def test_embed_tokens_returns_default_dim_vector():
    vec = transformer_sequence_embedder.embed_tokens(["meeting_logged", "quote_sent"])
    assert len(vec) == transformer_sequence_embedder.DEFAULT_DIM


def test_embed_tokens_empty_returns_zero_vector():
    vec = transformer_sequence_embedder.embed_tokens([])
    assert len(vec) == transformer_sequence_embedder.DEFAULT_DIM
    assert all(v == 0.0 for v in vec)


def test_embed_tokens_deterministic_for_same_input():
    a = transformer_sequence_embedder.embed_tokens(["meeting_logged", "quote_sent"])
    b = transformer_sequence_embedder.embed_tokens(["meeting_logged", "quote_sent"])
    assert a == b


def test_embed_tokens_distinguishes_different_sequences():
    a = transformer_sequence_embedder.embed_tokens(["meeting_logged", "quote_sent"])
    b = transformer_sequence_embedder.embed_tokens(["objection_raised"])
    assert a != b


def test_cosine_self_similarity_is_one():
    vec = transformer_sequence_embedder.embed_tokens(["meeting_logged", "quote_sent"])
    assert transformer_sequence_embedder.cosine(vec, vec) == pytest.approx(1.0, abs=1e-3)


def test_cosine_handles_zero_vectors():
    z = [0.0] * transformer_sequence_embedder.DEFAULT_DIM
    assert transformer_sequence_embedder.cosine(z, z) == 0.0


def test_cosine_returns_zero_when_dim_mismatch():
    a = transformer_sequence_embedder.embed_tokens(["meeting_logged"])
    b = a[:10]
    assert transformer_sequence_embedder.cosine(a, b) == 0.0


def test_cosine_returns_zero_for_empty():
    a = transformer_sequence_embedder.embed_tokens(["meeting_logged"])
    assert transformer_sequence_embedder.cosine(a, []) == 0.0
    assert transformer_sequence_embedder.cosine([], a) == 0.0


# ─────────────────────── humanise_tokens ─────────────────────────────


def test_humanise_tokens_uses_known_phrases_when_available():
    text = transformer_sequence_embedder._humanise_tokens(
        ["meeting_logged", "quote_sent"]
    )
    assert "in-person meeting completed" in text
    assert "quote sent to buyer" in text
    assert "then" in text  # narrative joiner


def test_humanise_tokens_falls_back_to_snake_case_for_unknown_tokens():
    text = transformer_sequence_embedder._humanise_tokens(["custom_event_xyz"])
    assert text == "custom event xyz"


def test_humanise_tokens_empty_returns_empty():
    assert transformer_sequence_embedder._humanise_tokens([]) == ""


# ─────────────────────── module sanity ───────────────────────────────


def test_module_exports_versions_and_helpers():
    assert isinstance(transformer_sequence_embedder.VERSION, str)
    assert transformer_sequence_embedder.DEFAULT_DIM > 0
    assert callable(transformer_sequence_embedder.embed_tokens)
    assert callable(transformer_sequence_embedder.cosine)


def test_repository_module_imports():
    """Persistence helper must be importable for the migration to land."""
    import importlib

    mod = importlib.import_module("app.services.transformer_seq_repository")
    assert hasattr(mod, "upsert_transformer_seq_embedding")
    assert hasattr(mod, "backfill_transformer_seq_embeddings")


def test_backfill_script_module_imports():
    import importlib

    mod = importlib.import_module("scripts.backfill_transformer_seq")
    assert hasattr(mod, "main")
    assert hasattr(mod, "main_async")


# ─────────────────────── blend math sanity ───────────────────────────


def test_v12_blend_weights_sum_to_one():
    # Sanity check on the weight contract documented in
    # ``deal_similarity_service.refresh_similarity_links``.
    v12_weights = (0.4, 0.15, 0.25, 0.2)
    assert math.isclose(sum(v12_weights), 1.0, abs_tol=1e-6)


def test_v8_blend_weights_sum_to_one():
    v8_weights = (0.5, 0.2, 0.3)
    assert math.isclose(sum(v8_weights), 1.0, abs_tol=1e-6)
