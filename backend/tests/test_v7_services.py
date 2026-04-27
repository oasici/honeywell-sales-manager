"""V7 final-stretch service tests.

Covers:
- bayesian_uplift: smoothing math, CI bounds, is_promotable gate
- sequence_similarity: LCS length/ratio + blend
- objection_llm_detector: flag-gating + parser validation (mocked Claude)
- objection_intelligence_service.detect_and_record_hybrid: routing
- tenant_context: scoped() filter helper + derive_tenant_count
- federated_benchmark_service: V7 source_tenant_ids path
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.user import User
from app.models.v5_objection import Objection
from app.models.v7_tenant import Tenant
from app.services import (
    bayesian_uplift,
    federated_benchmark_service,
    objection_intelligence_service,
    sequence_similarity,
    tenant_context,
)


# ─────────────────────── bayesian_uplift ─────────────────────────────


def test_uplift_with_zero_support_returns_baseline():
    stats = bayesian_uplift.compute_uplift(
        wins=0, support=0, baseline_winrate=0.3
    )
    assert stats.smoothed_winrate == pytest.approx(0.3)
    assert stats.uplift_score == 0.0
    assert stats.is_promotable is False


def test_uplift_with_strong_signal_above_baseline_is_promotable():
    # 18 of 20 wins vs baseline 0.3 — should beat baseline easily.
    stats = bayesian_uplift.compute_uplift(
        wins=18, support=20, baseline_winrate=0.3
    )
    assert stats.smoothed_winrate > 0.3
    assert stats.uplift_score > 0
    assert stats.ci_low > 0.3
    assert stats.is_promotable is True


def test_uplift_with_tiny_sample_is_not_promotable_even_with_high_winrate():
    # 2 of 2 wins — looks like 100% but sample too small.
    stats = bayesian_uplift.compute_uplift(
        wins=2, support=2, baseline_winrate=0.3
    )
    # is_promotable requires support ≥ 5
    assert stats.is_promotable is False


def test_uplift_below_baseline_is_not_promotable():
    stats = bayesian_uplift.compute_uplift(
        wins=2, support=20, baseline_winrate=0.3
    )
    assert stats.smoothed_winrate < 0.3 or stats.is_promotable is False


def test_uplift_clips_ci_to_unit_interval():
    stats = bayesian_uplift.compute_uplift(
        wins=100, support=100, baseline_winrate=0.5
    )
    assert 0.0 <= stats.ci_low <= 1.0
    assert 0.0 <= stats.ci_high <= 1.0


def test_uplift_handles_invalid_inputs_gracefully():
    stats = bayesian_uplift.compute_uplift(
        wins=10, support=5, baseline_winrate=0.3  # wins > support
    )
    assert stats.is_promotable is False


# ─────────────────────── sequence_similarity ─────────────────────────


def test_lcs_length_identical_sequences():
    assert sequence_similarity.lcs_length(["a", "b", "c"], ["a", "b", "c"]) == 3


def test_lcs_length_disjoint_sequences():
    assert sequence_similarity.lcs_length(["a", "b"], ["c", "d"]) == 0


def test_lcs_length_partial_match():
    assert (
        sequence_similarity.lcs_length(
            ["meeting", "quote", "followup"],
            ["meeting", "email", "quote", "followup"],
        )
        == 3
    )


def test_lcs_ratio_bounded():
    r = sequence_similarity.lcs_ratio(["a", "b", "c"], ["a", "x", "c"])
    assert 0.0 <= r <= 1.0


def test_lcs_ratio_empty_returns_zero():
    assert sequence_similarity.lcs_ratio([], ["a"]) == 0.0
    assert sequence_similarity.lcs_ratio(["a"], []) == 0.0


def test_blend_similarity_pure_cosine():
    out = sequence_similarity.blend_similarity(
        cosine_score=0.8, sequence_score=0.0, cosine_weight=1.0, sequence_weight=0.0
    )
    assert out == pytest.approx(0.8)


def test_blend_similarity_default_weights():
    out = sequence_similarity.blend_similarity(cosine_score=1.0, sequence_score=0.0)
    # 0.7*1 + 0.3*0 = 0.7
    assert out == pytest.approx(0.7)


# ─────────────────────── objection LLM detector ──────────────────────


@pytest.mark.asyncio
async def test_objection_llm_detector_returns_empty_when_flag_off():
    from app.services.objection_llm_detector import detect_with_llm

    out = await detect_with_llm("This deal is too expensive and we have security concerns")
    assert out == []


@pytest.mark.asyncio
async def test_objection_llm_detector_returns_empty_for_blank_input():
    from app.services.objection_llm_detector import detect_with_llm

    assert await detect_with_llm("") == []
    assert await detect_with_llm("   \n") == []
    assert await detect_with_llm(None) == []


@pytest.mark.asyncio
async def test_objection_llm_detector_parses_valid_response():
    from app.services.objection_llm_detector import detect_with_llm

    fake_response = SimpleNamespace(
        content=[
            SimpleNamespace(
                text='{"objections": [{"objection_type": "price", "severity": "high", "evidence_text": "too expensive"}]}'
            )
        ]
    )
    with patch("app.services.objection_llm_detector.settings") as ms, patch(
        "app.services.objection_llm_detector.claude_messages_create",
        new=AsyncMock(return_value=fake_response),
    ):
        ms.FEATURE_V7_LLM_OBJECTION = True
        ms.ANTHROPIC_API_KEY = "sk-test"
        ms.AI_MODEL_NAME = "claude-haiku-4-5"
        out = await detect_with_llm("anything")
    assert len(out) == 1
    assert out[0].objection_type == "price"
    assert out[0].severity == "high"


@pytest.mark.asyncio
async def test_objection_llm_detector_rejects_invalid_type():
    from app.services.objection_llm_detector import detect_with_llm

    fake_response = SimpleNamespace(
        content=[
            SimpleNamespace(
                text='{"objections": [{"objection_type": "made_up_type", "severity": "med", "evidence_text": "x"}]}'
            )
        ]
    )
    with patch("app.services.objection_llm_detector.settings") as ms, patch(
        "app.services.objection_llm_detector.claude_messages_create",
        new=AsyncMock(return_value=fake_response),
    ):
        ms.FEATURE_V7_LLM_OBJECTION = True
        ms.ANTHROPIC_API_KEY = "sk-test"
        ms.AI_MODEL_NAME = "claude-haiku-4-5"
        out = await detect_with_llm("anything")
    assert out == []


# ─────────────────────── hybrid detect path ──────────────────────────


async def _seed_opp(db: AsyncSession) -> Opportunity:
    user = User(
        email="rep_v7@test.com",
        full_name="Rep V7",
        hashed_password=hash_password("Test1234"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    cust = Customer(
        name="V7 Acme",
        company="V7 Acme",
        email="v7@test.com",
        phone="",
        address="",
        tax_id="",
    )
    db.add(cust)
    await db.commit()
    await db.refresh(user)
    await db.refresh(cust)

    opp = Opportunity(
        customer_id=cust.id,
        owner_id=user.id,
        title="V7 Deal",
        stage="qualified",
        status="active",
        amount=300_000,
        currency="TRY",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


@pytest.mark.asyncio
async def test_hybrid_keyword_only_when_flag_off(db: AsyncSession):
    opp = await _seed_opp(db)
    out = await objection_intelligence_service.detect_and_record_hybrid(
        db, opportunity_id=opp.id, text="Bu fiyat çok pahalı"
    )
    # Keyword detector matches "pahalı" → price objection.
    assert any(o.objection_type == "price" for o in out)


@pytest.mark.asyncio
async def test_hybrid_returns_empty_for_unrecognized_text(db: AsyncSession):
    opp = await _seed_opp(db)
    out = await objection_intelligence_service.detect_and_record_hybrid(
        db, opportunity_id=opp.id, text="Lorem ipsum dolor sit amet."
    )
    assert out == []


# ─────────────────────── tenant_context ──────────────────────────────


def test_scoped_returns_stmt_unchanged_for_none_tenant():
    stmt = select(Objection)
    out = tenant_context.scoped(stmt, None, column=Objection.id)
    assert out is stmt


def test_scoped_adds_filter_when_tenant_set():
    stmt = select(Objection)
    out = tenant_context.scoped(stmt, 42, column=Objection.id)
    compiled = str(out.compile(compile_kwargs={"literal_binds": True}))
    assert "objections.id = 42" in compiled


def test_derive_tenant_count_dedupes():
    assert tenant_context.derive_tenant_count([1, 2, 2, 3, 3, 3]) == 3
    assert tenant_context.derive_tenant_count([]) == 0


@pytest.mark.asyncio
async def test_ensure_tenant_is_idempotent(db: AsyncSession):
    first = await tenant_context.ensure_tenant(db, name="acme-co")
    second = await tenant_context.ensure_tenant(db, name="acme-co")
    await db.commit()
    assert first.id == second.id
    rows = (await db.execute(select(Tenant).where(Tenant.name == "acme-co"))).scalars().all()
    assert len(rows) == 1


# ─────────────────────── federated benchmark V7 path ─────────────────


@pytest.mark.asyncio
async def test_federated_publish_uses_source_tenant_ids(db: AsyncSession):
    row = await federated_benchmark_service.publish_benchmark(
        db,
        benchmark_key="industrial_midmarket",
        metric_name="avg_discount",
        metric_value=0.18,
        sample_size=50,
        source_tenant_ids=[1, 2, 2, 3, 3, 3, 4, 5, 6, 7],  # 7 distinct
    )
    assert row.tenant_count == 7
    assert row.suppressed is False
    assert row.metric_value == pytest.approx(0.18)


@pytest.mark.asyncio
async def test_federated_publish_source_ids_below_threshold_suppressed(
    db: AsyncSession,
):
    row = await federated_benchmark_service.publish_benchmark(
        db,
        benchmark_key="industrial_midmarket",
        metric_name="avg_discount",
        metric_value=0.18,
        sample_size=50,
        source_tenant_ids=[1, 2],  # only 2 distinct
    )
    assert row.tenant_count == 2
    assert row.suppressed is True
    assert row.metric_value is None
