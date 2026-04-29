"""Bootstrap the V4 → V5 intelligence pipeline on a fresh tenant.

Designed for a production-shaped DB that has core CRM rows
(opportunities/customers/users/quotes) plus the activity history
seeded by ``seed_activity_history.py``, but is otherwise empty
across the derived/aggregate tables. Fills:

Phase 1 — synthesised raw context (seeded, not computed):
  * ``stakeholders``           4 per opp, mixed buyer_role/seniority
  * ``stakeholder_roles``      decision-maker flags for the V6 ctx
  * ``objections``             1-2 per opp, mix of resolved/open
  * ``buyer_state_history``    last 14 daily snapshots per opp
  * ``revenue_signals``        2-3 per opp, mixed severity

Phase 2 — production code paths (computed from raw context above):
  * ``opportunity_features_daily``   build_daily_feature_store()
  * ``account_features_daily``       build_daily_feature_store()
  * ``rep_features_daily``           build_daily_feature_store()
  * ``v4_sales_dna_snapshots``       run_v4_sales_dna_nightly()
  * ``v4_deal_replay_snapshots``     run_v4_deal_replay_nightly()
  * ``deal_replay_deltas``           run_v4_deal_replay_nightly()
  * ``deal_similarity_links``        run_v5_intelligence_nightly()
  * ``dna_patterns``                 run_v5_intelligence_nightly()
  * ``objection_patterns``           run_v5_intelligence_nightly()
  * ``rep_dna_profiles``             run_v5_intelligence_nightly()
  * ``recommended_action_windows``   run_v5_intelligence_nightly()
  * ``playbook_adherence``           run_v5_intelligence_nightly()
  * ``dna_recommendations``          run_v5_intelligence_nightly()

Usage:
    cd backend && source venv/bin/activate
    python -m scripts.bootstrap_intelligence_pipeline --apply
    python -m scripts.bootstrap_intelligence_pipeline --apply --phase 1
    python -m scripts.bootstrap_intelligence_pipeline --apply --phase 2

Without ``--apply`` only prints the plan + per-table existing-row
counts. Idempotent: phase 1 skips opps that already have stakeholders;
phase 2 production code paths upsert by (id, snapshot_date).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
)
logger = logging.getLogger("bootstrap_intelligence")

# Deterministic so re-runs against the same DB produce the same
# fingerprint (helps with debugging "why didn't this opp get a row").
RNG = random.Random(42)


# ─────────────────────── Phase 1: raw context ───────────────────────


# Each opp gets 4 stakeholders mapped to the buying-committee roles
# the tokenizer + decision-gap detector look for. ``decision_maker``
# is the role that drives ``decision_maker_count`` in TokenizerContext.
_STAKEHOLDER_TEMPLATE = [
    {
        "name_pool": ["Mehmet Yılmaz", "Ayşe Demir", "Murat Şahin", "Elif Kaya"],
        "title": "Operasyon Direktörü",
        "seniority": "executive",
        "department_group": "operations",
        "buyer_role": "decision_maker",
    },
    {
        "name_pool": ["Burak Aydın", "Selin Polat", "Tolga Eren", "Deniz Akın"],
        "title": "Satın Alma Müdürü",
        "seniority": "senior",
        "department_group": "finance",
        "buyer_role": "influencer",
    },
    {
        "name_pool": ["Cem Aslan", "Zeynep Çelik", "Hakan Doğan", "Pınar Erdoğan"],
        "title": "Mühendislik Liderii",
        "seniority": "senior",
        "department_group": "tech",
        "buyer_role": "champion",
    },
    {
        "name_pool": ["Esra Tunç", "Onur Bektaş", "Selen Acar", "Berk Güneş"],
        "title": "Satınalma Asistanı",
        "seniority": "mid_level",
        "department_group": "finance",
        "buyer_role": "gatekeeper",
    },
]


# Mix of common B2B objections; mostly resolved so the resolution
# patterns the V5 miner produces have at least 1 success_rate signal.
_OBJECTION_TEMPLATES = [
    ("price_too_high", "med", "Önerilen fiyat bütçenin üzerinde, %5 indirim talep edildi.", True, 36.0),
    ("competitor_quoted_lower", "high", "Rakip A %8 daha düşük teklif verdi, kalite farkı vurgulandı.", True, 72.0),
    ("technical_fit_concern", "med", "Sensör hassasiyeti soruları teknik dokümanla yanıtlandı.", False, None),
    ("contract_terms", "low", "Sözleşmedeki SLA maddesi revize edildi.", True, 48.0),
]


# Buyer states by stage rank. The V4 builder normally classifies these
# from features, but until OFD has rows we seed deterministic snapshots
# so dashboards look populated and the V6 tokenizer's
# buyer_state_changes_norm dimension has variation.
_BUYER_STATES = ("exploring", "evaluating", "negotiating", "stalling", "closing")


_REVENUE_SIGNAL_TEMPLATES = [
    ("positive", "low", "Müşteri pozitif sinyaller veriyor.", "Aktif takip et."),
    ("pricing_concern", "med", "Fiyat itirazı sürdü; iskonto opsiyonu hazırla.", "Revize teklif gönder."),
    ("competitor", "med", "Rakip teklif baskısı tespit edildi.", "Değer önerisi ön plana çıkar."),
    ("expansion_signal", "low", "Müşteri ek lokasyonları gündeme getirdi.", "Cross-sell konuş."),
    ("playbook_triggered", "low", "Otomatik playbook tetiklendi.", "Adımları takip et."),
]


async def _phase1_stakeholders(db, opps) -> int:
    from app.models.sequence_v2 import Stakeholder

    from sqlalchemy import func, select

    written = 0
    for opp in opps:
        existing = (
            await db.execute(
                select(func.count(Stakeholder.id)).where(
                    Stakeholder.opportunity_id == opp.id
                )
            )
        ).scalar_one()
        if existing >= 3:
            continue
        for tmpl in _STAKEHOLDER_TEMPLATE:
            name = RNG.choice(tmpl["name_pool"])
            db.add(
                Stakeholder(
                    opportunity_id=opp.id,
                    customer_id=opp.customer_id,
                    name=name,
                    email=f"{name.lower().replace(' ', '.').replace('ş','s').replace('ı','i').replace('ç','c').replace('ğ','g').replace('ü','u').replace('ö','o')}@example.com",
                    title=tmpl["title"],
                    seniority=tmpl["seniority"],
                    department_group=tmpl["department_group"],
                    buyer_role=tmpl["buyer_role"],
                    is_auto_detected=False,
                    created_by=opp.owner_id,
                )
            )
            written += 1
        await db.flush()
    return written


async def _phase1_objections(db, opps) -> int:
    from app.models.v5_objection import Objection, ObjectionResolutionAction

    from sqlalchemy import func, select

    written = 0
    written_actions = 0
    for opp in opps:
        existing = (
            await db.execute(
                select(func.count(Objection.id)).where(
                    Objection.opportunity_id == opp.id
                )
            )
        ).scalar_one()
        if existing >= 1:
            continue

        # 2 objections per opp: at least one resolved (so V5 miner
        # has success-rate signal) and one open (so the deal-health
        # objection_density_norm dim is non-zero).
        for obj_type, severity, evidence, resolved, ttr in _OBJECTION_TEMPLATES[:2]:
            created_at = datetime.now(timezone.utc) - timedelta(
                days=RNG.randint(20, 50)
            )
            obj = Objection(
                opportunity_id=opp.id,
                event_id=None,
                objection_type=obj_type,
                severity=severity,
                evidence_text=evidence,
                resolved_flag=resolved,
                resolved_at=(created_at + timedelta(hours=ttr)) if resolved and ttr else None,
                ttr_hours=ttr,
                created_at=created_at,
            )
            db.add(obj)
            written += 1
            await db.flush()  # so obj.id is set for the action FK

            # Resolution actions for resolved ones — gives the
            # objection_intelligence miner a payload to learn from.
            if resolved:
                db.add(
                    ObjectionResolutionAction(
                        objection_id=obj.id,
                        action_type="discount_offered" if obj_type.startswith("price") else "value_reframe",
                        action_ts=created_at + timedelta(hours=ttr / 2 if ttr else 1),
                        payload_json=json.dumps({"note": "auto-seeded resolution"}),
                    )
                )
                written_actions += 1
    return written + written_actions


async def _phase1_buyer_state_history(db, opps) -> int:
    from app.models.buyer_state_history import BuyerStateHistory

    from sqlalchemy import select

    written = 0
    today = datetime.now(timezone.utc).date()
    for opp in opps:
        # Skip if any history already exists for this opp.
        existing = (
            await db.execute(
                select(BuyerStateHistory.snapshot_date)
                .where(BuyerStateHistory.opportunity_id == opp.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        # 14 daily snapshots culminating in a current state. State
        # walks forward on the rank ladder so the V6 trajectory dim
        # ``buyer_state_changes_norm`` has at least 2 distinct
        # states per opp.
        for d in range(14, 0, -1):
            snapshot = today - timedelta(days=d)
            # Walk through 3 states over the 14-day window.
            phase_idx = min(2, (14 - d) // 5)
            state = _BUYER_STATES[phase_idx]
            confidence = round(0.55 + 0.05 * phase_idx + RNG.random() * 0.1, 2)
            db.add(
                BuyerStateHistory(
                    opportunity_id=opp.id,
                    snapshot_date=snapshot,
                    state=state,
                    confidence=confidence,
                    drivers_json=json.dumps(
                        {"momentum": phase_idx * 25 + 30, "auto_seeded": True}
                    ),
                )
            )
            written += 1
        await db.flush()
    return written


async def _phase1_revenue_signals(db, opps) -> int:
    from app.models.revenue_signal import RevenueSignal

    from sqlalchemy import func, select

    written = 0
    for opp in opps:
        existing = (
            await db.execute(
                select(func.count(RevenueSignal.id)).where(
                    RevenueSignal.opportunity_id == opp.id
                )
            )
        ).scalar_one()
        if existing >= 1:
            continue
        # 3 signals per opp: ensure at least 1 positive (so cockpit
        # green metric is non-zero) and 1 risk (so risk band has
        # data to render).
        for i, (st, sv, ra, action) in enumerate(_REVENUE_SIGNAL_TEMPLATES[:3]):
            created = datetime.now(timezone.utc) - timedelta(
                days=RNG.randint(2, 25)
            )
            db.add(
                RevenueSignal(
                    signal_type=st,
                    source_entity_type="opportunity",
                    source_entity_id=opp.id,
                    opportunity_id=opp.id,
                    customer_id=opp.customer_id,
                    owner_id=opp.owner_id,
                    severity=sv,
                    confidence=0.7,
                    recommended_action=action,
                    metadata_json=json.dumps({"auto_seeded": True}),
                    depth=0,
                    event_key=f"seed.v2:revsig:opp{opp.id}:{i}:{st}",
                    is_resolved=False,
                    created_at=created,
                )
            )
            written += 1
        await db.flush()
    return written


# ─────────────────────── Phase 2: production code ───────────────────


async def _phase2_feature_store(db, target: date) -> dict:
    from app.services.feature_store_builder import build_daily_feature_store

    res = await build_daily_feature_store(db, snapshot_date=target)
    await db.commit()
    return {
        "snapshot_date": str(res.snapshot_date),
        "opportunities_upserted": res.opportunities_upserted,
        "accounts_upserted": res.accounts_upserted,
        "reps_upserted": res.reps_upserted,
    }


async def _phase2_v4_sales_dna(db, target: date) -> dict:
    from app.services.v4_learning_nightly import run_v4_sales_dna_nightly

    return await run_v4_sales_dna_nightly(db, target_date=target)


async def _phase2_v4_deal_replay(db, target: date) -> dict:
    from app.services.v4_learning_nightly import run_v4_deal_replay_nightly

    return await run_v4_deal_replay_nightly(db, target_date=target)


async def _phase2_v5_intelligence(db, target: date) -> dict:
    from app.services.v4_learning_nightly import run_v5_intelligence_nightly

    return await run_v5_intelligence_nightly(db, target_date=target)


# ─────────────────────── orchestrator ───────────────────────────────


async def main_async(*, phase: int | None, apply: bool) -> None:
    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.opportunity import Opportunity

    async with async_session() as db:
        opps = (
            await db.execute(select(Opportunity).where(Opportunity.status == "active"))
        ).scalars().all()
        logger.info("Found %d active opportunities", len(opps))
        if not opps:
            logger.warning("No active opportunities — nothing to do.")
            return

        if not apply:
            logger.info(
                "DRY-RUN — would seed phase 1 raw context + run phase 2 production "
                "code paths against %d opps. Pass --apply to execute.",
                len(opps),
            )
            return

        target_date = datetime.now(timezone.utc).date()

        # ── Phase 1 ──
        if phase is None or phase == 1:
            logger.info("--- PHASE 1: synthesised raw context ---")
            n = await _phase1_stakeholders(db, opps)
            await db.commit()
            logger.info("  stakeholders: +%d rows", n)

            n = await _phase1_objections(db, opps)
            await db.commit()
            logger.info("  objections + resolution_actions: +%d rows", n)

            n = await _phase1_buyer_state_history(db, opps)
            await db.commit()
            logger.info("  buyer_state_history: +%d rows", n)

            n = await _phase1_revenue_signals(db, opps)
            await db.commit()
            logger.info("  revenue_signals: +%d rows", n)

        # ── Phase 2 ──
        if phase is None or phase == 2:
            logger.info("--- PHASE 2: production code paths ---")

            try:
                res = await _phase2_feature_store(db, target_date)
                logger.info("  build_daily_feature_store: %s", res)
            except Exception as exc:
                logger.exception("  build_daily_feature_store FAILED: %s", exc)
                await db.rollback()

            try:
                res = await _phase2_v4_sales_dna(db, target_date)
                logger.info("  run_v4_sales_dna_nightly: %s", res)
            except Exception as exc:
                logger.exception("  run_v4_sales_dna_nightly FAILED: %s", exc)
                await db.rollback()

            try:
                res = await _phase2_v4_deal_replay(db, target_date)
                logger.info("  run_v4_deal_replay_nightly: %s", res)
            except Exception as exc:
                logger.exception("  run_v4_deal_replay_nightly FAILED: %s", exc)
                await db.rollback()

            try:
                res = await _phase2_v5_intelligence(db, target_date)
                logger.info("  run_v5_intelligence_nightly: %s", res)
            except Exception as exc:
                logger.exception("  run_v5_intelligence_nightly FAILED: %s", exc)
                await db.rollback()

        logger.info("Bootstrap pipeline complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap V4 → V5 intelligence pipeline data on a fresh tenant.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually execute (default: dry-run prints the plan only).",
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=(1, 2),
        default=None,
        help="Restrict to phase 1 (raw context) or phase 2 (production code). "
        "Default: run both in order.",
    )
    args = parser.parse_args()
    asyncio.run(main_async(phase=args.phase, apply=args.apply))


if __name__ == "__main__":
    main()
