"""Fill UI data gaps found during UAT testing.

Run AFTER seed_demo_data.py AND seed_uat_data.py:
    cd backend && source venv/bin/activate && python -m scripts.seed_uat_gaps

Creates:
1.  Revenue Signals (12) — Gelir Kokpiti
2.  AI Tasks (6) — Gelir Kokpiti
3.  Competitor Mentions (3) — Gelir Kokpiti
4.  Playbooks (4) + Executions (5)
5.  Rotting Opportunities — Sales Board (update + 3 new)
6.  Win/Loss Closed Opportunities (7) — Satis Analitigi + Siralama
7.  Pipeline Snapshots (8 weeks × 4 stages) — Satis Analitigi trend
8.  Opportunity Events — deal velocity + analytics
9.  Subscriptions (5) with MRR
10. Activity Logs (30 more) — SLA + leaderboard
11. Quote discount_total + close_reason patches
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
logger = logging.getLogger("seed-gaps")


async def seed_gaps() -> None:  # noqa: C901  (intentionally long seed function)
    from sqlalchemy import select, func, update

    from app.core.database import async_session, engine, Base
    from app.models.user import User
    from app.models.customer import Customer
    from app.models.spare_part import SparePart
    from app.models.quote import Quote
    from app.models.opportunity import Opportunity, OpportunityEvent, Task
    from app.models.activity_log import ActivityLog
    from app.models.revenue_signal import RevenueSignal
    from app.models.competitor_mention import CompetitorMention
    from app.models.playbook import Playbook, PlaybookExecution
    from app.models.forecast import PipelineSnapshot
    from app.models.subscription import Subscription

    # Ensure all tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        now = datetime.now(timezone.utc)

        # ── Idempotency guard ──
        sig_count = (
            await db.execute(select(func.count(RevenueSignal.id)))
        ).scalar() or 0
        if sig_count > 0:
            logger.info(
                "Gap data already seeded (%d revenue signals). Skipping.", sig_count
            )
            return

        # ── Load existing entities ──
        logger.info("Loading existing base entities...")

        admin = (
            await db.execute(select(User).where(User.email == "admin@honeywell.com"))
        ).scalar_one()
        rep = (
            await db.execute(select(User).where(User.email == "rep@honeywell.com"))
        ).scalar_one()

        admin_id = admin.id
        rep_id = rep.id

        customers = list(
            (await db.execute(select(Customer).order_by(Customer.id))).scalars().all()
        )
        parts = list(
            (await db.execute(select(SparePart).order_by(SparePart.id))).scalars().all()
        )
        quotes = list(
            (await db.execute(select(Quote).order_by(Quote.id))).scalars().all()
        )
        opps = list(
            (
                await db.execute(select(Opportunity).order_by(Opportunity.id))
            ).scalars().all()
        )

        logger.info(
            "Loaded: %d customers, %d parts, %d quotes, %d opps",
            len(customers),
            len(parts),
            len(quotes),
            len(opps),
        )

        # Convenience refs to the first 5 original opportunities
        opp1 = opps[0]
        opp2 = opps[1]
        opp3 = opps[2]
        opp4 = opps[3]
        opp5 = opps[4] if len(opps) >= 5 else opps[0]

        # ── 1. REVENUE SIGNALS ──
        logger.info("Creating revenue signals...")

        signals_spec = [
            # (signal_type, severity, opp, owner_id, is_resolved, description)
            ("no_touch",               "high",     opp1, rep_id,   False, "Son 14 gunde aktivite yok"),
            ("churn_risk",             "critical", opp2, rep_id,   False, "Musteri yanit vermiyor, 3 email cevapsiz"),
            ("cross_sell_opportunity", "med",      opp3, admin_id, False, "Sensor paketi alimina ek filtre onerileri"),
            ("pricing_concern",        "high",     opp1, rep_id,   False, "Rakip fiyat %15 daha dusuk"),
            ("upsell_detected",        "med",      opp4, admin_id, False, "Mevcut siparis hacmi 2x artti"),
            ("forecast_miss",          "high",     opp2, rep_id,   True,  "Kapanma tarihi 2 kez ertelendi"),
            ("expansion_signal",       "low",      opp3, rep_id,   False, "Yeni tesis acilisi planlaniyor"),
            ("no_touch",               "med",      opp4, admin_id, False, "7 gundur iletisim yok"),
            ("churn_risk",             "high",     opp1, rep_id,   False, "NPS skoru dusuk"),
            ("positive",               "low",      opp5, admin_id, True,  "Musteri tavsiye etti"),
            ("cross_sell_opportunity", "med",      opp2, rep_id,   False, "DCS modul ihtiyaci tespit edildi"),
            ("pricing_concern",        "low",      opp3, admin_id, True,  "Fiyat araligi onaylandi"),
        ]

        for i, (sig_type, severity, opp, owner_id, resolved, desc) in enumerate(signals_spec):
            db.add(RevenueSignal(
                signal_type=sig_type,
                severity=severity,
                source_entity_type="opportunity",
                source_entity_id=opp.id,
                opportunity_id=opp.id,
                customer_id=opp.customer_id,
                owner_id=owner_id,
                confidence=round(random.uniform(0.6, 0.95), 2),
                recommended_action=desc,
                metadata_json=json.dumps({"description": desc}),
                is_resolved=resolved,
                event_key=f"gap-signal-{i+1}",
                created_at=now - timedelta(days=random.randint(0, 14)),
            ))

        await db.flush()
        logger.info("Created %d revenue signals", len(signals_spec))

        # ── 2. AI TASKS ──
        logger.info("Creating AI tasks...")

        ai_tasks_spec = [
            (rep_id,   opp1, "Anadolu Endustri ile takip gorusmesi yap",      "open", "high",   "ai"),
            (rep_id,   opp2, "Ege Mekatronik icin fiyat karsilastirmasi hazirla", "open", "urgent", "ai"),
            (admin_id, opp3, "Karadeniz Oto referans musterisi bul",           "open", "normal", "ai"),
            (rep_id,   opp4, "Marmara HVAC yeni ihtiyac analizi",              "open", "high",   "ai"),
            (admin_id, opp5, "GAP Muhendislik sozlesme yenileme",              "done", "normal", "ai"),
            (rep_id,   opp1, "Rakip analiz raporu guncelle",                   "open", "normal", "ai"),
        ]

        for owner_id, opp, title, status, priority, source in ai_tasks_spec:
            db.add(Task(
                owner_id=owner_id,
                opportunity_id=opp.id,
                title=title,
                status=status,
                priority=priority,
                source=source,
                due_at=now + timedelta(days=random.randint(1, 7)),
                created_at=now - timedelta(days=random.randint(0, 5)),
            ))

        await db.flush()
        logger.info("Created %d AI tasks", len(ai_tasks_spec))

        # ── 3. COMPETITOR MENTIONS ──
        logger.info("Creating competitor mentions...")

        mention_spec = [
            (
                "Schneider Electric",
                "Schneider Electric ayni urun grubunda %10 daha ucuz teklif vermis",
                opp1.id, rep_id,
            ),
            (
                "Siemens",
                "Siemens PLC alternatifi musteri tarafindan degerlendiriliyor",
                opp2.id, rep_id,
            ),
            (
                "ABB",
                "ABB aktuator fiyatlari karsilastirildi, Honeywell avantajli",
                opp3.id, admin_id,
            ),
        ]

        for competitor, snippet, opp_id, detected_by_user in mention_spec:
            db.add(CompetitorMention(
                competitor_name=competitor,
                source_entity_type="opportunity",
                source_entity_id=opp_id,
                opportunity_id=opp_id,
                context_snippet=snippet,
                sentiment="negative" if "ucuz" in snippet or "alternatif" in snippet else "positive",
                detected_by="ai",
                created_at=now - timedelta(days=random.randint(1, 10)),
            ))

        await db.flush()
        logger.info("Created %d competitor mentions", len(mention_spec))

        # ── 4. PLAYBOOKS + EXECUTIONS ──
        logger.info("Creating playbooks...")

        playbook_spec = [
            (
                "Yeni Musteri Kazanim",
                "Yeni musteri kazanim sureci",
                "acquisition",
                '[{"field":"stage","op":"equals","value":"prospecting"}]',
                '[{"step":1,"action":"Tanitim emaili gonder","delay_days":0},'
                '{"step":2,"action":"Demo plani","delay_days":3},'
                '{"step":3,"action":"Teklif hazirla","delay_days":7}]',
            ),
            (
                "Buyuk Firsat Takibi",
                "100K+ firsatlar icin ozel takip",
                "enterprise",
                '[{"field":"amount","op":"gte","value":100000}]',
                '[{"step":1,"action":"Ust yonetim toplantisi","delay_days":0},'
                '{"step":2,"action":"Referans sunumu","delay_days":5},'
                '{"step":3,"action":"Ozel fiyat hazirla","delay_days":10}]',
            ),
            (
                "Churn Onleme",
                "Risk altindaki musteriler icin",
                "retention",
                '[{"field":"health_score","op":"lt","value":50}]',
                '[{"step":1,"action":"Acil arama yap","delay_days":0},'
                '{"step":2,"action":"Ozel indirim teklifi","delay_days":2}]',
            ),
            (
                "Cross-Sell Firsati",
                "Mevcut musterilere ek urun satisi",
                "growth",
                '[{"field":"signal_type","op":"equals","value":"cross_sell_opportunity"}]',
                '[{"step":1,"action":"Urun katalogu gonder","delay_days":0},'
                '{"step":2,"action":"Tanitim toplantisi ayarla","delay_days":3}]',
            ),
        ]

        playbooks: list[Playbook] = []
        for name, desc, category, trigger_json, steps_json in playbook_spec:
            pb = Playbook(
                name=name,
                description=desc,
                category=category,
                trigger_conditions_json=trigger_json,
                steps_json=steps_json,
                is_active=True,
                created_by=admin_id,
                created_at=now - timedelta(days=30),
            )
            db.add(pb)
            playbooks.append(pb)

        await db.flush()
        logger.info("Created %d playbooks", len(playbooks))

        # Executions: some active, some completed
        execution_spec = [
            # (playbook, opp, status, current_step, completed_days_ago)
            (playbooks[0], opp1, "active",    2, None),
            (playbooks[0], opp3, "completed", 3, 5),
            (playbooks[1], opp4, "active",    1, None),
            (playbooks[2], opp2, "active",    1, None),
            (playbooks[3], opp3, "completed", 2, 10),
        ]

        for pb, opp, status, step, completed_days_ago in execution_spec:
            completed_at = (
                now - timedelta(days=completed_days_ago)
                if completed_days_ago is not None
                else None
            )
            db.add(PlaybookExecution(
                playbook_id=pb.id,
                opportunity_id=opp.id,
                current_step=step,
                status=status,
                started_at=now - timedelta(days=random.randint(5, 20)),
                completed_at=completed_at,
                next_action_at=now + timedelta(days=1) if status == "active" else None,
            ))

        await db.flush()
        logger.info("Created %d playbook executions", len(execution_spec))

        # ── 5. ROTTING OPPORTUNITIES ──
        logger.info("Aging opportunities for rotting detection...")

        # Mark 2 existing opportunities as stale
        rotting_candidates = [
            o for o in opps
            if o.stage in ("prospecting", "qualified", "proposal")
        ]
        for i, opp in enumerate(rotting_candidates[:2]):
            opp.updated_at = now - timedelta(days=12 + i * 5)

        await db.flush()

        # Add 3 fresh active opportunities to populate the board
        new_opp_spec = [
            ("Kocaeli Filtre - Yillik Tedarikat", "proposal",    175000, customers[9].id, rep_id),
            ("Bolu Termal - Sistem Yenileme",     "qualified",   95000,  customers[8].id, admin_id),
            ("Akdeniz Proses - Otomasyon Paketi", "negotiation", 310000, customers[5].id, rep_id),
        ]

        new_opps: list[Opportunity] = []
        for title, stage, amount, cust_id, owner_id in new_opp_spec:
            o = Opportunity(
                title=title,
                stage=stage,
                amount=amount,
                currency="TRY",
                customer_id=cust_id,
                owner_id=owner_id,
                close_date=(now + timedelta(days=random.randint(14, 60))).date(),
                forecast_category=random.choice(["pipeline", "best_case", "commit"]),
                created_at=now - timedelta(days=random.randint(1, 10)),
            )
            db.add(o)
            new_opps.append(o)

        await db.flush()
        logger.info(
            "Aged %d rotting opps; created %d new active opps",
            min(2, len(rotting_candidates)),
            len(new_opps),
        )

        # ── 6. CLOSED OPPORTUNITIES (win/loss for analytics) ──
        logger.info("Creating closed opportunities for analytics...")

        closed_opp_spec = [
            ("Ankara Teknik - Vana Paketi",    "closed_won",  78000,  customers[3].id, rep_id,   None),
            ("Trakya End. - Sensor Tedarikat", "closed_won",  145000, customers[6].id, admin_id, None),
            ("Ege Mek. - Filtre Yenileme",     "closed_lost", 62000,  customers[1].id, rep_id,   "Fiyat yuksek"),
            ("Bolu Termal - PLC Projesi",      "closed_lost", 210000, customers[8].id, admin_id, "Rakip tercih edildi"),
            ("GAP Muh. - Ek Siparis",          "closed_won",  95000,  customers[7].id, rep_id,   None),
            ("Anadolu End. - DCS Upgrade",     "closed_lost", 320000, customers[0].id, rep_id,   "Butce yetersiz"),
            ("Marmara HVAC - Dedektör Sist.",  "closed_won",  56000,  customers[4].id, admin_id, None),
        ]

        closed_opps: list[Opportunity] = []
        for i, (title, stage, amount, cust_id, owner_id, loss_reason) in enumerate(
            closed_opp_spec
        ):
            close_days_ago = random.randint(2, 28)
            o = Opportunity(
                title=title,
                stage=stage,
                amount=amount,
                currency="TRY",
                customer_id=cust_id,
                owner_id=owner_id,
                status="closed",
                loss_reason=loss_reason,
                forecast_category="closed",
                close_date=(now - timedelta(days=close_days_ago)).date(),
                created_at=now - timedelta(days=close_days_ago + random.randint(10, 45)),
                updated_at=now - timedelta(days=close_days_ago),
            )
            db.add(o)
            closed_opps.append(o)

        await db.flush()
        logger.info("Created %d closed opportunities", len(closed_opps))

        # ── 7. PIPELINE SNAPSHOTS (8 weeks of trend data) ──
        logger.info("Creating pipeline snapshots...")

        stages_for_snapshot = ["prospecting", "qualified", "proposal", "negotiation"]
        stage_weights = {"prospecting": 0.20, "qualified": 0.25, "proposal": 0.30, "negotiation": 0.25}
        stage_probs = {"prospecting": 0.10, "qualified": 0.25, "proposal": 0.50, "negotiation": 0.75}

        snapshot_count = 0
        for week in range(8):
            week_date = (now - timedelta(weeks=7 - week)).date()
            base_total = 500_000 + week * 35_000 + random.randint(-20_000, 20_000)
            total_count = 12 + week

            for stage in stages_for_snapshot:
                weight = stage_weights[stage]
                stage_amount = base_total * weight
                stage_count = max(1, round(total_count * weight))
                prob = stage_probs[stage]

                db.add(PipelineSnapshot(
                    snapshot_date=week_date,
                    stage=stage,
                    opportunity_count=stage_count,
                    total_amount=stage_amount,
                    weighted_amount=stage_amount * prob,
                    created_at=now - timedelta(weeks=7 - week),
                ))
                snapshot_count += 1

        await db.flush()
        logger.info("Created %d pipeline snapshot rows (8 weeks × 4 stages)", snapshot_count)

        # ── 8. OPPORTUNITY EVENTS (deal velocity + analytics) ──
        logger.info("Creating opportunity events...")

        all_opps = opps + new_opps + closed_opps
        event_count = 0
        stage_sequence = ["prospecting", "qualified", "proposal", "negotiation"]

        for opp in all_opps:
            # Determine how far through the funnel this opp went
            if opp.stage == "closed_won":
                stages_passed = stage_sequence  # all 4 stages
            elif opp.stage == "closed_lost":
                stages_passed = stage_sequence[:3]
            elif opp.stage == "negotiation":
                stages_passed = stage_sequence
            elif opp.stage == "proposal":
                stages_passed = stage_sequence[:3]
            elif opp.stage == "qualified":
                stages_passed = stage_sequence[:2]
            else:
                stages_passed = stage_sequence[:1]

            for i, stage in enumerate(stages_passed):
                db.add(OpportunityEvent(
                    opportunity_id=opp.id,
                    event_type="stage_change",
                    description=f"Asama degisti: {stage}",
                    occurred_at=now - timedelta(days=60 - i * 12),
                ))
                event_count += 1

        await db.flush()
        logger.info("Created %d opportunity events", event_count)

        # ── 9. SUBSCRIPTIONS ──
        logger.info("Creating subscriptions...")

        filt_part = next((p for p in parts if p.honeywell_code == "HW-FILT-001"), parts[7])
        sens_part = next((p for p in parts if p.honeywell_code == "HW-SENS-001"), parts[2])

        subscription_spec = [
            # (name, customer_idx, status, billing_cycle, mrr, start_days_ago, end_days_from_now)
            ("Anadolu HVAC Bakim Aboneligi",  0, "active",    "monthly",   12500, 180, 185),
            ("Ege Sensor Takip Servisi",      1, "active",    "monthly",   8500,  90,  275),
            ("Marmara HVAC Premium",          4, "active",    "quarterly", 25000, 60,  305),
            ("GAP Muhendislik Destek",        7, "cancelled", "monthly",   6000,  365, -30),
            ("Kocaeli Filtre Yenileme",       9, "active",    "monthly",   4500,  45,  320),
        ]

        items_filt = json.dumps([
            {"part": filt_part.honeywell_code, "qty": 50},
            {"part": sens_part.honeywell_code, "qty": 20},
        ])

        for name, cust_idx, status, billing_cycle, mrr, start_ago, end_from_now in subscription_spec:
            start_date = (now - timedelta(days=start_ago)).date()
            end_date = (now + timedelta(days=end_from_now)).date()
            is_active = status == "active"
            # Next renewal within 30 days for active subs
            next_renewal = (now + timedelta(days=random.randint(5, 30))).date() if is_active else None

            db.add(Subscription(
                name=name,
                customer_id=customers[cust_idx].id,
                status=status,
                billing_cycle=billing_cycle,
                mrr=mrr,
                start_date=start_date,
                end_date=end_date,
                next_renewal_date=next_renewal,
                auto_renew=is_active,
                items_json=items_filt,
                currency="TRY",
                created_by=admin_id,
                created_at=now - timedelta(days=start_ago),
            ))

        await db.flush()
        logger.info("Created %d subscriptions", len(subscription_spec))

        # ── 10. ACTIVITY LOGS (30 more for SLA + leaderboard) ──
        logger.info("Creating additional activity logs...")

        all_opp_ids = [o.id for o in all_opps]
        all_customer_ids = [c.id for c in customers]
        activity_types = ["call", "email_sent", "meeting", "note", "quote_created", "demo"]
        entity_types = ["opportunity", "customer", "quote"]
        summaries = [
            "Telefon gorusmesi",
            "Toplanti notu",
            "Email takip",
            "Teklif gonderimi",
            "Demo sunumu",
            "Musteri ziyareti",
        ]

        for i in range(30):
            activity_type = random.choice(activity_types)
            entity_type = random.choice(entity_types)
            has_opp = random.random() > 0.3
            has_duration = random.random() > 0.3

            db.add(ActivityLog(
                activity_type=activity_type,
                entity_type=entity_type,
                entity_id=random.randint(1, 15),
                opportunity_id=random.choice(all_opp_ids) if has_opp else None,
                customer_id=random.choice(all_customer_ids),
                user_id=random.choice([admin_id, rep_id]),
                summary=f"Aktivite #{i + 1} - {random.choice(summaries)}",
                duration_minutes=random.randint(5, 120) if has_duration else None,
                created_at=now - timedelta(days=random.randint(0, 30)),
            ))

        await db.flush()
        logger.info("Created 30 additional activity log entries")

        # ── 11. QUOTE DISCOUNT + CLOSE REASON PATCHES ──
        logger.info("Patching quotes with discount_total and close_reason...")

        loss_reasons = ["Fiyat yuksek", "Teslimat suresi uzun", "Rakip tercih edildi"]
        win_reasons = ["Fiyat uygun", "Kalite", "Mevcut iliski"]

        patched = 0
        for q in quotes:
            if q.subtotal and q.grand_total:
                q.discount_total = round(q.subtotal * random.uniform(0.05, 0.15), 2)
                patched += 1

            if q.status == "rejected":
                q.close_reason = random.choice(loss_reasons)
                q.closed_at = now - timedelta(days=random.randint(1, 20))
            elif q.status == "accepted":
                q.close_reason = random.choice(win_reasons)
                q.closed_at = now - timedelta(days=random.randint(1, 15))

        await db.flush()
        logger.info("Patched %d quotes with discount_total / close_reason", patched)

        # ── COMMIT ──
        await db.commit()

        logger.info("=" * 60)
        logger.info("UAT GAP SEED COMPLETE")
        logger.info("=" * 60)
        logger.info("  Revenue Signals:      12")
        logger.info("  AI Tasks:              6")
        logger.info("  Competitor Mentions:   3")
        logger.info("  Playbooks:             4 (+ 5 executions)")
        logger.info("  New Active Opps:       3")
        logger.info("  Closed Opps (W/L):     7")
        logger.info("  Pipeline Snapshots:   %d (8 weeks × 4 stages)", snapshot_count)
        logger.info("  Opportunity Events:   %d", event_count)
        logger.info("  Subscriptions:         5")
        logger.info("  Activity Logs:        30 added")
        logger.info("  Quotes patched:       %d", patched)
        logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed_gaps())
