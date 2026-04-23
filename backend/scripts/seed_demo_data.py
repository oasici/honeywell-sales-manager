"""Seed demo data for Honeywell Sales Manager.

Run: cd backend && source venv/bin/activate && python -m scripts.seed_demo_data

Creates realistic demo data for all features:
- 3 users (admin, sales rep, operations)
- 10 customers
- 5 leads (various stages)
- 20 spare parts
- 15 quotes (various statuses)
- 5 opportunities
- Activity logs, notifications, etc.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
logger = logging.getLogger("seed")


async def seed():
    from app.core.database import async_session, engine, Base
    from app.core.security import hash_password
    from app.models.user import User
    from app.models.customer import Customer
    from app.models.spare_part import SparePart
    from app.models.price_entry import PriceEntry
    from app.models.quote import Quote
    from app.models.quote_item import QuoteItem
    from app.models.email_request import EmailRequest
    from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal, Task
    from app.models.lead import Lead
    from app.models.activity_log import ActivityLog
    from app.models.notification import Notification

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        from sqlalchemy import select, func

        # Check if already seeded
        count = (await db.execute(select(func.count(User.id)))).scalar()
        if count and count > 1:
            logger.info("Database already has data (%d users). Skipping seed.", count)
            return

        # Use naive UTC datetimes for PostgreSQL compatibility with mixed model definitions
        now = datetime.utcnow()

        # ── USERS ──
        logger.info("Creating users...")

        # Admin already created by lifespan — find it
        admin_result = await db.execute(select(User).where(User.email == "admin@honeywell.com"))
        admin_user = admin_result.scalar_one_or_none()
        if admin_user:
            admin_id = admin_user.id
            # Update name for demo
            admin_user.full_name = "Ahmet Yilmaz"
            admin_user.email_setup_completed = True
            admin_user.password_change_required = False
        else:
            admin = User(
                email="admin@honeywell.com", full_name="Ahmet Yilmaz",
                hashed_password=hash_password("Admin123!"),
                role="sales_manager", is_active=True, email_setup_completed=True,
            )
            db.add(admin)
            await db.flush()
            admin_id = admin.id

        # Create rep and ops users (skip if exist)
        for email, name, pwd, role in [
            ("rep@honeywell.com", "Elif Kaya", "Rep12345", "sales_rep"),
            ("ops@honeywell.com", "Mehmet Demir", "Ops12345", "operations"),
        ]:
            existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if not existing:
                u = User(
                    email=email, full_name=name, hashed_password=hash_password(pwd),
                    role=role, is_active=True, email_setup_completed=True,
                )
                db.add(u)
        await db.flush()

        rep_result = (await db.execute(select(User).where(User.email == "rep@honeywell.com"))).scalar_one()
        ops_result = (await db.execute(select(User).where(User.email == "ops@honeywell.com"))).scalar_one()
        rep_id, ops_id = rep_result.id, ops_result.id

        # Set manager hierarchy: rep and ops report to admin
        rep_result.manager_id = admin_id
        ops_result.manager_id = admin_id
        await db.flush()

        logger.info("Users ready (admin=%d, rep=%d, ops=%d)", admin_id, rep_id, ops_id)

        # ── CUSTOMERS ──
        logger.info("Creating customers...")
        customer_data = [
            ("Anadolu Endustri A.S.", "Anadolu", "satis@anadoluendustri.com.tr", "+90 212 555 0101", "Istanbul, Ikitelli OSB"),
            ("Ege Mekatronik Ltd.", "Ege Mekatronik", "info@egemekatronik.com", "+90 232 555 0202", "Izmir, Cigli"),
            ("Karadeniz Otomasyon", "Karadeniz Oto", "siparis@karadenizoto.com.tr", "+90 462 555 0303", "Trabzon, Organize Sanayi"),
            ("Ankara Teknik Servis", "Ankara Teknik", "destek@ankarateknik.com.tr", "+90 312 555 0404", "Ankara, OSTiM"),
            ("Marmara HVAC Systems", "Marmara HVAC", "purchasing@marmarahvac.com", "+90 216 555 0505", "Istanbul, Tuzla"),
            ("Akdeniz Proses", "Akdeniz Proses", "tedarik@akdenizproses.com.tr", "+90 242 555 0606", "Antalya"),
            ("Trakya Endustriyel", "Trakya End.", "satis@trakyaend.com.tr", "+90 284 555 0707", "Edirne"),
            ("GAP Muhendislik", "GAP Muh.", "proje@gapmuh.com.tr", "+90 414 555 0808", "Sanliurfa"),
            ("Bolu Termal Sistemler", "Bolu Termal", "info@bolutermal.com", "+90 374 555 0909", "Bolu"),
            ("Kocaeli Filtre San.", "Kocaeli Filtre", "siparis@kocaelifiltre.com.tr", "+90 262 555 1010", "Kocaeli, Gebze"),
        ]
        customers = []
        for name, company, email, phone, address in customer_data:
            c = Customer(name=name, company=company, email=email, phone=phone, address=address, created_by=rep_id)
            db.add(c)
            customers.append(c)
        await db.flush()
        logger.info("Created %d customers", len(customers))

        # ── SPARE PARTS ──
        logger.info("Creating spare parts...")
        parts_data = [
            ("HW-VALVE-001", "Control Valve DN50", "Kontrol Vanasi DN50", "Valves", "Control", 850.0, 620.0),
            ("HW-VALVE-002", "Safety Relief Valve", "Emniyet Tahliye Vanasi", "Valves", "Safety", 1200.0, 880.0),
            ("HW-SENS-001", "Temperature Sensor PT100", "Sicaklik Sensoru PT100", "Sensors", "Temperature", 320.0, 210.0),
            ("HW-SENS-002", "Pressure Transmitter 4-20mA", "Basinc Transmitteri", "Sensors", "Pressure", 1450.0, 980.0),
            ("HW-SENS-003", "Humidity Sensor", "Nem Sensoru", "Sensors", "Humidity", 580.0, 390.0),
            ("HW-CTRL-001", "PLC Controller HC900", "PLC Kontrolor HC900", "Controllers", "PLC", 4500.0, 3200.0),
            ("HW-CTRL-002", "DCS Module C300", "DCS Modul C300", "Controllers", "DCS", 8200.0, 5800.0),
            ("HW-FILT-001", "Air Filter Panel 20x20", "Hava Filtresi Panel 20x20", "Filters", "Air", 95.0, 55.0),
            ("HW-FILT-002", "HEPA Filter H13", "HEPA Filtre H13", "Filters", "HEPA", 340.0, 220.0),
            ("HW-FILT-003", "Oil Filter Cartridge", "Yag Filtresi Kartus", "Filters", "Oil", 180.0, 110.0),
            ("HW-ACTU-001", "Pneumatic Actuator", "Pnomatik Aktuator", "Actuators", "Pneumatic", 2100.0, 1500.0),
            ("HW-ACTU-002", "Electric Actuator 24V", "Elektrik Aktuator 24V", "Actuators", "Electric", 2800.0, 1950.0),
            ("HW-THER-001", "Thermostat T6360", "Termostat T6360", "Thermostats", "Room", 125.0, 75.0),
            ("HW-THER-002", "Digital Thermostat T9", "Dijital Termostat T9", "Thermostats", "Smart", 450.0, 310.0),
            ("HW-DET-001", "Smoke Detector System", "Duman Dedektoru Sistemi", "Detectors", "Smoke", 680.0, 450.0),
            ("HW-DET-002", "Gas Detector XCD", "Gaz Dedektoru XCD", "Detectors", "Gas", 3200.0, 2300.0),
            ("HW-CAL-001", "Calibrator MC5", "Kalibrator MC5", "Calibration", "Portable", 5500.0, 3900.0),
            ("HW-FLOW-001", "Flow Meter Versaflow", "Debi Olcer Versaflow", "Flow", "Coriolis", 7800.0, 5500.0),
            ("HW-REC-001", "Paperless Recorder", "Kagitsiz Kaydedici", "Recorders", "Paperless", 3600.0, 2500.0),
            ("HW-ANAL-001", "Gas Analyzer", "Gaz Analizoru", "Analyzers", "Gas", 12000.0, 8500.0),
        ]
        parts = []
        for code, name_en, name_tr, cat, subcat, transfer, supplier in parts_data:
            p = SparePart(
                honeywell_code=code, name_en=name_en, name_tr=name_tr,
                category=cat, subcategory=subcat,
                transfer_price=transfer, supplier_price=supplier,
                price_currency="USD", is_active=True,
            )
            db.add(p)
            parts.append(p)
        await db.flush()

        # Price entries
        for p in parts:
            db.add(PriceEntry(
                spare_part_id=p.id, list_price=p.transfer_price * 1.4,
                discount_pct=0, net_price=p.transfer_price * 1.4,
                currency="USD", price_list_version="2026-Q1",
            ))
        await db.flush()
        logger.info("Created %d spare parts with prices", len(parts))

        # ── OPPORTUNITIES ──
        logger.info("Creating opportunities...")
        # 20 opportunities with mixed stages + some won/lost samples
        opp_templates = [
            "HVAC Yenileme",
            "PLC Upgrade",
            "Sensor Paketi",
            "Yillik Bakim",
            "Proses Otomasyon",
            "Filtrasyon Hatti",
            "DCS Modernizasyon",
            "Saha Servis Kontrati",
            "Enerji Optimizasyon",
            "Gaz Analizor Bakimi",
        ]
        stage_pool = (
            ["prospecting"] * 4
            + ["qualified"] * 5
            + ["proposal"] * 5
            + ["negotiation"] * 4
            + ["closed_won"] * 1
            + ["closed_lost"] * 1
        )
        opps = []
        for i in range(20):
            cust = random.choice(customers)
            stage = stage_pool[i % len(stage_pool)]
            owner_id = rep_id if i % 3 != 0 else admin_id
            amount = random.choice([18000, 42000, 85000, 125000, 200000, 350000, 520000])
            title = f"{cust.company} - {random.choice(opp_templates)}"
            o = Opportunity(
                title=title,
                stage=stage,
                amount=amount,
                currency="TRY",
                customer_id=cust.id,
                owner_id=owner_id,
                close_date=(now + timedelta(days=random.randint(7, 90))).date(),
                forecast_category=random.choice(["pipeline", "best_case", "commit"]),
            )
            if stage in ("closed_won", "closed_lost"):
                o.status = "closed"
            db.add(o)
            opps.append(o)
        await db.flush()

        # Opportunity events (timeline-rich)
        for o in opps:
            db.add(
                OpportunityEvent(
                    opportunity_id=o.id,
                    event_type="stage_change",
                    description=f"Firsat olusturuldu: {o.stage}",
                )
            )
            db.add(
                OpportunityEvent(
                    opportunity_id=o.id,
                    event_type="note",
                    description=random.choice(
                        [
                            "Musteri fiyat hassasiyeti belirtti.",
                            "Teknik sartname bekleniyor.",
                            "Rakip X firmasi devrede.",
                            "Toplanti sonrasi aksiyonlar belirlendi.",
                        ]
                    ),
                )
            )
        await db.flush()

        # Signals
        signal_types = [
            "pricing_concern",
            "competitor",
            "objection",
            "no_touch",
            "discount_risk",
            "sla_breach",
            "positive",
        ]
        for o in opps:
            for _ in range(random.randint(0, 3)):
                db.add(
                    OpportunitySignal(
                        opportunity_id=o.id,
                        signal_type=random.choice(signal_types),
                        severity=random.choice(["low", "med", "high"]),
                        evidence="Demo sinyal verisi",
                        source_type=random.choice(["ai", "email", "quote"]),
                        is_resolved=random.choice([False, False, True]),
                    )
                )
        await db.flush()

        # Tasks
        for o in opps:
            for _ in range(random.randint(1, 3)):
                db.add(
                    Task(
                        owner_id=o.owner_id,
                        opportunity_id=o.id,
                        title=random.choice(
                            [
                                "Musteri ile follow-up aramasi",
                                "Teklif revizyonu hazirla",
                                "Rakip karsilastirma notu",
                                "Teknik demo planla",
                            ]
                        ),
                        description="Demo task",
                        due_at=(datetime.now(timezone.utc) + timedelta(days=random.randint(1, 14))),
                        status=random.choice(["open", "open", "done"]),
                        source=random.choice(["manual", "rule", "ai"]),
                        priority=random.choice(["low", "normal", "high"]),
                    )
                )
        await db.flush()
        logger.info("Created %d opportunities with events and signals", len(opps))

        # ── QUOTES ──
        logger.info("Creating quotes...")
        statuses = ["draft", "draft", "pending_approval", "approved", "approved", "sent", "sent", "accepted", "rejected"]
        quotes = []
        for i in range(15):
            cust = random.choice(customers)
            opp = random.choice(opps) if i < 5 else None
            q = Quote(
                quote_number=f"QT-2026-{1000+i:06d}",
                customer_id=cust.id,
                created_by=rep_id if i % 2 == 0 else admin_id,
                status=statuses[i % len(statuses)],
                language="tr",
                currency="TRY",
                tax_rate=20.0,
                valid_days=30,
                opportunity_id=opp.id if opp else None,
                notes=f"Demo teklif #{i+1}",
            )
            db.add(q)
            quotes.append(q)
        await db.flush()

        # Quote items
        for q in quotes:
            num_items = random.randint(1, 4)
            subtotal = 0
            for j in range(num_items):
                part = random.choice(parts)
                qty = random.randint(1, 10)
                price = (part.transfer_price or 100) * 1.3
                discount = random.choice([0, 5, 10, 15])
                line_total = qty * price * (1 - discount / 100)
                subtotal += line_total
                db.add(QuoteItem(
                    quote_id=q.id, spare_part_id=part.id,
                    honeywell_code=part.honeywell_code,
                    description=part.name_tr or part.name_en,
                    quantity=qty, unit_price=price,
                    discount_pct=discount, line_total=line_total,
                    match_score=random.uniform(75, 100),
                    match_strategy=random.choice(["exact_code", "fuzzy_code", "semantic"]),
                    is_confirmed=True, sort_order=j,
                ))
            q.subtotal = subtotal
            q.tax_amount = subtotal * q.tax_rate / 100
            q.grand_total = subtotal + q.tax_amount
        await db.flush()
        logger.info("Created %d quotes with items", len(quotes))

        # ── LEADS ──
        logger.info("Creating leads...")
        lead_data = [
            ("Burak", "Ozturk", "burak@potansiyelmusteri.com", "Potansiyel A.S.", "new", 45),
            ("Selin", "Arslan", "selin@yeniproje.com.tr", "Yeni Proje Ltd.", "contacted", 62),
            ("Can", "Tekin", "can.tekin@sanayici.com", "Sanayici Grup", "qualified", 78),
            ("Zeynep", "Celik", "zeynep@hvacpro.com.tr", "HVAC Pro", "qualified", 85),
            ("Emre", "Sahin", "emre@eskimusteri.com", None, "unqualified", 20),
        ]
        for first, last, email, company, status, score in lead_data:
            db.add(Lead(
                first_name=first, last_name=last, email=email,
                company=company, source="manual", status=status,
                lead_score=score, owner_id=rep_id,
            ))
        await db.flush()
        logger.info("Created 5 leads")

        # ── EMAIL REQUESTS ──
        logger.info("Creating email requests...")
        for i in range(8):
            cust = random.choice(customers)
            db.add(EmailRequest(
                customer_id=cust.id,
                message_id=f"demo-msg-{i+1}@mail.example.com",
                from_address=cust.email,
                subject=f"Yedek parca talebi - {cust.company}",
                body_text=f"Merhabalar, {random.choice(parts).honeywell_code} urununden {random.randint(1,5)} adet ihtiyacimiz var.",
                status=random.choice(["new", "parsed", "quoted"]),
                category="spare_part_request",
                category_confidence=random.uniform(0.7, 0.98),
                review_status=random.choice(["pending_review", "approved"]),
                assigned_to=rep_id,
            ))
        await db.flush()
        logger.info("Created 8 email requests")

        # ── ACTIVITY LOGS ──
        for i in range(20):
            db.add(ActivityLog(
                activity_type=random.choice(["quote_created", "quote_approved", "email_parsed", "stage_change"]),
                entity_type=random.choice(["quote", "email", "opportunity"]),
                entity_id=random.randint(1, 15),
                opportunity_id=random.choice(opps).id if random.random() > 0.3 else None,
                customer_id=random.choice(customers).id,
                user_id=random.choice([admin_id, rep_id]),
                summary=f"Demo aktivite #{i+1}",
                created_at=now - timedelta(days=random.randint(0, 30)),
            ))
        await db.flush()

        # ── TASKS ──
        for opp in opps[:3]:
            db.add(Task(
                owner_id=rep_id, opportunity_id=opp.id,
                title=f"{opp.title} - Takip görüsmesi",
                status=random.choice(["open", "done"]),
                priority=random.choice(["normal", "high"]),
                source="manual",
            ))
        await db.flush()

        # ── NOTIFICATIONS ──
        for i in range(5):
            db.add(Notification(
                user_id=rep_id,
                type=random.choice(["quote_approved", "email_reviewed", "anomaly_alert"]),
                title=f"Demo bildirim #{i+1}",
                message="Bu bir demo bildirimidir.",
                is_read=i > 2,
            ))
        await db.flush()

        await db.commit()
        logger.info("Seed data complete!")
        logger.info("Login credentials:")
        logger.info("  Admin: admin@honeywell.com / Admin123!")
        logger.info("  Rep:   rep@honeywell.com / Rep12345")
        logger.info("  Ops:   ops@honeywell.com / Ops12345")


if __name__ == "__main__":
    asyncio.run(seed())
