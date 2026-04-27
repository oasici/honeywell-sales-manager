"""V8 service tests — text embedder, multi-tenant CRM helpers, seed sanity."""

from __future__ import annotations

import math

import pytest

from app.services import text_embedder, tenant_context


# ─────────────────────── text_embedder ───────────────────────────────


def test_embed_tokens_returns_default_dim_vector():
    vec = text_embedder.embed_tokens(["meeting_logged", "quote_sent"])
    assert len(vec) == text_embedder.DEFAULT_DIM


def test_embed_tokens_is_l2_normalised():
    vec = text_embedder.embed_tokens(["meeting_logged", "quote_sent", "followup_within_24h_after_quote"])
    norm = math.sqrt(sum(v * v for v in vec))
    assert norm == pytest.approx(1.0, abs=1e-3)


def test_embed_tokens_empty_returns_zero_vector():
    vec = text_embedder.embed_tokens([])
    assert all(v == 0.0 for v in vec)
    assert len(vec) == text_embedder.DEFAULT_DIM


def test_embed_tokens_deterministic_for_same_input():
    a = text_embedder.embed_tokens(["meeting_logged", "quote_sent"])
    b = text_embedder.embed_tokens(["meeting_logged", "quote_sent"])
    assert a == b


def test_embed_tokens_distinguishes_different_sequences():
    a = text_embedder.embed_tokens(["meeting_logged", "quote_sent"])
    b = text_embedder.embed_tokens(["objection_logged", "stage_changed"])
    assert a != b
    sim = text_embedder.cosine(a, b)
    assert -1.0 <= sim <= 1.0
    assert sim < 0.5  # disjoint sequences should have low cosine


def test_embed_tokens_identical_have_cosine_one():
    a = text_embedder.embed_tokens(["meeting_logged", "quote_sent"])
    b = text_embedder.embed_tokens(["meeting_logged", "quote_sent"])
    assert text_embedder.cosine(a, b) == pytest.approx(1.0, abs=1e-3)


def test_vocab_hash_changes_with_vocabulary():
    h1 = text_embedder.vocab_hash(["a", "b"])
    h2 = text_embedder.vocab_hash(["a", "b", "c"])
    assert h1 != h2


def test_vocab_hash_stable_for_permutations():
    """Hash is over the *set* of tokens — order shouldn't matter."""
    h1 = text_embedder.vocab_hash(["meeting_logged", "quote_sent"])
    h2 = text_embedder.vocab_hash(["quote_sent", "meeting_logged"])
    assert h1 == h2


def test_cosine_handles_zero_vectors():
    z = [0.0] * text_embedder.DEFAULT_DIM
    a = text_embedder.embed_tokens(["meeting_logged"])
    assert text_embedder.cosine(z, a) == 0.0


# ─────────────────────── tenant_context CRM helpers ──────────────────


def test_scoped_for_user_with_tenant():
    from sqlalchemy import select

    from app.models.user import User

    stmt = select(User)
    fake_user = type("U", (), {"tenant_id": 5})()
    out = tenant_context.scoped_for_user(stmt, fake_user, column=User.tenant_id)
    compiled = str(out.compile(compile_kwargs={"literal_binds": True}))
    assert "users.tenant_id = 5" in compiled


def test_scoped_for_user_without_tenant_returns_unchanged():
    from sqlalchemy import select

    from app.models.user import User

    stmt = select(User)
    fake_user = type("U", (), {"tenant_id": None})()
    out = tenant_context.scoped_for_user(stmt, fake_user, column=User.tenant_id)
    assert out is stmt


def test_scoped_for_user_with_none_user_returns_unchanged():
    from sqlalchemy import select

    from app.models.user import User

    stmt = select(User)
    out = tenant_context.scoped_for_user(stmt, None, column=User.tenant_id)
    assert out is stmt


@pytest.mark.asyncio
async def test_resolve_tenant_id_prefers_header(db):
    out = await tenant_context.resolve_tenant_id(
        db, header_tenant_id=99, user_tenant_id=42
    )
    assert out == 99


@pytest.mark.asyncio
async def test_resolve_tenant_id_falls_back_to_user(db):
    out = await tenant_context.resolve_tenant_id(
        db, header_tenant_id=None, user_tenant_id=42
    )
    assert out == 42


@pytest.mark.asyncio
async def test_resolve_tenant_id_returns_none_when_both_missing(db):
    out = await tenant_context.resolve_tenant_id(
        db, header_tenant_id=None, user_tenant_id=None
    )
    assert out is None


# ─────────────────────── seed importability ──────────────────────────


def test_seed_v8_full_demo_module_imports():
    """The seed module must at least be syntactically valid + import-clean."""
    import scripts.seed_v8_full_demo  # noqa: F401
