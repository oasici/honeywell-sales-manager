"""Seed activity history for existing opportunities.

Designed for **production-shaped** databases that already have
opportunities + customers + users but no interaction trail
(``activity_logs`` / ``opportunity_events`` / ``opportunity_signals``
all empty). Without that trail, the V4 → V5 → V8 → V12 pipeline
can't compute anything: tokenizer returns empty lists, similarity
embeddings stay zeroed, deal-health scores fall back to defaults.

What this script does
---------------------
For each ``Opportunity`` that has < ``MIN_ACTIVITIES`` ActivityLog rows,
synthesise a plausible 90-day interaction history:

- 4–8 ``ActivityLog`` rows per opp, types weighted toward
  ``call`` / ``email_sent`` / ``meeting`` with sprinkled
  ``stage_change`` / ``note_added`` / ``task_completed``.
- 1–3 ``OpportunityEvent`` rows mirroring the activities so the
  V4 sales-events shadow has joinable data.
- 0–2 ``OpportunitySignal`` rows (severity weighted, mostly low/med).
- ``source_ref`` populated for idempotency: re-running won't
  duplicate rows because the shadow-sync de-dupes on it.

What this script does NOT do
----------------------------
- Touch any opportunity's stage, amount, status, owner, or close_date.
- Touch users, customers, leads, quotes, or spare_parts.
- Run derived-data jobs (V4 nightly / V5 / V8). After this seeds
  raw data, the operator triggers ``backfill-text-embeddings.yml``
  and ``backfill-transformer-seq.yml`` to compute the rest.

Idempotency
-----------
Re-running is safe — opps that already have ≥ ``MIN_ACTIVITIES``
log rows are skipped. To force-reseed a specific opp, delete its
``activity_logs`` rows first.

Usage
-----
    cd backend && source venv/bin/activate
    python -m scripts.seed_activity_history --apply

Options
-------
    --apply              Run the inserts (without it: dry-run summary).
    --opp <ID>           Limit to one opportunity id (repeatable).
    --min-activities N   Skip opps that already have ≥ N activities (default 3).
    --window-days N      Activity timestamps spread over the last N days
                         (default 90 — matches V6 tokenizer's 180-day window
                         with comfortable headroom).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
)
logger = logging.getLogger("seed_activity_history")


# Deterministic RNG so re-runs against the same DB produce the same
# fingerprint (helps with debugging "why didn't this opp get a row").
RNG = random.Random(42)


# Activity types weighted by realistic prevalence.
ACTIVITY_TYPES = [
    ("call", 25),
    ("email_sent", 30),
    ("email_received", 20),
    ("meeting", 12),
    ("stage_change", 5),
    ("note_added", 5),
    ("task_completed", 3),
]
_ACTIVITY_POOL = [t for t, w in ACTIVITY_TYPES for _ in range(w)]


# Map activity → opportunity_event type.
_EVENT_TYPE_MAP = {
    "call": "call",
    "email_sent": "email",
    "email_received": "email",
    "meeting": "meeting",
    "stage_change": "stage_change",
    "note_added": "note",
    "task_completed": "task",
}


# Realistic Turkish summary templates, chosen to give the V6
# tokenizer + V8 BoW something with vocabulary variety.
_SUMMARY_TEMPLATES = {
    "call": [
        "Müşteri ile fiyat görüşmesi yapıldı, ek bilgi talep edildi.",
        "Teknik şartname üzerinde mutabık kalındı.",
        "Sipariş süreci sorgulandı; satın alma onayı bekleniyor.",
        "Rakip teklif karşılaştırması istendi.",
    ],
    "email_sent": [
        "Revize teklif gönderildi.",
        "Teknik dokümantasyon ve referanslar paylaşıldı.",
        "Sözleşme taslağı incelenmek üzere iletildi.",
        "Toplantı sonrası özet ve aksiyonlar gönderildi.",
    ],
    "email_received": [
        "Müşteriden ek soru listesi geldi.",
        "İskonto talebi e-postayla iletildi.",
        "Teknik onay onaylandığı yönünde geri dönüş.",
        "Karşı tarafın sözleşme revizyonları alındı.",
    ],
    "meeting": [
        "Karar mercileri ile demo toplantısı yapıldı.",
        "Yerinde keşif ve gereksinim çalışması.",
        "Pilot uygulama plan toplantısı.",
        "Yönetim seviyesi onay görüşmesi.",
    ],
    "stage_change": [
        "Aşama ilerletildi: müzakere",
        "Aşama: teklif onayı",
        "Pipeline aşaması güncellendi",
    ],
    "note_added": [
        "Karar verici tatildeydi, geri döndüğünde aranacak.",
        "Bütçe Q4'e kaydı; takip planına alındı.",
        "Rakip A devreye girdi; konum savunulacak.",
    ],
    "task_completed": [
        "Teknik onay belgesi tamamlandı.",
        "Demo ortamı hazır.",
        "Numune teslim edildi.",
    ],
}


def _pick_summary(activity_type: str) -> str:
    pool = _SUMMARY_TEMPLATES.get(activity_type) or ["Etkileşim kaydı."]
    return RNG.choice(pool)


def _pick_signal_type() -> tuple[str, str]:
    """Returns (signal_type, severity)."""
    # Distribution favours informational signals over high-severity
    # ones — matches what the AI risk pass actually produces.
    candidates = [
        ("positive", "low", 30),
        ("no_touch", "med", 20),
        ("pricing_concern", "med", 15),
        ("competitor", "med", 12),
        ("objection", "high", 8),
        ("discount_risk", "med", 8),
        ("sla_breach", "high", 4),
        ("pricing_concern", "high", 3),
    ]
    total = sum(w for _, _, w in candidates)
    pick = RNG.uniform(0, total)
    acc = 0.0
    for st, sv, w in candidates:
        acc += w
        if pick <= acc:
            return st, sv
    return "positive", "low"


def _spread_timestamps(
    n: int, window_days: int, now: datetime
) -> list[datetime]:
    """Generate ``n`` timestamps within the last ``window_days``,
    weighted toward the *recent* end so the tokenizer's 180-day
    window catches most of them."""
    out: list[datetime] = []
    for _ in range(n):
        # Bias toward recent: square-root distribution.
        days_back = (RNG.random() ** 0.5) * window_days
        out.append(now - timedelta(days=days_back, hours=RNG.randint(0, 23)))
    out.sort()
    return out


async def main_async(
    *,
    opportunity_ids: list[int] | None,
    min_activities: int,
    window_days: int,
    apply: bool,
) -> None:
    from sqlalchemy import func, select

    from app.core.database import async_session
    from app.models.activity_log import ActivityLog
    from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal

    async with async_session() as db:
        if opportunity_ids:
            opps = (
                await db.execute(
                    select(Opportunity).where(
                        Opportunity.id.in_(opportunity_ids)
                    )
                )
            ).scalars().all()
        else:
            opps = (await db.execute(select(Opportunity))).scalars().all()

        logger.info("Found %d opportunities to consider", len(opps))

        plan: list[tuple[Opportunity, int]] = []
        for opp in opps:
            existing = (
                await db.execute(
                    select(func.count(ActivityLog.id)).where(
                        ActivityLog.opportunity_id == opp.id
                    )
                )
            ).scalar_one()
            if existing >= min_activities:
                logger.info(
                    "  opp=%d (%r) skipped: already has %d activities",
                    opp.id, opp.title, existing,
                )
                continue
            count = RNG.randint(4, 8)
            plan.append((opp, count))

        logger.info(
            "Plan: %d opps will be seeded (min_activities=%d, window=%dd)",
            len(plan), min_activities, window_days,
        )

        if not apply:
            for opp, count in plan:
                logger.info("  + opp=%d (%r): %d activities", opp.id, opp.title, count)
            logger.info("DRY-RUN — pass --apply to insert.")
            return

        now = datetime.now(timezone.utc)
        total_act = total_evt = total_sig = 0

        for opp, count in plan:
            timestamps = _spread_timestamps(count, window_days, now)
            for i, ts in enumerate(timestamps):
                act_type = RNG.choice(_ACTIVITY_POOL)
                summary = _pick_summary(act_type)
                # Stable source_ref so the V4 shadow-sync de-dupes
                # on idempotent re-runs.
                source_ref = f"seed:opp{opp.id}:act{i}:{act_type}"
                db.add(
                    ActivityLog(
                        activity_type=act_type,
                        entity_type="opportunity",
                        entity_id=opp.id,
                        opportunity_id=opp.id,
                        customer_id=opp.customer_id,
                        user_id=opp.owner_id,
                        summary=summary,
                        outcome=None,
                        source_ref=source_ref,
                        created_at=ts,
                    )
                )
                total_act += 1

                # Mirror ~half of the activities into opportunity_events
                # so the legacy timeline view also lights up.
                if RNG.random() < 0.5:
                    db.add(
                        OpportunityEvent(
                            opportunity_id=opp.id,
                            event_type=_EVENT_TYPE_MAP.get(act_type, "note"),
                            entity_type="opportunity",
                            entity_id=opp.id,
                            description=summary,
                            occurred_at=ts,
                        )
                    )
                    total_evt += 1

            # 0-2 signals per opp.
            sig_count = RNG.choice([0, 1, 1, 2])
            for j in range(sig_count):
                ts = timestamps[-1] if timestamps else now
                st, sv = _pick_signal_type()
                db.add(
                    OpportunitySignal(
                        opportunity_id=opp.id,
                        signal_type=st,
                        severity=sv,
                        evidence=f"Auto-seeded {st} signal during activity backfill",
                        is_resolved=False,
                        created_at=ts,
                    )
                )
                total_sig += 1

            await db.flush()  # per-opp flush so partial progress is visible
            logger.info(
                "  ✓ opp=%d (%r): +%d activities", opp.id, opp.title, count,
            )

        await db.commit()
        logger.info(
            "Seed complete — activities=%d events=%d signals=%d across %d opps.",
            total_act, total_evt, total_sig, len(plan),
        )
        logger.info(
            "Next: trigger backfill-text-embeddings.yml + "
            "backfill-transformer-seq.yml to populate V8/V12 vectors."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed activity history for existing opportunities.",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Actually insert rows (default: dry-run)."
    )
    parser.add_argument(
        "--opp",
        action="append",
        type=int,
        default=None,
        help="Restrict to a specific opportunity id (repeatable).",
    )
    parser.add_argument(
        "--min-activities",
        type=int,
        default=3,
        help="Skip opps already having >= N activities (default 3).",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=90,
        help="Spread timestamps over the last N days (default 90).",
    )
    args = parser.parse_args()
    asyncio.run(
        main_async(
            opportunity_ids=args.opp,
            min_activities=args.min_activities,
            window_days=args.window_days,
            apply=args.apply,
        )
    )


if __name__ == "__main__":
    main()
