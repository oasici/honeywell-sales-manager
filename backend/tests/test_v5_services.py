"""V5 Intelligence Platform — service-level tests.

Covers the unit-level behavior of each new V5 service:

* segment_key derivation
* objection_intelligence_service: keyword detection + idempotent record
* timing_engine_service: urgency math + window materialization
* benchmark_gap_service: signed pct diff + envelope shape
* deal_similarity_service: cosine + embedding builder
* dna_pattern_miner: signature reduction + lift filter
* rep_dna_service: classifier thresholds
* v5_foundation_builder: account/rep augmentation columns

Pure-function tests run without DB; service tests use the in-memory
SQLite fixture from conftest.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.customer import Customer
from app.models.feature_store_daily import (
    AccountFeaturesDaily,
    OpportunityFeaturesDaily,
    RepFeaturesDaily,
)
from app.models.opportunity import Opportunity
from app.models.sales_event_shadow import SalesEventShadow
from app.models.user import User
from app.models.v5_objection import Objection
from app.services import (
    benchmark_gap_service,
    deal_similarity_service,
    dna_pattern_miner,
    objection_intelligence_service,
    rep_dna_service,
    timing_engine_service,
    v5_foundation_builder,
)
from app.services.segment_key import derive_segment_key


# ─────────────────────── pure helpers ────────────────────────────────


def test_derive_segment_key_handles_none_inputs():
    key = derive_segment_key(industry=None, employee_count=None, amount_try=None)
    assert key == "unknown_unknown_unknown_general"


def test_derive_segment_key_buckets_size_and_amount():
    key = derive_segment_key(
        industry="Manufacturing",
        employee_count=120,
        amount_try=300_000,
        product_family="HVAC",
    )
    assert key == "manufacturing_mid_200k_1m_hvac"


def test_objection_detect_in_text_matches_turkish_and_english():
    detections = objection_intelligence_service.detect_in_text(
        "Bu fiyat çok pahalı. We need a discount."
    )
    types = {d.objection_type for d in detections}
    assert "price" in types
    # Both keywords resolve to 'price' but only the first match is kept
    assert len(detections) == 1


def test_objection_detect_in_text_returns_empty_for_no_signal():
    assert objection_intelligence_service.detect_in_text("") == []
    assert objection_intelligence_service.detect_in_text("merhaba dünya") == []


def test_signed_pct_diff_handles_zero_and_directionality():
    fn = benchmark_gap_service._signed_pct_diff
    assert fn(10, 0, True) == 0.0  # zero benchmark guard
    # higher_is_better=True: actual > benchmark → positive diff
    assert fn(12, 10, True) == pytest.approx(0.2)
    # higher_is_better=False: actual > benchmark → negative diff (worse)
    assert fn(12, 10, False) == pytest.approx(-0.2)


def test_cosine_similarity_orthogonal_and_identical():
    assert deal_similarity_service.cosine_similarity([1, 0, 0], [0, 1, 0]) == 0.0
    assert deal_similarity_service.cosine_similarity([1, 0, 0], [1, 0, 0]) == 1.0


def test_cosine_similarity_handles_zero_vectors():
    assert deal_similarity_service.cosine_similarity([0, 0], [1, 1]) == 0.0
    assert deal_similarity_service.cosine_similarity([], []) == 0.0


def test_dna_pattern_miner_signature_drops_noise():
    class _E:
        def __init__(self, t): self.event_type = t

    sig = dna_pattern_miner._signature(
        [_E("page_view"), _E("meeting_logged"), _E("ping"), _E("quote_sent")]
    )
    assert sig == ("meeting_logged", "quote_sent")


# ─────────────────────── DB-backed tests ─────────────────────────────


_TENANT_ID = 1  # Round-15 Sprint 15k/l — canonical single-tenant id.


async def _seed_basics(
    db: AsyncSession,
) -> tuple[User, Customer, Opportunity]:
    user = User(
        tenant_id=_TENANT_ID,
        email="rep_v5@test.com",
        full_name="Rep V5",
        hashed_password=hash_password("Test1234"),
        role="sales_rep",
        is_active=True,
    )
    db.add(user)
    cust = Customer(
        tenant_id=_TENANT_ID,
        name="Acme",
        company="Acme",
        email="acme@test.com",
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
        tenant_id=_TENANT_ID,
        customer_id=cust.id,
        owner_id=user.id,
        title="Deal V5",
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
    return user, cust, opp


@pytest.mark.asyncio
async def test_record_objection_is_idempotent_per_unresolved(db: AsyncSession):
    _, _, opp = await _seed_basics(db)
    detection = objection_intelligence_service.DetectedObjection(
        objection_type="price", severity="med", evidence_text="çok pahalı"
    )
    first = await objection_intelligence_service.record_objection(
        db, opportunity_id=opp.id, detection=detection
    )
    second = await objection_intelligence_service.record_objection(
        db, opportunity_id=opp.id, detection=detection
    )
    assert first.id == second.id


@pytest.mark.asyncio
async def test_record_resolution_action_marks_resolved_and_sets_ttr(db: AsyncSession):
    _, _, opp = await _seed_basics(db)
    detection = objection_intelligence_service.DetectedObjection(
        objection_type="security", severity="high", evidence_text="kvkk"
    )
    obj = await objection_intelligence_service.record_objection(
        db, opportunity_id=opp.id, detection=detection
    )
    await objection_intelligence_service.record_resolution_action(
        db,
        objection_id=obj.id,
        action_type="security_doc_sent",
        mark_resolved=True,
    )
    refreshed = await db.get(Objection, obj.id)
    assert refreshed.resolved_flag is True
    assert refreshed.resolved_at is not None
    assert refreshed.ttr_hours is not None and refreshed.ttr_hours >= 0


@pytest.mark.asyncio
async def test_timing_engine_skips_when_no_trigger(db: AsyncSession):
    _, _, opp = await _seed_basics(db)
    written = await timing_engine_service.materialize_windows_for_opportunity(
        db, opportunity_id=opp.id
    )
    assert written == 0


@pytest.mark.asyncio
async def test_timing_engine_emits_window_when_trigger_overdue(db: AsyncSession):
    _, _, opp = await _seed_basics(db)
    overdue = datetime.now(timezone.utc) - timedelta(hours=72)
    db.add(
        SalesEventShadow(
            source_ref=f"shadow:test:{opp.id}",
            provenance="test",
            opportunity_id=opp.id,
            event_type="quote_sent",
            event_ts=overdue,
            actor_type="rep",
            channel="crm",
            direction="outbound",
            payload_json="{}",
        )
    )
    db.add(
        OpportunityFeaturesDaily(
            opportunity_id=opp.id,
            snapshot_date=date.today(),
            momentum_score=40,
            days_since_last_buyer_touch=5,
        )
    )
    await db.commit()

    written = await timing_engine_service.materialize_windows_for_opportunity(
        db, opportunity_id=opp.id
    )
    assert written == 1
    rows = await timing_engine_service.list_active_windows(db, opportunity_id=opp.id)
    assert rows and rows[0].action_type == "followup_after_quote"
    assert 0.0 <= rows[0].urgency_score <= 1.0


@pytest.mark.asyncio
async def test_benchmark_gap_envelope_shape(db: AsyncSession):
    _, _, opp = await _seed_basics(db)
    envelope = await benchmark_gap_service.score_opportunity(db, opp.id)
    assert set(envelope.keys()) == {
        "value",
        "confidence",
        "drivers",
        "benchmark_context",
        "recommended_actions",
    }
    # No features/benchmark yet → graceful empty
    assert envelope["value"] is None
    assert envelope["confidence"] == 0.0


@pytest.mark.asyncio
async def test_deal_similarity_embedding_dim(db: AsyncSession):
    _, _, opp = await _seed_basics(db)
    db.add(
        OpportunityFeaturesDaily(
            opportunity_id=opp.id,
            snapshot_date=date.today(),
            momentum_score=70,
            days_since_last_rep_touch=2,
            buyer_reply_count_14d=3,
        )
    )
    await db.commit()
    vec = await deal_similarity_service.build_embedding(db, opportunity_id=opp.id)
    assert vec is not None
    assert len(vec) == deal_similarity_service.EMBEDDING_DIM
    assert all(0.0 <= v <= 1.0 for v in vec)


@pytest.mark.asyncio
async def test_v5_foundation_augmentation_writes_v5_columns(db: AsyncSession):
    user, cust, opp = await _seed_basics(db)
    snap = date.today()
    db.add(
        OpportunityFeaturesDaily(
            opportunity_id=opp.id,
            snapshot_date=snap,
            momentum_score=80,
            buyer_reply_count_14d=4,
            meeting_count_30d=2,
            positive_signal_count_14d=3,
        )
    )
    db.add(
        AccountFeaturesDaily(
            account_id=cust.id,
            snapshot_date=snap,
            open_opportunity_count=1,
            total_open_pipeline=300_000,
            last_touch_days=2,
        )
    )
    db.add(
        RepFeaturesDaily(
            rep_id=user.id,
            snapshot_date=snap,
        )
    )
    await db.commit()

    result = await v5_foundation_builder.run_v5_foundation_augmentation(
        db, snapshot_date=snap
    )
    assert result.accounts_updated >= 1
    assert result.reps_updated >= 1

    refreshed = await db.get(AccountFeaturesDaily, (cust.id, snap))
    assert refreshed.avg_momentum == pytest.approx(80.0)
    assert refreshed.expansion_signal_score == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_rep_dna_classify_balanced_when_no_signal():
    rep = type(
        "R",
        (),
        {
            "avg_followup_hours": None,
            "discount_dependence": None,
            "objection_recovery_rate": None,
            "stakeholder_coverage_rate": None,
        },
    )()
    team = rep_dna_service._TeamStats(None, None, None, None)
    cluster, strengths, gaps = rep_dna_service.classify_rep(rep=rep, team=team)
    assert cluster == rep_dna_service.CLUSTER_BALANCED
    assert strengths == [] and gaps == []


@pytest.mark.asyncio
async def test_rep_dna_classify_picks_fast_followup_when_below_team():
    rep = type(
        "R",
        (),
        {
            "avg_followup_hours": 4.0,
            "discount_dependence": 0.05,
            "objection_recovery_rate": 0.5,
            "stakeholder_coverage_rate": 0.5,
        },
    )()
    team = rep_dna_service._TeamStats(
        avg_followup_hours=8.0,
        discount_dependence=0.15,
        objection_recovery_rate=0.5,
        stakeholder_coverage_rate=0.5,
    )
    cluster, strengths, _ = rep_dna_service.classify_rep(rep=rep, team=team)
    assert cluster == rep_dna_service.CLUSTER_FAST_FOLLOWUP
    assert "fast_followup" in strengths
