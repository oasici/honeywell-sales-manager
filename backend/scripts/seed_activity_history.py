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


# Activity-type names follow the V6 sequence-tokenizer vocabulary,
# not the activity_logs registry — the canonical projector passes
# ``activity_type`` through verbatim into ``sales_events_shadow``,
# and the tokenizer matches on the *shadow* event_type strings
# (``email_sent``, ``call_logged``, ``meeting_logged``, ``quote_sent``,
# ``stage_changed``, ``objection_logged``). Using these names ensures
# the synthesised events actually trigger tokenizer rules instead of
# silently passing through and producing empty token lists.
#
# Map activity_type → opportunity_event type. OpportunityEvent rows
# also feed the shadow, so we use the same vocabulary on both sides.
_EVENT_TYPE_MAP: dict[str, str] = {
    "email_sent": "email",
    "email_received": "email",
    "call_logged": "call",
    "meeting_logged": "meeting",
    "quote_sent": "quote",
    "stage_changed": "stage_change",
    "objection_logged": "note",
    "note_added": "note",
    "task_completed": "task",
}


# Realistic Turkish summary templates, chosen to give the V6
# tokenizer + V8 BoW something with vocabulary variety.
_SUMMARY_TEMPLATES: dict[str, list[str]] = {
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
    "call_logged": [
        "Müşteri ile fiyat görüşmesi yapıldı, ek bilgi talep edildi.",
        "Teknik şartname üzerinde mutabık kalındı.",
        "Sipariş süreci sorgulandı; satın alma onayı bekleniyor.",
        "Rakip teklif karşılaştırması istendi.",
    ],
    "meeting_logged": [
        "Karar mercileri ile demo toplantısı yapıldı.",
        "Yerinde keşif ve gereksinim çalışması.",
        "Pilot uygulama plan toplantısı.",
        "Yönetim seviyesi onay görüşmesi.",
    ],
    "quote_sent": [
        "İlk teklif paylaşıldı, kalem detayları onaya gönderildi.",
        "Revize teklif numarası paylaşıldı.",
    ],
    "stage_changed": [
        "Aşama ilerletildi: nitelendirildi",
        "Aşama: teklif onayı",
        "Pipeline aşaması güncellendi",
    ],
    "objection_logged": [
        "Müşteri fiyat itirazını gündeme getirdi.",
        "Rakip teklif baskısı oluştu, revizyon talep edildi.",
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


# Token-firing sequence template. Each tuple is ``(activity_type,
# days_back, hours_back)`` measured from ``now``. Designed to fire 4
# tokenizer rules per opp:
#   1. ``buyer_replied_within_48h`` — email_sent → email_received +12h
#   2. ``meeting_before_quote``      — meeting_logged precedes quote_sent
#   3. ``followup_within_24h_after_quote`` — call_logged +6h after quote_sent
#   4. ``stage_progressed_within_7d`` — two stage_changed within 7 days
# ``objection_logged`` then a later ``quote_sent`` would also fire
# ``quote_revised_after_objection`` but adding it would push the
# sequence past 8 events; we stop at the high-signal four.
_PATTERN_SEQUENCE: list[tuple[str, int, int]] = [
    ("stage_changed",   75,  0),  # day -75: prospecting → qualified
    ("email_sent",      60,  0),  # day -60: outreach
    ("email_received",  59, 12),  # day -59 +12h: buyer replies (rule 1)
    ("meeting_logged",  45,  0),  # day -45: discovery (precedes quote, rule 2)
    ("stage_changed",   42,  0),  # day -42: qualified → proposal (rule 8 with -75)
    ("quote_sent",      30,  0),  # day -30: first quote (rule 2 trigger)
    ("call_logged",     29, 18),  # day -29 +6h: followup (rule 6 — 24h window)
    ("note_added",      14,  0),  # day -14: noise/colour
]


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


def _build_pattern(
    *, count: int, window_days: int, now: datetime
) -> list[tuple[str, datetime]]:
    """Materialise the token-firing template into ``(activity_type, ts)``
    pairs in chronological order.

    ``count`` selects how many of the 8-event template to emit (4-8).
    The template is ordered so the first 4 events already trigger
    rules 1+2+6 (buyer-reply, meeting-before-quote, 24h-followup), so
    truncating to a smaller count still produces a non-empty token
    list. Timestamps are derived from the template offsets but
    rescaled to fit ``window_days`` if it's tighter than the default
    75-day pattern span.
    """
    pattern = _PATTERN_SEQUENCE[:count]
    max_days = max(d for _, d, _ in pattern)
    scale = min(1.0, window_days / max_days) if max_days else 1.0
    out: list[tuple[str, datetime]] = []
    for act_type, days_back, hours_back in pattern:
        offset = timedelta(
            days=days_back * scale,
            hours=hours_back * scale,
        )
        out.append((act_type, now - offset))
    out.sort(key=lambda p: p[1])
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
            # Skip predicate counts only token-firing v2 seed rows
            # (and any non-seed organic activity). The v1 seed rows
            # had non-canonical activity_types that don't trigger
            # tokenizer rules, so they shouldn't count toward the
            # "already has enough activity" threshold.
            existing = (
                await db.execute(
                    select(func.count(ActivityLog.id)).where(
                        ActivityLog.opportunity_id == opp.id,
                        (
                            ActivityLog.source_ref.is_(None)
                            | ~ActivityLog.source_ref.like("seed:%")
                        ),
                    )
                )
            ).scalar_one()
            if existing >= min_activities:
                logger.info(
                    "  opp=%d (%r) skipped: already has %d non-v1-seed activities",
                    opp.id, opp.title, existing,
                )
                continue
            # Always emit the full 8-event token-firing template so
            # rules 1+2+6+8 fire. Smaller counts would still produce
            # tokens but with weaker coverage.
            plan.append((opp, len(_PATTERN_SEQUENCE)))

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
            sequence = _build_pattern(count=count, window_days=window_days, now=now)
            for i, (act_type, ts) in enumerate(sequence):
                summary = _pick_summary(act_type)
                # Stable source_ref so the V4 shadow-sync de-dupes
                # on idempotent re-runs (and so re-running this
                # script after a vocabulary fix doesn't duplicate
                # rows that already use the new naming).
                # ``seed.v2`` prefix: the v1 prefix used registry
                # names like ``call`` / ``meeting`` that the V6
                # tokenizer doesn't match. Those rows still live in
                # the DB as inert noise; v2 rows use tokenizer-canon
                # vocabulary so rules actually fire. Skipping a
                # prefix bump would risk source_ref collisions in
                # sales_events_shadow on re-runs.
                source_ref = f"seed.v2:opp{opp.id}:act{i}:{act_type}"
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

                # Mirror every activity into opportunity_events so
                # both projections feed the shadow with consistent
                # timing — the tokenizer reads from the *union*, so
                # duplicate signals just reinforce rule firing.
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
            last_ts = sequence[-1][1] if sequence else now
            for j in range(sig_count):
                ts = last_ts
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
