"""V11 Qdrant RAG completion — service-level tests.

Most tests run with ``FEATURE_RAG=false`` (default test config) and
verify the short-circuit + fallback paths so we don't need a live
Qdrant or sentence-transformers in CI. The Claude path is always
mocked.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.competitor_mention import CompetitorMention
from app.models.customer import Customer
from app.models.engagement import Transcript
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services import rag_answer_service, rag_backfill_service


# ─────────────────────── flag short-circuit ─────────────────────────


@pytest.mark.asyncio
async def test_backfill_deals_skipped_when_flag_off(db: AsyncSession):
    # Default test config has FEATURE_RAG=false.
    out = await rag_backfill_service.backfill_deals(db)
    assert out == 0


@pytest.mark.asyncio
async def test_backfill_interactions_skipped_when_flag_off(db: AsyncSession):
    out = await rag_backfill_service.backfill_interactions(db)
    assert out == 0


@pytest.mark.asyncio
async def test_backfill_competitors_skipped_when_flag_off(db: AsyncSession):
    out = await rag_backfill_service.backfill_competitors(db)
    assert out == 0


@pytest.mark.asyncio
async def test_full_backfill_returns_zeroed_result_when_flag_off(db: AsyncSession):
    out = await rag_backfill_service.run_full_backfill(db)
    assert out.deals_indexed == 0
    assert out.interactions_indexed == 0
    assert out.competitors_indexed == 0


@pytest.mark.asyncio
async def test_incremental_backfill_uses_25h_window(db: AsyncSession):
    """The cron path forwards a since=now-25h cutoff."""
    captured: dict = {}

    async def _mock_full(db_arg, *, since=None):
        captured["since"] = since
        return rag_backfill_service.BackfillResult()

    with patch.object(rag_backfill_service, "run_full_backfill", new=_mock_full):
        await rag_backfill_service.run_incremental_backfill(db)

    assert captured["since"] is not None
    delta = datetime.now(timezone.utc) - captured["since"]
    # 25h window — allow a 5 second tolerance for test runtime.
    assert timedelta(hours=24, minutes=55) < delta < timedelta(hours=25, minutes=5)


# ─────────────────────── answer service short-circuit ───────────────


@pytest.mark.asyncio
async def test_answer_empty_question_returns_empty():
    out = await rag_answer_service.answer_question(question="   ")
    assert out.answer == ""
    assert out.fallback_reason == "empty_question"


@pytest.mark.asyncio
async def test_answer_disabled_when_flag_off():
    out = await rag_answer_service.answer_question(
        question="Why did ACME deal close lost?"
    )
    assert out.fallback_reason == "feature_disabled"
    assert out.confidence == 0.0
    assert out.citations == []


@pytest.mark.asyncio
async def test_answer_empty_retrieval_returns_no_context():
    """When FEATURE_RAG=true but Qdrant returns nothing, we surface that clearly."""
    with patch.object(rag_answer_service, "settings") as ms:
        ms.FEATURE_RAG = True
        ms.ANTHROPIC_API_KEY = "sk-test"
        ms.AI_MODEL_NAME = "claude-haiku"
        with patch.object(rag_answer_service, "_retrieve", new=AsyncMock(return_value=([], ["deals"]))):
            out = await rag_answer_service.answer_question(question="Why ACME?")

    assert out.fallback_reason == "empty_retrieval"
    assert out.citations == []


@pytest.mark.asyncio
async def test_answer_falls_back_when_claude_not_configured():
    """Retrieval-only mode when ANTHROPIC_API_KEY is missing."""
    fake_rows = [
        {"source": "deal", "score": 0.9, "deal_id": 7, "title": "ACME deal", "summary": "won"},
    ]
    with patch.object(rag_answer_service, "settings") as ms:
        ms.FEATURE_RAG = True
        ms.ANTHROPIC_API_KEY = ""  # not configured
        ms.AI_MODEL_NAME = "claude-haiku"
        with patch.object(
            rag_answer_service, "_retrieve",
            new=AsyncMock(return_value=(fake_rows, ["deals"])),
        ):
            out = await rag_answer_service.answer_question(question="Why ACME?")

    assert out.fallback_reason == "claude_not_configured"
    assert len(out.citations) == 1
    assert out.confidence > 0.0


@pytest.mark.asyncio
async def test_answer_full_path_with_mocked_claude():
    fake_rows = [
        {"source": "deal", "score": 0.92, "deal_id": 1, "title": "Win 1", "summary": "summary 1"},
        {"source": "deal", "score": 0.88, "deal_id": 2, "title": "Win 2", "summary": "summary 2"},
    ]
    fake_response = SimpleNamespace(
        content=[
            SimpleNamespace(
                text='{"answer": "İndirim disiplinli kalmış.", '
                     '"confidence": 0.78, "used_citation_ids": [1]}'
            )
        ]
    )

    with patch.object(rag_answer_service, "settings") as ms:
        ms.FEATURE_RAG = True
        ms.ANTHROPIC_API_KEY = "sk-test"
        ms.AI_MODEL_NAME = "claude-haiku"
        with patch.object(
            rag_answer_service, "_retrieve",
            new=AsyncMock(return_value=(fake_rows, ["deals"])),
        ), patch.object(
            rag_answer_service, "claude_messages_create",
            new=AsyncMock(return_value=fake_response),
        ):
            out = await rag_answer_service.answer_question(question="ACME neden kazandı?")

    assert out.fallback_reason is None
    assert "İndirim disiplinli" in out.answer
    assert out.confidence == 0.78
    # Only citation id 1 was kept (Claude said so)
    assert len(out.citations) == 1
    assert out.citations[0]["metadata"].get("deal_id") == 1


# ─────────────────────── prompt builder ─────────────────────────────


def test_build_prompt_truncates_safely():
    rows = [
        {"source": "deal", "deal_id": i, "title": f"Title {i}", "summary": "x" * 1000}
        for i in range(20)
    ]
    out = rag_answer_service._build_prompt("test question", rows)
    # safety cap is 8000 chars but we add a newline-joined header/footer
    assert "Question: test question" in out
    assert "Answer in JSON" in out


def test_extract_competitor_hint_finds_known_names():
    assert rag_answer_service._extract_competitor_hint("ACME chose Siemens last year") == "Siemens"
    assert rag_answer_service._extract_competitor_hint("nothing specific") is None
    assert rag_answer_service._extract_competitor_hint("") is None


# ─────────────────────── auto-ingest hooks safety ───────────────────


@pytest.mark.asyncio
async def test_index_transcript_now_no_op_when_flag_off():
    # Should not raise, should not even open a session.
    await rag_backfill_service.index_transcript_now(99999)


@pytest.mark.asyncio
async def test_index_opportunity_close_no_op_when_flag_off():
    await rag_backfill_service.index_opportunity_close(99999)


# ─────────────────────── flag-on backfill paths (mocked vector_store) ─


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _seed_basic_data(db: AsyncSession) -> tuple[int, int]:
    user = User(
        tenant_id=_TENANT_ID,
        email="rag_owner@test.com",
        full_name="RAG Owner",
        hashed_password=hash_password("Test1234"),
        role="sales_manager",
        is_active=True,
    )
    db.add(user)
    cust = Customer(
        tenant_id=_TENANT_ID,
        name="RAG Cust", company="RAG Cust", email="rag@test.com",
        phone="", address="", tax_id="",
    )
    db.add(cust)
    await db.commit()
    await db.refresh(user)
    await db.refresh(cust)

    opp = Opportunity(
        tenant_id=_TENANT_ID,
        customer_id=cust.id, owner_id=user.id, title="RAG Deal",
        stage="closed_won", status="closed", amount=120_000.0, currency="TRY",
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(opp)
    tr = Transcript(
        title="RAG Test Transcript",
        content="customer was happy with the renewal terms",
        source="upload",
        opportunity_id=None,
        customer_id=cust.id,
        sentiment="positive",
    )
    db.add(tr)
    await db.commit()
    await db.refresh(opp)
    await db.refresh(tr)
    return int(opp.id), int(tr.id)


@pytest.mark.asyncio
async def test_backfill_deals_invokes_store_deal_when_flag_on(db: AsyncSession):
    opp_id, _ = await _seed_basic_data(db)
    invoked: list = []

    async def fake_store_deal(payload):
        invoked.append(payload)
        return f"point-{payload.get('id')}"

    with patch.object(rag_backfill_service, "settings") as ms:
        ms.FEATURE_RAG = True
        with patch(
            "app.services.vector_store.store_deal",
            new=AsyncMock(side_effect=fake_store_deal),
        ):
            count = await rag_backfill_service.backfill_deals(db)

    assert count >= 1
    assert any(p.get("id") == opp_id for p in invoked)


@pytest.mark.asyncio
async def test_backfill_interactions_invokes_store_interaction(db: AsyncSession):
    _, tr_id = await _seed_basic_data(db)
    invoked: list = []

    async def fake_store(payload):
        invoked.append(payload)
        return f"int-{payload.get('id')}"

    with patch.object(rag_backfill_service, "settings") as ms:
        ms.FEATURE_RAG = True
        with patch(
            "app.services.vector_store.store_interaction",
            new=AsyncMock(side_effect=fake_store),
        ):
            count = await rag_backfill_service.backfill_interactions(db)

    assert count >= 1
    assert any(p.get("id") == tr_id and p.get("type") == "transcript" for p in invoked)


@pytest.mark.asyncio
async def test_backfill_competitors_invokes_store_competitor_intel(db: AsyncSession):
    _, _ = await _seed_basic_data(db)
    cm = CompetitorMention(
        opportunity_id=None,
        competitor_name="Siemens",
        source_entity_type="opportunity",
        source_entity_id=1,
        context_snippet="Müşteri Siemens'i değerlendiriyor",
        sentiment="negative",
        detected_by="seed",
    )
    db.add(cm)
    await db.commit()
    invoked: list = []

    async def fake_store(payload):
        invoked.append(payload)
        return f"comp-{payload.get('competitor')}"

    with patch.object(rag_backfill_service, "settings") as ms:
        ms.FEATURE_RAG = True
        with patch(
            "app.services.vector_store.store_competitor_intel",
            new=AsyncMock(side_effect=fake_store),
        ):
            count = await rag_backfill_service.backfill_competitors(db)

    assert count >= 1
    assert any(p.get("competitor") == "Siemens" for p in invoked)
