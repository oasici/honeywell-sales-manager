"""V6 Intelligence Depth — service-level tests.

Covers:
- sequence_tokenizer: 8 token rules
- _buyer_state_and_drivers: 7-state classifier promotion paths
- event_recompute_hooks: flag-gated short-circuit
- replay_delta_service: counterfactual hints + idempotent recompute
- dna_playbook_promoter: token→step mapping + idempotency
- deal_similarity_service: 12-dim vector + trajectory dims bounded
- federated_benchmark_service: k-anonymity suppression
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.customer import Customer
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services import (
    deal_similarity_service,
    dna_playbook_promoter,
    federated_benchmark_service,
    replay_delta_service,
    sequence_tokenizer,
)
from app.services.feature_store_builder import _buyer_state_and_drivers


# ─────────────────────── tokenizer tests ─────────────────────────────


@dataclass
class _FakeEvent:
    event_type: str
    event_ts: datetime
    payload_json: dict | None = None


def _ev(event_type: str, hours_offset: int, payload: dict | None = None) -> _FakeEvent:
    return _FakeEvent(
        event_type=event_type,
        event_ts=datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc) + timedelta(hours=hours_offset),
        payload_json=payload,
    )


def test_tokenize_emits_buyer_reply_within_48h():
    events = [_ev("email_sent", 0), _ev("email_received", 24)]
    tokens = sequence_tokenizer.tokenize(events)
    assert sequence_tokenizer.TOK_BUYER_REPLY_FAST in tokens


def test_tokenize_does_not_emit_buyer_reply_when_late():
    events = [_ev("email_sent", 0), _ev("email_received", 72)]
    tokens = sequence_tokenizer.tokenize(events)
    assert sequence_tokenizer.TOK_BUYER_REPLY_FAST not in tokens


def test_tokenize_emits_meeting_before_quote():
    events = [_ev("meeting_logged", 0), _ev("quote_sent", 24)]
    tokens = sequence_tokenizer.tokenize(events)
    assert sequence_tokenizer.TOK_MEETING_BEFORE_QUOTE in tokens


def test_tokenize_emits_followup_within_24h_after_quote():
    events = [_ev("quote_sent", 0), _ev("call_logged", 6)]
    tokens = sequence_tokenizer.tokenize(events)
    assert sequence_tokenizer.TOK_FOLLOWUP_AFTER_QUOTE in tokens


def test_tokenize_emits_3plus_stakeholders_via_context():
    ctx = sequence_tokenizer.TokenizerContext(stakeholder_count=4)
    tokens = sequence_tokenizer.tokenize([], ctx)
    assert sequence_tokenizer.TOK_3PLUS_STAKEHOLDERS in tokens


def test_tokenize_emits_discount_under_15():
    ctx = sequence_tokenizer.TokenizerContext(latest_discount_pct=10.0)
    tokens = sequence_tokenizer.tokenize([], ctx)
    assert sequence_tokenizer.TOK_DISCOUNT_LOW in tokens


def test_tokenize_does_not_emit_discount_low_when_high():
    ctx = sequence_tokenizer.TokenizerContext(latest_discount_pct=20.0)
    tokens = sequence_tokenizer.tokenize([], ctx)
    assert sequence_tokenizer.TOK_DISCOUNT_LOW not in tokens


def test_tokenize_emits_quote_revised_after_objection():
    events = [_ev("objection_logged", 0), _ev("quote_sent", 96)]
    tokens = sequence_tokenizer.tokenize(events)
    assert sequence_tokenizer.TOK_QUOTE_REVISED_AFTER_OBJECTION in tokens


def test_tokenize_returns_stable_sorted_order():
    ctx = sequence_tokenizer.TokenizerContext(
        stakeholder_count=4, latest_discount_pct=5.0
    )
    events = [_ev("email_sent", 0), _ev("email_received", 12)]
    tokens = sequence_tokenizer.tokenize(events, ctx)
    assert tokens == sorted(tokens)


# ─────────────────────── 7-state buyer classifier ────────────────────


def test_buyer_state_ready_to_buy_when_contract_sent_and_replies():
    state, conf, _ = _buyer_state_and_drivers(
        stage="negotiation",
        days_since_buyer=1,
        buyer_reply_14d=4,
        meetings_30d=3,
        quote_count=2,
        negative_signals_14d=0,
        contract_sent=True,
    )
    assert state == "ready_to_buy"
    assert conf >= 0.8


def test_buyer_state_procurement_when_procurement_signal():
    state, _conf, _ = _buyer_state_and_drivers(
        stage="negotiation",
        days_since_buyer=2,
        buyer_reply_14d=2,
        meetings_30d=1,
        quote_count=1,
        negative_signals_14d=2,
        procurement_signals_30d=2,
    )
    assert state == "procurement"


def test_buyer_state_aligning_on_stakeholder_growth():
    state, _conf, _ = _buyer_state_and_drivers(
        stage="qualified",
        days_since_buyer=2,
        buyer_reply_14d=2,
        meetings_30d=2,
        quote_count=0,
        negative_signals_14d=0,
        stakeholder_growth_14d=2,
    )
    assert state == "aligning"


def test_buyer_state_falls_back_to_v5_when_no_v6_signals():
    state, _conf, _ = _buyer_state_and_drivers(
        stage="qualified",
        days_since_buyer=2,
        buyer_reply_14d=1,
        meetings_30d=1,
        quote_count=0,
        negative_signals_14d=0,
    )
    assert state == "evaluating"


def test_buyer_state_closed_short_circuits():
    state, conf, _ = _buyer_state_and_drivers(
        stage="closed_won",
        days_since_buyer=0,
        buyer_reply_14d=0,
        meetings_30d=0,
        quote_count=0,
        negative_signals_14d=0,
        contract_sent=True,
    )
    assert state == "closed"
    assert conf == 0.9


# ─────────────────────── event_recompute_hooks ───────────────────────


@pytest.mark.asyncio
async def test_recompute_after_activity_short_circuits_when_flag_off(db: AsyncSession):
    from app.services.event_recompute_hooks import recompute_after_activity

    # Default test config has FEATURE_V6_REALTIME = False → empty dict.
    result = await recompute_after_activity(db, opportunity_id=1)
    assert result == {}


# ─────────────────────── DB-backed helpers ───────────────────────────


async def _seed_opp(db: AsyncSession) -> Opportunity:
    user = User(
        email="rep_v6@test.com",
        full_name="Rep V6",
        hashed_password=hash_password("Test1234"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    cust = Customer(
        name="V6 Acme",
        company="V6 Acme",
        email="v6@test.com",
        phone="",
        address="",
        tax_id="",
        industry="manufacturing",
        employee_count=120,
    )
    db.add(cust)
    await db.commit()
    await db.refresh(user)
    await db.refresh(cust)

    opp = Opportunity(
        customer_id=cust.id,
        owner_id=user.id,
        title="V6 Deal",
        stage="qualified",
        status="active",
        amount=300_000,
        currency="TRY",
        created_at=datetime.now(timezone.utc) - timedelta(days=20),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(opp)
    await db.commit()
    await db.refresh(opp)
    return opp


# ─────────────────────── replay_delta_service ────────────────────────


@pytest.mark.asyncio
async def test_replay_delta_emits_post_quote_gap_hint(db: AsyncSession):
    opp = await _seed_opp(db)
    today = date.today()

    # Two OFD snapshots: yesterday momentum=70, today momentum=50 with
    # days_since_last_rep_touch=4 → triggers post_quote_followup_gap.
    db.add(
        OpportunityFeaturesDaily(
            opportunity_id=opp.id,
            snapshot_date=today - timedelta(days=1),
            momentum_score=70,
            days_since_last_rep_touch=1,
        )
    )
    db.add(
        OpportunityFeaturesDaily(
            opportunity_id=opp.id,
            snapshot_date=today,
            momentum_score=50,
            days_since_last_rep_touch=4,
        )
    )
    await db.commit()

    # Add a quote_sent event between the two snapshots.
    from app.models.sales_event_shadow import SalesEventShadow

    db.add(
        SalesEventShadow(
            source_ref=f"shadow:test:v6:{opp.id}",
            provenance="test",
            opportunity_id=opp.id,
            event_type="quote_sent",
            event_ts=datetime.now(timezone.utc) - timedelta(hours=18),
            actor_type="rep",
            channel="crm",
            direction="outbound",
            payload_json="{}",
        )
    )
    await db.commit()

    written = await replay_delta_service.compute_deltas(db, opportunity_id=opp.id)
    assert written >= 1
    rows = await replay_delta_service.list_deltas(db, opportunity_id=opp.id)
    assert any(
        r.counterfactual_hint == replay_delta_service.HINT_POST_QUOTE_GAP for r in rows
    )


@pytest.mark.asyncio
async def test_replay_delta_idempotent(db: AsyncSession):
    opp = await _seed_opp(db)
    today = date.today()
    db.add(
        OpportunityFeaturesDaily(
            opportunity_id=opp.id,
            snapshot_date=today - timedelta(days=2),
            momentum_score=75,
            days_since_last_rep_touch=1,
        )
    )
    db.add(
        OpportunityFeaturesDaily(
            opportunity_id=opp.id,
            snapshot_date=today - timedelta(days=1),
            momentum_score=60,
            days_since_last_rep_touch=2,
        )
    )
    db.add(
        OpportunityFeaturesDaily(
            opportunity_id=opp.id,
            snapshot_date=today,
            momentum_score=45,
            days_since_last_rep_touch=4,
        )
    )
    await db.commit()

    first = await replay_delta_service.compute_deltas(db, opportunity_id=opp.id)
    second = await replay_delta_service.compute_deltas(db, opportunity_id=opp.id)
    assert first == second
    rows = await replay_delta_service.list_deltas(db, opportunity_id=opp.id)
    assert len(rows) == first


# ─────────────────────── deal_similarity 12-dim ──────────────────────


@pytest.mark.asyncio
async def test_similarity_embedding_is_12_dim(db: AsyncSession):
    opp = await _seed_opp(db)
    db.add(
        OpportunityFeaturesDaily(
            opportunity_id=opp.id,
            snapshot_date=date.today(),
            momentum_score=80,
            stage_velocity_days=5.0,
        )
    )
    await db.commit()

    vec = await deal_similarity_service.build_embedding(db, opportunity_id=opp.id)
    assert vec is not None
    assert len(vec) == 12
    assert deal_similarity_service.EMBEDDING_DIM == 12
    assert deal_similarity_service.EMBEDDING_VERSION == "v6-trajectory-1"
    # Trajectory dims (last 4) must be in [0, 1].
    assert all(0.0 <= v <= 1.0 for v in vec[-4:])


# ─────────────────────── DNA → Playbook promoter ─────────────────────


@pytest.mark.asyncio
async def test_dna_promote_skips_when_no_qualifying_pattern(db: AsyncSession):
    written = await dna_playbook_promoter.promote_top_patterns(db)
    assert written == 0


@pytest.mark.asyncio
async def test_dna_promote_creates_playbook_with_steps(db: AsyncSession):
    import json

    from app.models.v5_dna_patterns import DnaPattern

    db.add(
        DnaPattern(
            # Round-10 R10-DB-3 — the playbook promoter mirrors the
            # pattern's tenant_id onto the auto-created Playbook
            # (which is NOT NULL). Patterns with tenant_id=None are
            # treated as global / training artifacts and skipped.
            tenant_id=1,
            segment_key="manufacturing_mid_200k_1m_general",
            pattern_name="meeting_first_then_quote",
            pattern_type="event_sequence",
            sequence_template_json=json.dumps(
                [
                    sequence_tokenizer.TOK_MEETING_BEFORE_QUOTE,
                    sequence_tokenizer.TOK_FOLLOWUP_AFTER_QUOTE,
                ]
            ),
            support_count=15,
            win_rate=0.6,
            baseline_win_rate=0.3,
            lift_vs_baseline=2.0,
            confidence_score=0.75,
            # V7 gating: pretend the Bayesian miner already cleared
            # this pattern. Without is_promotable=True the V7
            # promoter filters it out.
            is_promotable=True,
            uplift_score=0.3,
        )
    )
    await db.commit()

    written = await dna_playbook_promoter.promote_top_patterns(db)
    assert written == 1

    # Re-running should be idempotent (same playbook updated, count == 1).
    second = await dna_playbook_promoter.promote_top_patterns(db)
    assert second == 1


# ─────────────────────── federated benchmark suppression ─────────────


@pytest.mark.asyncio
async def test_federated_benchmark_suppresses_below_min_sample(db: AsyncSession):
    row = await federated_benchmark_service.publish_benchmark(
        db,
        benchmark_key="industrial_midmarket",
        metric_name="win_rate_90d",
        metric_value=0.42,
        sample_size=5,  # below MIN_SAMPLE_SIZE
        tenant_count=5,
    )
    assert row.suppressed is True
    assert row.metric_value is None


@pytest.mark.asyncio
async def test_federated_benchmark_suppresses_below_min_tenants(db: AsyncSession):
    row = await federated_benchmark_service.publish_benchmark(
        db,
        benchmark_key="industrial_midmarket",
        metric_name="win_rate_90d",
        metric_value=0.42,
        sample_size=50,
        tenant_count=2,  # below MIN_TENANT_COUNT
    )
    assert row.suppressed is True


@pytest.mark.asyncio
async def test_federated_benchmark_publishes_above_threshold(db: AsyncSession):
    row = await federated_benchmark_service.publish_benchmark(
        db,
        benchmark_key="industrial_midmarket",
        metric_name="win_rate_90d",
        metric_value=0.42,
        sample_size=50,
        tenant_count=5,
    )
    assert row.suppressed is False
    assert row.metric_value == pytest.approx(0.42)
