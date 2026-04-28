"""Seed UAT data for Honeywell Sales Manager — Sprint 1-8 features.

Run AFTER seed_demo_data.py:
    cd backend && source venv/bin/activate && python -m scripts.seed_uat_data

Creates data for all new features:
- Campaigns (3) with members (15+)
- Account hierarchy (parent/child)
- Pipelines (3) with stages
- Territories (5) with assignments
- Invoices (5) from quotes
- E-Signatures (3)
- Contracts (4)
- Advanced pricing (tiers + customer pricing)
- Revenue recognition (2 schedules)
- Chat sessions (2) with messages + auto-response rules (3)
- Email templates (3)
- Workflow rules (2)
- Comments (5)
- Achievements (3)
- Stage configs (6)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
logger = logging.getLogger("seed_uat")

NOW = datetime.now(timezone.utc)


async def seed_uat():
    from sqlalchemy import select, func

    from app.core.database import async_session, engine, Base
    from app.models.user import User
    from app.models.customer import Customer
    from app.models.spare_part import SparePart
    from app.models.price_entry import PriceEntry
    from app.models.quote import Quote
    from app.models.opportunity import Opportunity
    from app.models.lead import Lead
    from app.models.campaign import Campaign, CampaignMember
    from app.models.pipeline import Pipeline
    from app.models.territory import Territory, TerritoryAssignment
    from app.models.invoice import Invoice
    from app.models.signature import SignatureRequest
    from app.models.contract import Contract
    from app.models.pricing import PriceTier, CustomerPricing
    from app.models.revenue_recognition import RevenueSchedule, RevenueScheduleEntry
    from app.models.chat import ChatSession, ChatMessage, AutoResponseRule
    from app.models.email_template import EmailTemplate
    from app.models.workflow_rule import WorkflowRule
    from app.models.comment import Comment
    from app.models.achievement import Achievement
    from app.models.stage_config import StageConfig

    # Create tables (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        # ── Guard: skip if UAT data already exists ──
        campaign_count = (await db.execute(select(func.count(Campaign.id)))).scalar() or 0
        if campaign_count > 0:
            logger.info(
                "UAT data already exists (%d campaigns). Skipping.", campaign_count
            )
            return

        # ── Fetch existing base-seed entities ──
        logger.info("Fetching existing base-seed entities...")

        admin = (
            await db.execute(select(User).where(User.email == "admin@honeywell.com"))
        ).scalar_one()
        rep = (
            await db.execute(select(User).where(User.email == "rep@honeywell.com"))
        ).scalar_one()
        ops = (
            await db.execute(select(User).where(User.email == "ops@honeywell.com"))
        ).scalar_one()

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
        leads = list(
            (await db.execute(select(Lead).order_by(Lead.id))).scalars().all()
        )
        price_entries = list(
            (await db.execute(select(PriceEntry).order_by(PriceEntry.id))).scalars().all()
        )

        admin_id = admin.id
        rep_id = rep.id
        ops_id = ops.id

        logger.info(
            "Base data: %d customers, %d parts, %d quotes, %d opps, %d leads",
            len(customers),
            len(parts),
            len(quotes),
            len(opps),
            len(leads),
        )

        # ── 1. CAMPAIGNS ──
        logger.info("Creating campaigns...")
        campaign_defs = [
            ("Q1 2026 Sensor Kampanyasi", "email", "active", 15000, 5000, 45000, 32000),
            ("HVAC Yenileme Webinari", "webinar", "completed", 8000, 6500, 120000, 98000),
            ("Yeni Musteri Sosyal Medya", "social", "draft", 20000, 0, 0, 0),
        ]
        campaigns = []
        for name, ctype, status, budget, cost, exp_rev, act_rev in campaign_defs:
            c = Campaign(
                name=name,
                type=ctype,
                status=status,
                budget=budget,
                actual_cost=cost,
                expected_revenue=exp_rev,
                actual_revenue=act_rev,
                start_date=NOW - timedelta(days=30),
                end_date=NOW + timedelta(days=60),
                created_by=admin_id,
                description=f"{name} - UAT demo verisi",
            )
            db.add(c)
            campaigns.append(c)
        await db.flush()

        # Campaign members — leads and customers with various statuses
        member_statuses = ["sent", "opened", "clicked", "responded", "converted", "unsubscribed"]
        member_count = 0
        for lead in leads:
            cm = CampaignMember(
                campaign_id=campaigns[0].id,
                lead_id=lead.id,
                status=member_statuses[member_count % len(member_statuses)],
            )
            db.add(cm)
            member_count += 1

        for i, cust in enumerate(customers):
            target_campaign = campaigns[i % len(campaigns)]
            cm = CampaignMember(
                campaign_id=target_campaign.id,
                customer_id=cust.id,
                status=member_statuses[i % len(member_statuses)],
                responded_at=NOW - timedelta(days=i) if i % 3 == 0 else None,
            )
            db.add(cm)
            member_count += 1
        await db.flush()
        logger.info("Created %d campaigns with %d members", len(campaigns), member_count)

        # ── 2. ACCOUNT HIERARCHY ──
        logger.info("Setting up account hierarchy...")
        # customers[0] = Anadolu Endustri, [6] = Trakya Endustriyel, [7] = GAP Muhendislik
        # customers[4] = Marmara HVAC, [8] = Bolu Termal
        customers[6].parent_id = customers[0].id  # Trakya -> Anadolu
        customers[7].parent_id = customers[0].id  # GAP -> Anadolu
        customers[8].parent_id = customers[4].id  # Bolu -> Marmara
        await db.flush()
        logger.info(
            "Account hierarchy: Anadolu->Trakya,GAP | Marmara->Bolu"
        )

        # ── 3. PIPELINES ──
        logger.info("Creating pipelines...")
        pipeline_defs = [
            (
                "Standart Satış",
                True,
                [
                    {"key": "prospecting", "label": "Araştırma", "order": 1, "probability": 10},
                    {"key": "qualified", "label": "Nitelendirme", "order": 2, "probability": 25},
                    {"key": "proposal", "label": "Teklif", "order": 3, "probability": 50},
                    {"key": "negotiation", "label": "Müzakere", "order": 4, "probability": 75},
                    {"key": "closed_won", "label": "Kazanıldı", "order": 5, "probability": 100},
                    {"key": "closed_lost", "label": "Kaybedildi", "order": 6, "probability": 0},
                ],
            ),
            (
                "Hızlı Satış",
                False,
                [
                    {"key": "lead", "label": "Aday", "order": 1, "probability": 20},
                    {"key": "demo", "label": "Demo", "order": 2, "probability": 50},
                    {"key": "closing", "label": "Kapanış", "order": 3, "probability": 80},
                    {"key": "won", "label": "Kazanıldı", "order": 4, "probability": 100},
                ],
            ),
            (
                "Proje Satisi",
                False,
                [
                    {"key": "discovery", "label": "Kesif", "order": 1, "probability": 5},
                    {"key": "solution_design", "label": "Cozum Tasarimi", "order": 2, "probability": 20},
                    {"key": "poc", "label": "POC", "order": 3, "probability": 40},
                    {"key": "commercial", "label": "Ticari Muzakere", "order": 4, "probability": 60},
                    {"key": "legal", "label": "Sozlesme", "order": 5, "probability": 85},
                    {"key": "won", "label": "Kazanildi", "order": 6, "probability": 100},
                    {"key": "lost", "label": "Kaybedildi", "order": 7, "probability": 0},
                ],
            ),
        ]
        pipelines = []
        for name, is_default, stages in pipeline_defs:
            p = Pipeline(
                name=name,
                is_default=is_default,
                stages_json=json.dumps(stages, ensure_ascii=False),
                description=f"{name} pipeline - UAT",
                created_by=admin_id,
            )
            db.add(p)
            pipelines.append(p)
        await db.flush()

        # Assign some opportunities to the default pipeline
        for opp in opps:
            opp.pipeline_id = pipelines[0].id
        await db.flush()
        logger.info("Created %d pipelines", len(pipelines))

        # ── 4. TERRITORIES ──
        logger.info("Creating territories...")
        t_marmara = Territory(
            name="Marmara Bolgesi",
            region="Marmara",
            description="Istanbul, Bursa, Kocaeli ve cevre iller",
            created_by=admin_id,
        )
        db.add(t_marmara)
        await db.flush()

        t_istanbul = Territory(
            name="Istanbul Saha",
            region="Marmara",
            parent_id=t_marmara.id,
            description="Istanbul ili saha satislari",
            created_by=admin_id,
        )
        t_bursa_kocaeli = Territory(
            name="Bursa-Kocaeli",
            region="Marmara",
            parent_id=t_marmara.id,
            description="Bursa ve Kocaeli saha satislari",
            created_by=admin_id,
        )
        db.add_all([t_istanbul, t_bursa_kocaeli])
        await db.flush()

        t_anadolu = Territory(
            name="Anadolu Bolgesi",
            region="Ic Anadolu",
            description="Ankara ve Ic Anadolu bolgesi",
            created_by=admin_id,
        )
        t_ege = Territory(
            name="Ege-Akdeniz Bolgesi",
            region="Ege",
            description="Izmir, Antalya ve cevre iller",
            created_by=admin_id,
        )
        db.add_all([t_anadolu, t_ege])
        await db.flush()

        # Territory assignments
        db.add(TerritoryAssignment(territory_id=t_istanbul.id, user_id=rep_id, role="owner"))
        db.add(TerritoryAssignment(territory_id=t_marmara.id, user_id=admin_id, role="owner"))
        db.add(TerritoryAssignment(territory_id=t_anadolu.id, user_id=ops_id, role="member"))
        db.add(TerritoryAssignment(territory_id=t_ege.id, user_id=rep_id, role="member"))
        await db.flush()

        # Assign territory to some customers
        customers[0].territory_id = t_istanbul.id      # Anadolu Endustri -> Istanbul
        customers[4].territory_id = t_istanbul.id      # Marmara HVAC -> Istanbul
        customers[1].territory_id = t_ege.id           # Ege Mekatronik -> Ege
        customers[3].territory_id = t_anadolu.id       # Ankara Teknik -> Anadolu
        customers[9].territory_id = t_bursa_kocaeli.id # Kocaeli Filtre -> Bursa-Kocaeli

        # Assign territory to some opportunities
        if len(opps) >= 3:
            opps[0].territory_id = t_istanbul.id
            opps[1].territory_id = t_ege.id
            opps[3].territory_id = t_istanbul.id
        await db.flush()
        logger.info(
            "Created 5 territories with %d assignments",
            4,
        )

        # ── 5. CONTRACTS ──
        logger.info("Creating contracts...")
        contract_defs = [
            ("Anadolu HVAC Bakim Sozlesmesi", "active", 250000, 12, customers[0].id),
            ("Ege Sensor Tedarikat", "active", 180000, 6, customers[1].id),
            ("Karadeniz Yillik Servis", "draft", 95000, 12, customers[2].id),
            ("GAP Proses Otomasyon", "completed", 350000, 24, customers[7].id),
        ]
        contracts = []
        for title, status, value, months, cust_id in contract_defs:
            ct = Contract(
                title=title,
                status=status,
                value=value,
                customer_id=cust_id,
                start_date=(NOW - timedelta(days=months * 15)).date(),
                end_date=(NOW + timedelta(days=months * 15)).date(),
                created_by=admin_id,
                signed_at=NOW - timedelta(days=months * 15) if status != "draft" else None,
                signed_by="Yetkili Imzaci" if status != "draft" else None,
            )
            db.add(ct)
            contracts.append(ct)
        await db.flush()
        logger.info("Created %d contracts", len(contracts))

        # ── 6. INVOICES ──
        logger.info("Creating invoices...")
        # Find quotes by status for realistic invoice creation
        accepted_quotes = [q for q in quotes if q.status == "accepted"]
        approved_quotes = [q for q in quotes if q.status == "approved"]
        sent_quotes = [q for q in quotes if q.status == "sent"]

        invoice_defs = [
            ("INV-2026-0001", "paid", accepted_quotes[0] if accepted_quotes else quotes[0]),
            ("INV-2026-0002", "sent", accepted_quotes[1] if len(accepted_quotes) > 1 else quotes[1]),
            ("INV-2026-0003", "draft", approved_quotes[0] if approved_quotes else quotes[2]),
            ("INV-2026-0004", "overdue", sent_quotes[0] if sent_quotes else quotes[3]),
            ("INV-2026-0005", "voided", accepted_quotes[2] if len(accepted_quotes) > 2 else quotes[4]),
        ]
        invoices = []
        for inv_num, status, quote in invoice_defs:
            inv = Invoice(
                invoice_number=inv_num,
                quote_id=quote.id,
                customer_id=quote.customer_id,
                created_by=rep_id,
                issue_date=NOW - timedelta(days=15),
                due_date=NOW + timedelta(days=30),
                status=status,
                currency=quote.currency or "TRY",
                subtotal=quote.subtotal or 10000,
                tax_rate=quote.tax_rate or 18.0,
                tax_amount=quote.tax_amount or 1800,
                grand_total=quote.grand_total or 11800,
                notes=f"Fatura - {inv_num}",
                paid_at=NOW - timedelta(days=5) if status == "paid" else None,
            )
            db.add(inv)
            invoices.append(inv)
        await db.flush()
        logger.info("Created %d invoices", len(invoices))

        # ── 7. E-SIGNATURES ──
        logger.info("Creating signature requests...")
        sig_defs = [
            ("quote", quotes[0].id, "signed", "satis@anadoluendustri.com.tr", "Ahmet Yilmaz"),
            ("contract", contracts[0].id, "pending", "info@egemekatronik.com", "Ege Mekatronik Yetkili"),
            ("invoice", invoices[0].id, "expired", "siparis@karadenizoto.com.tr", "Karadeniz Otomasyon"),
        ]
        for doc_type, doc_id, status, signer_email, signer_name in sig_defs:
            sig = SignatureRequest(
                document_type=doc_type,
                document_id=doc_id,
                signer_email=signer_email,
                signer_name=signer_name,
                status=status,
                signed_at=NOW - timedelta(days=3) if status == "signed" else None,
                viewed_at=NOW - timedelta(days=5) if status != "pending" else None,
                expires_at=NOW + timedelta(days=7) if status != "expired" else NOW - timedelta(days=1),
                created_by=rep_id,
            )
            db.add(sig)
        await db.flush()
        logger.info("Created 3 signature requests")

        # ── 8. ADVANCED PRICING ──
        logger.info("Creating advanced pricing tiers...")
        # Find price entries for specific parts
        filt_entry = None
        sens_entry = None
        valve_entry = None
        for pe in price_entries:
            for p in parts:
                if p.id == pe.spare_part_id:
                    if p.honeywell_code == "HW-FILT-001":
                        filt_entry = pe
                    elif p.honeywell_code == "HW-SENS-001":
                        sens_entry = pe
                    elif p.honeywell_code == "HW-VALVE-001":
                        valve_entry = pe

        tier_count = 0
        if filt_entry:
            for min_q, max_q, price, disc in [
                (1, 49, 95, 0),
                (50, 199, 85, 10.5),
                (200, None, 72, 24.2),
            ]:
                db.add(PriceTier(
                    price_entry_id=filt_entry.id,
                    min_qty=min_q,
                    max_qty=max_q,
                    unit_price=price,
                    discount_pct=disc,
                ))
                tier_count += 1

        if sens_entry:
            for min_q, max_q, price, disc in [
                (1, 9, 320, 0),
                (10, 49, 290, 9.4),
                (50, None, 260, 18.7),
            ]:
                db.add(PriceTier(
                    price_entry_id=sens_entry.id,
                    min_qty=min_q,
                    max_qty=max_q,
                    unit_price=price,
                    discount_pct=disc,
                ))
                tier_count += 1

        if valve_entry:
            for min_q, max_q, price, disc in [
                (1, 4, 850, 0),
                (5, 19, 780, 8.2),
                (20, None, 700, 17.6),
            ]:
                db.add(PriceTier(
                    price_entry_id=valve_entry.id,
                    min_qty=min_q,
                    max_qty=max_q,
                    unit_price=price,
                    discount_pct=disc,
                ))
                tier_count += 1
        await db.flush()

        # Customer contracted pricing
        cp_count = 0
        filt_part = next((p for p in parts if p.honeywell_code == "HW-FILT-001"), None)
        sens_part = next((p for p in parts if p.honeywell_code == "HW-SENS-001"), None)

        if filt_part and len(customers) > 0:
            db.add(CustomerPricing(
                customer_id=customers[0].id,
                spare_part_id=filt_part.id,
                contracted_price=70,
                currency="USD",
                discount_pct=26.3,
                valid_from=NOW - timedelta(days=90),
                valid_until=NOW + timedelta(days=275),
                notes="Anadolu Endustri yillik sozlesme fiyati",
                created_by=admin_id,
            ))
            cp_count += 1

        if sens_part and len(customers) > 4:
            db.add(CustomerPricing(
                customer_id=customers[4].id,
                spare_part_id=sens_part.id,
                contracted_price=275,
                currency="USD",
                discount_pct=14.1,
                valid_from=NOW - timedelta(days=60),
                valid_until=NOW + timedelta(days=305),
                notes="Marmara HVAC ozel fiyat anlasmasi",
                created_by=admin_id,
            ))
            cp_count += 1
        await db.flush()
        logger.info("Created %d price tiers, %d customer pricing entries", tier_count, cp_count)

        # ── 9. REVENUE RECOGNITION ──
        logger.info("Creating revenue recognition schedules...")
        rev_schedules = []

        # Schedule 1: straight_line, 12 months, total 250000 (from contract[0])
        sched1 = RevenueSchedule(
            contract_id=contracts[0].id,
            recognition_type="straight_line",
            start_date=NOW - timedelta(days=180),
            end_date=NOW + timedelta(days=180),
            total_amount=250000,
            recognized_amount=0,
            currency="TRY",
            created_by=admin_id,
        )
        db.add(sched1)
        await db.flush()
        rev_schedules.append(sched1)

        monthly_amount_1 = round(250000 / 12, 2)
        recognized_total_1 = 0.0
        for month_offset in range(12):
            entry_date = NOW - timedelta(days=180) + timedelta(days=month_offset * 30)
            period = entry_date.strftime("%Y-%m")
            is_past = entry_date < NOW
            entry_status = "recognized" if is_past else "pending"
            recognized = monthly_amount_1 if is_past else 0
            recognized_total_1 += recognized

            db.add(RevenueScheduleEntry(
                schedule_id=sched1.id,
                period=period,
                amount=monthly_amount_1,
                recognized_amount=recognized,
                status=entry_status,
                recognized_at=entry_date if is_past else None,
            ))
        sched1.recognized_amount = recognized_total_1
        await db.flush()

        # Schedule 2: straight_line, 6 months, total 180000 (from contract[1])
        sched2 = RevenueSchedule(
            contract_id=contracts[1].id,
            recognition_type="straight_line",
            start_date=NOW - timedelta(days=90),
            end_date=NOW + timedelta(days=90),
            total_amount=180000,
            recognized_amount=0,
            currency="TRY",
            created_by=admin_id,
        )
        db.add(sched2)
        await db.flush()
        rev_schedules.append(sched2)

        monthly_amount_2 = round(180000 / 6, 2)
        recognized_total_2 = 0.0
        for month_offset in range(6):
            entry_date = NOW - timedelta(days=90) + timedelta(days=month_offset * 30)
            period = entry_date.strftime("%Y-%m")
            is_past = entry_date < NOW
            entry_status = "recognized" if is_past else "pending"
            recognized = monthly_amount_2 if is_past else 0
            recognized_total_2 += recognized

            db.add(RevenueScheduleEntry(
                schedule_id=sched2.id,
                period=period,
                amount=monthly_amount_2,
                recognized_amount=recognized,
                status=entry_status,
                recognized_at=entry_date if is_past else None,
            ))
        sched2.recognized_amount = recognized_total_2
        await db.flush()
        logger.info("Created %d revenue schedules with entries", len(rev_schedules))

        # ── 10. CHAT ──
        logger.info("Creating chat sessions and auto-response rules...")
        auto_rules_data = [
            ("fiyat", "Fiyat bilgisi icin satis temsilciniz sizinle iletisime gececektir.", 10),
            ("stok", "Stok durumu sorgunuz alinmistir. En kisa surede donecegiz.", 5),
            ("destek", "Teknik destek talebiniz olusturuldu. Referans no: #AUTO", 1),
        ]
        for keyword, response, priority in auto_rules_data:
            db.add(AutoResponseRule(
                trigger_keyword=keyword,
                response_text=response,
                is_active=True,
                priority=priority,
                created_by=admin_id,
            ))
        await db.flush()

        # Session 1: open
        session1 = ChatSession(
            visitor_id="visitor-001",
            assigned_agent_id=rep_id,
            status="open",
        )
        db.add(session1)
        await db.flush()

        msgs1 = [
            ("visitor", "visitor-001", "Merhaba, HW-SENS-001 urunun fiyati nedir?"),
            ("bot", None, "Fiyat bilgisi icin satis temsilciniz sizinle iletisime gececektir."),
            (
                "agent",
                str(rep_id),
                "Merhaba! HW-SENS-001 PT100 Sicaklik Sensoru liste fiyati 320 USD'dir. "
                "Adet miktarina gore indirim uygulanabilir.",
            ),
        ]
        for sender_type, sender_id, content in msgs1:
            db.add(ChatMessage(
                session_id=session1.id,
                sender_type=sender_type,
                sender_id=sender_id,
                content=content,
            ))
        await db.flush()

        # Session 2: closed
        session2 = ChatSession(
            visitor_id="visitor-002",
            status="closed",
        )
        db.add(session2)
        await db.flush()

        msgs2 = [
            ("visitor", "visitor-002", "Stok durumu hakkinda bilgi almak istiyorum"),
            ("bot", None, "Stok durumu sorgunuz alinmistir. En kisa surede donecegiz."),
        ]
        for sender_type, sender_id, content in msgs2:
            db.add(ChatMessage(
                session_id=session2.id,
                sender_type=sender_type,
                sender_id=sender_id,
                content=content,
            ))
        await db.flush()
        logger.info("Created 2 chat sessions, 5 messages, 3 auto-response rules")

        # ── 11. EMAIL TEMPLATES ──
        logger.info("Creating email templates...")
        template_defs = [
            (
                "Teklif Gonderim",
                "Teklif No: {{quote_number}} - {{customer_name}}",
                (
                    "<p>Sayin {{customer_name}},</p>"
                    "<p>{{quote_number}} numarali teklifiniz ekte sunulmustur.</p>"
                    "<p>Gecerlilik suresi: {{valid_days}} gun</p>"
                    "<p>Saygilarimizla,<br>Honeywell Satis Ekibi</p>"
                ),
                '["customer_name", "quote_number", "valid_days"]',
                "quote",
            ),
            (
                "Takip Maili",
                "Teklifiniz Hakkinda - {{customer_name}}",
                (
                    "<p>Sayin {{customer_name}},</p>"
                    "<p>{{days_ago}} gun once gonderdigimiz teklif hakkinda goruslerinizi almak istiyoruz.</p>"
                    "<p>Herhangi bir sorunuz varsa lutfen cekinmeden bize ulasin.</p>"
                    "<p>Saygilarimizla,<br>Honeywell Satis Ekibi</p>"
                ),
                '["customer_name", "days_ago"]',
                "follow_up",
            ),
            (
                "Hosgeldiniz",
                "Honeywell Ailesine Hosgeldiniz - {{customer_name}}",
                (
                    "<p>Sayin {{customer_name}},</p>"
                    "<p>Honeywell ailesine hosgeldiniz! Sizinle calismayi dort gozle bekliyoruz.</p>"
                    "<p>Satis temsilciniz: {{rep_name}}</p>"
                    "<p>Iletisim: {{rep_email}}</p>"
                    "<p>Saygilarimizla,<br>Honeywell Satis Ekibi</p>"
                ),
                '["customer_name", "rep_name", "rep_email"]',
                "onboarding",
            ),
        ]
        for name, subject, body, variables, category in template_defs:
            db.add(EmailTemplate(
                name=name,
                subject=subject,
                body_html=body,
                variables_json=variables,
                category=category,
                is_shared=True,
                created_by=admin_id,
            ))
        await db.flush()
        logger.info("Created 3 email templates")

        # ── 12. WORKFLOW RULES ──
        logger.info("Creating workflow rules...")
        wf_defs = [
            (
                "Yuksek Deger Firsat Bildirimi",
                "opportunity",
                "stage_change",
                json.dumps(
                    {"conditions": [{"field": "amount", "operator": "gt", "value": 100000}]},
                    ensure_ascii=False,
                ),
                json.dumps(
                    {"actions": [{"type": "notification", "target": "manager"}]},
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "nodes": [
                            {"id": "1", "type": "trigger", "label": "Asama Degisti"},
                            {"id": "2", "type": "condition", "label": "Tutar > 100K?"},
                            {"id": "3", "type": "action", "label": "Yoneticiye Bildir"},
                        ],
                        "edges": [
                            {"from": "1", "to": "2"},
                            {"from": "2", "to": "3", "label": "Evet"},
                        ],
                    },
                    ensure_ascii=False,
                ),
            ),
            (
                "Lead Skoru Yuksek Atama",
                "lead",
                "score_update",
                json.dumps(
                    {"conditions": [{"field": "lead_score", "operator": "gt", "value": 80}]},
                    ensure_ascii=False,
                ),
                json.dumps(
                    {"actions": [{"type": "assign", "target": "senior_rep"}]},
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "nodes": [
                            {"id": "1", "type": "trigger", "label": "Skor Guncellendi"},
                            {"id": "2", "type": "condition", "label": "Skor > 80?"},
                            {"id": "3", "type": "action", "label": "Kidemli Temsilciye Ata"},
                        ],
                        "edges": [
                            {"from": "1", "to": "2"},
                            {"from": "2", "to": "3", "label": "Evet"},
                        ],
                    },
                    ensure_ascii=False,
                ),
            ),
        ]
        for name, entity, trigger, cond, actions, flow in wf_defs:
            db.add(WorkflowRule(
                name=name,
                entity_type=entity,
                trigger_event=trigger,
                conditions_json=cond,
                actions_json=actions,
                flow_json=flow,
                is_active=True,
                created_by=admin_id,
            ))
        await db.flush()
        logger.info("Created 2 workflow rules")

        # ── 13. COMMENTS ──
        logger.info("Creating comments...")
        comment_defs = [
            (
                "opportunity",
                opps[0].id,
                rep_id,
                "Musteri ile gorusme yapildi, fiyat konusunda hassaslar. @admin dikkatine.",
                json.dumps([admin_id]),
            ),
            (
                "opportunity",
                opps[1].id,
                admin_id,
                "PLC upgrade projesi oncelikli. @rep lutfen bu hafta demo planla.",
                json.dumps([rep_id]),
            ),
            (
                "customer",
                customers[0].id,
                rep_id,
                "Anadolu Endustri yillik sozlesme yenileme gorusmesi yapilacak.",
                None,
            ),
            (
                "opportunity",
                opps[2].id,
                rep_id,
                "Sensor paketi icin alternatif urunler sunuldu. Karar bekleniyor.",
                None,
            ),
            (
                "customer",
                customers[4].id,
                admin_id,
                "Marmara HVAC bakim sozlesmesi detaylari icin @ops ile koordine olunmali.",
                json.dumps([ops_id]),
            ),
        ]
        for entity_type, entity_id, user_id, body, mentions in comment_defs:
            db.add(Comment(
                entity_type=entity_type,
                entity_id=entity_id,
                user_id=user_id,
                body=body,
                mentions_json=mentions,
            ))
        await db.flush()
        logger.info("Created 5 comments")

        # ── 14. ACHIEVEMENTS ──
        logger.info("Creating achievements...")
        achievement_defs = [
            (
                rep_id,
                "monthly_top",
                "Ayin Satiscisi",
                "Mart 2026 en yuksek satis hacmi",
                json.dumps({"month": "2026-03", "revenue": 485000}),
            ),
            (
                rep_id,
                "revenue_milestone",
                "100K Kulubu",
                "Tek bir firsatta 100.000 TRY ustu kapatti",
                json.dumps({"opportunity_id": opps[0].id, "amount": 125000}),
            ),
            (
                admin_id,
                "speed_champion",
                "Hiz Sampiyonu",
                "En hizli teklif-kapanma suresi (3 gun)",
                json.dumps({"days": 3, "quote_id": quotes[0].id}),
            ),
        ]
        for user_id, atype, title, desc, meta in achievement_defs:
            db.add(Achievement(
                user_id=user_id,
                achievement_type=atype,
                title=title,
                description=desc,
                metadata_json=meta,
                earned_at=NOW - timedelta(days=10),
            ))
        await db.flush()
        logger.info("Created 3 achievements")

        # ── 15. STAGE CONFIGS ──
        logger.info("Creating stage configs...")
        stage_config_defs = [
            ("prospecting", "Arastirma", 10, 7, 1),
            ("qualified", "Nitelendirme", 25, 14, 2),
            ("proposal", "Teklif", 50, 10, 3),
            ("negotiation", "Muzakere", 75, 7, 4),
            ("closed_won", "Kazanildi", 100, 0, 5),
            ("closed_lost", "Kaybedildi", 0, 0, 6),
        ]
        for stage_name, label, prob, rot_days, order in stage_config_defs:
            # Check if stage config already exists
            existing = (
                await db.execute(
                    select(StageConfig).where(StageConfig.stage_name == stage_name)
                )
            ).scalar_one_or_none()
            if not existing:
                db.add(StageConfig(
                    stage_name=stage_name,
                    label=label,
                    probability_pct=prob,
                    rotting_threshold_days=rot_days,
                    sort_order=order,
                    is_active=True,
                ))
        await db.flush()
        logger.info("Created stage configs")

        # ── COMMIT ──
        await db.commit()

        # ── SUMMARY ──
        logger.info("=" * 60)
        logger.info("UAT SEED DATA COMPLETE")
        logger.info("=" * 60)
        logger.info("  Campaigns:          %d (with %d members)", len(campaigns), member_count)
        logger.info("  Account Hierarchy:  3 parent-child links")
        logger.info("  Pipelines:          %d", len(pipelines))
        logger.info("  Territories:        5 (with 4 assignments)")
        logger.info("  Contracts:          %d", len(contracts))
        logger.info("  Invoices:           %d", len(invoices))
        logger.info("  Signatures:         3")
        logger.info("  Price Tiers:        %d", tier_count)
        logger.info("  Customer Pricing:   %d", cp_count)
        logger.info("  Revenue Schedules:  %d", len(rev_schedules))
        logger.info("  Chat Sessions:      2 (5 messages, 3 auto-rules)")
        logger.info("  Email Templates:    3")
        logger.info("  Workflow Rules:     2")
        logger.info("  Comments:           5")
        logger.info("  Achievements:       3")
        logger.info("  Stage Configs:      6")
        logger.info("=" * 60)
        logger.info("Run after seed_demo_data.py to have full UAT dataset.")


if __name__ == "__main__":
    asyncio.run(seed_uat())
