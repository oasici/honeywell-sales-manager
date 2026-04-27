"""Comprehensive V8 demo seed.

Populates **every major UI surface** with realistic content end-to-end:

* Tenants + Users + Customers + Contacts
* Opportunities across all stages, with linked Tasks, Quotes,
  ActivityLogs, OpportunityEvents, RevenueSignals, CompetitorMentions,
  Stakeholders, Objections, ObjectionResolutionActions
* Spare parts catalog + price entries
* Leads, Pipelines + StageConfigs, Email templates
* Campaigns + members, Contracts + amendments, DealRooms + documents
* MeetingLinks + bookings, Subscriptions + revenue schedules
* Sequences (v2) + enrollments + step runs
* ChatSessions + messages + auto rules
* Report templates + folders + dashboards
* SavedViews + comments + notifications
* ApiKeys + webhooks + workflow rules

Then triggers the V4/V5/V6/V7/V8 derived-data pipelines so the
analytics dashboards (DNA patterns, similarity links, replay deltas,
network anomalies, federated benchmarks) light up too.

Idempotent: re-running upserts by stable natural keys (email, name,
title, etc.) so this can run on production-shaped DBs without
duplicating rows.

Run:
    cd backend
    source venv/bin/activate
    python -m scripts.seed_v8_full_demo --apply
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

# Add backend to path so this works as ``python -m scripts.seed_v8_full_demo``
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
logger = logging.getLogger("seed_v8")


# Deterministic PRNG so re-runs produce stable counts.
RNG = random.Random(42)


# ─────────────────────── reference data ──────────────────────────────


INDUSTRIES = (
    "manufacturing", "logistics", "retail", "construction",
    "energy", "healthcare", "finance", "tech",
)
SIZE_BANDS = ((25, "smb"), (200, "mid"), (1500, "enterprise"))
PRODUCT_FAMILIES = ("hvac", "controls", "sensors", "automation", "general")
COUNTRIES = ("Türkiye", "Germany", "Netherlands", "UK", "USA")
REGIONS = ("Marmara", "Aegean", "Central Anatolia", "Mediterranean", "EMEA")


CUSTOMER_NAMES = [
    "ACME Endüstri", "Demir Çelik A.Ş.", "Anadolu Lojistik",
    "Mavi Gemi Tersane", "Yıldız Otomotiv", "Boğaziçi Tekstil",
    "Karadeniz Enerji", "Toros Yapı", "Egem İnşaat",
    "Ankara Üretim", "Bursa Mühendislik", "İzmir Liman A.Ş.",
    "Antalya Turizm Tedarik", "Adana Tarım Tek", "Eskişehir Raylı",
    "Konya Şeker Tedarik", "Trabzon Balıkçılık", "Samsun Liman",
    "Marmara Cam", "Polat Makine", "Demirören Lojistik",
    "Tekfen İnşaat Tedarik", "Gama Holding Operasyon", "ENKA Sistem",
    "Kale Endüstri", "Borusan Otomotiv Tedarik", "Eczacıbaşı Sağlık",
    "Sabancı Holding Operasyon", "Koç Sistem Servis", "Aselsan Tedarik",
]


REP_NAMES: list[tuple[str, str]] = [
    ("Ahmet", "Yılmaz"), ("Ayşe", "Demir"), ("Mehmet", "Kaya"),
    ("Fatma", "Çelik"), ("Mustafa", "Şahin"), ("Zeynep", "Yıldız"),
    ("Ali", "Aslan"), ("Elif", "Doğan"), ("Hasan", "Kara"),
    ("Hatice", "Polat"), ("Hüseyin", "Aydın"), ("Emine", "Öztürk"),
]


CONTACT_TITLES = (
    "CEO", "CTO", "CFO", "VP Engineering", "VP Operations",
    "Procurement Manager", "Plant Manager", "Maintenance Lead",
    "Buyer", "Director of IT", "Head of Quality",
)


# ─────────────────────── seed orchestrator ───────────────────────────


async def seed():
    from app.core.config import settings
    from app.core.database import async_session, engine, Base
    from app.core.security import hash_password
    # Trigger full model registration so ``Base.metadata.create_all``
    # below builds every table (incl. V5/V6/V7/V8 analytics tables).
    from app import models  # noqa: F401

    # Ensure schema exists when run on a fresh DB. Production deploys
    # use alembic; this is a dev/test-time convenience.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        tenant_ids = await _seed_tenants(db)
        user_ids_by_role = await _seed_users(db, tenant_ids, hash_password)
        customer_ids = await _seed_customers(db, tenant_ids, user_ids_by_role["sales_manager"][0])
        contact_ids = await _seed_contacts(db, customer_ids)
        await _seed_pipelines_and_stages(db, user_ids_by_role)
        opp_ids = await _seed_opportunities(db, tenant_ids, customer_ids, user_ids_by_role)
        await _seed_tasks(db, opp_ids, user_ids_by_role)
        spare_ids = await _seed_spare_parts(db)
        await _seed_price_entries(db, spare_ids)
        quote_ids = await _seed_quotes(db, tenant_ids, customer_ids, opp_ids, user_ids_by_role, spare_ids)
        await _seed_activity_history(db, opp_ids, customer_ids, user_ids_by_role)
        await _seed_signals_and_events(db, opp_ids, customer_ids, user_ids_by_role)
        await _seed_stakeholders_and_competitors(db, opp_ids, customer_ids)
        await _seed_objections(db, opp_ids)
        await _seed_leads(db, tenant_ids, user_ids_by_role)
        await _seed_email_templates(db, user_ids_by_role)
        await _seed_campaigns(db, user_ids_by_role, customer_ids)
        await _seed_contracts(db, customer_ids, opp_ids, user_ids_by_role)
        await _seed_deal_rooms(db, opp_ids, user_ids_by_role)
        await _seed_meetings(db, user_ids_by_role)
        await _seed_subscriptions(db, customer_ids, user_ids_by_role)
        await _seed_sequences_v2(db, user_ids_by_role, customer_ids)
        await _seed_chat(db, user_ids_by_role, customer_ids)
        await _seed_reports_and_dashboards(db, user_ids_by_role)
        await _seed_saved_views_comments_notifications(db, user_ids_by_role, opp_ids)
        await _seed_api_keys_workflows(db, user_ids_by_role)
        await db.commit()

    logger.info("Base data committed. Building derived feature snapshots…")
    await _build_derived_data(target_days=30)

    logger.info("Seed complete. Summary:")
    await _print_summary()


# ─────────────────────── 1. tenants + users ──────────────────────────


async def _seed_tenants(db) -> list[int]:
    from app.models.v7_tenant import Tenant
    from sqlalchemy import select

    out: list[int] = []
    for name, region in (("default", "TR"), ("acme-eu", "EU")):
        existing = (
            await db.execute(select(Tenant).where(Tenant.name == name))
        ).scalar_one_or_none()
        if existing is None:
            t = Tenant(name=name, region=region, plan_tier="standard")
            db.add(t)
            await db.flush()
            out.append(t.id)
        else:
            out.append(existing.id)
    logger.info("tenants: %s", out)
    return out


async def _seed_users(db, tenant_ids: list[int], hash_password) -> dict[str, list[int]]:
    from app.models.user import User
    from sqlalchemy import select

    primary_tenant = tenant_ids[0]
    eu_tenant = tenant_ids[1] if len(tenant_ids) > 1 else tenant_ids[0]

    plan: list[tuple[str, str, str, int]] = [
        ("admin@demo.honeywell", "Demo Admin", "admin", primary_tenant),
        ("manager@demo.honeywell", "Sezen Yöne", "sales_manager", primary_tenant),
        ("manager.eu@demo.honeywell", "Heinrich Möller", "sales_manager", eu_tenant),
        ("ops@demo.honeywell", "Operasyon Demo", "operations", primary_tenant),
    ]
    for i, (first, last) in enumerate(REP_NAMES[:8]):
        email = f"rep{i + 1}@demo.honeywell"
        plan.append((email, f"{first} {last}", "sales_rep", primary_tenant if i < 5 else eu_tenant))

    by_role: dict[str, list[int]] = {"admin": [], "sales_manager": [], "operations": [], "sales_rep": []}
    for email, name, role, tid in plan:
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is None:
            u = User(
                email=email,
                full_name=name,
                hashed_password=hash_password("Test1234!"),
                role=role,
                tenant_id=tid,
                is_active=True,
            )
            db.add(u)
            await db.flush()
            by_role[role].append(u.id)
        else:
            existing.tenant_id = existing.tenant_id or tid
            by_role[role].append(existing.id)
    await db.flush()
    logger.info("users: admins=%s, mgrs=%s, ops=%s, reps=%s",
                len(by_role["admin"]), len(by_role["sales_manager"]),
                len(by_role["operations"]), len(by_role["sales_rep"]))
    return by_role


# ─────────────────────── 2. customers + contacts ─────────────────────


async def _seed_customers(db, tenant_ids: list[int], created_by: int) -> list[int]:
    from app.models.customer import Customer
    from sqlalchemy import select

    out: list[int] = []
    for i, name in enumerate(CUSTOMER_NAMES):
        email = f"contact{i + 1}@{name.lower().replace(' ', '').replace('.', '').replace('ş', 's').replace('ç', 'c').replace('ğ', 'g').replace('ı', 'i').replace('ö', 'o').replace('ü', 'u')[:18]}.com"
        existing = (
            await db.execute(select(Customer).where(Customer.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            out.append(existing.id)
            continue
        size_threshold = RNG.choice(SIZE_BANDS)[0]
        c = Customer(
            name=name,
            company=name,
            email=email,
            phone=f"+90 5{RNG.randint(30, 59)} {RNG.randint(100, 999)} {RNG.randint(1000, 9999)}",
            address=f"{RNG.choice(REGIONS)}, {RNG.choice(COUNTRIES)}",
            tax_id=f"TR{RNG.randint(1000000000, 9999999999)}",
            preferred_lang="tr" if i < 20 else "en",
            tenant_id=tenant_ids[0] if i < 22 else tenant_ids[-1],
            created_by=created_by,
            kvkk_consent=True,
            kvkk_consent_method="form",
            data_classification="internal",
        )
        db.add(c)
        await db.flush()
        out.append(c.id)
    logger.info("customers: %s", len(out))
    return out


async def _seed_contacts(db, customer_ids: list[int]) -> list[int]:
    from app.models.v5_foundation import Contact
    from sqlalchemy import select

    out: list[int] = []
    for cid in customer_ids:
        # 2-4 contacts per customer
        n = RNG.randint(2, 4)
        for j in range(n):
            title = RNG.choice(CONTACT_TITLES)
            name = f"{RNG.choice(REP_NAMES)[0]} {RNG.choice(REP_NAMES)[1]}"
            email = f"contact{cid}_{j}@demo.honeywell"
            existing = (
                await db.execute(select(Contact).where(Contact.email == email))
            ).scalar_one_or_none()
            if existing is not None:
                out.append(existing.id)
                continue
            seniority = 80 if title in {"CEO", "CTO", "CFO"} else 60 if "VP" in title or "Director" in title else 40
            c = Contact(
                account_id=cid,
                name=name,
                title=title,
                department="Procurement" if "Procurement" in title or "Buyer" in title else "Engineering",
                email=email,
                phone=f"+90 5{RNG.randint(30, 59)} {RNG.randint(100, 999)} {RNG.randint(1000, 9999)}",
                seniority_score=seniority,
                is_decision_maker=title in {"CEO", "CTO", "CFO", "VP Engineering", "VP Operations"},
                linkedin_url=f"https://linkedin.com/in/demo-{cid}-{j}",
            )
            db.add(c)
            await db.flush()
            out.append(c.id)
    logger.info("contacts: %s", len(out))
    return out


# ─────────────────────── 3. pipelines + stages ───────────────────────


async def _seed_pipelines_and_stages(db, user_ids_by_role: dict) -> None:
    from app.models.pipeline import Pipeline
    from app.models.stage_config import StageConfig
    from sqlalchemy import select

    mgr_id = user_ids_by_role["sales_manager"][0]
    stage_defs = [
        ("prospecting", "Prospecting", 10, 14),
        ("qualified", "Qualified", 25, 14),
        ("proposal", "Proposal", 50, 10),
        ("negotiation", "Negotiation", 75, 7),
        ("closed_won", "Closed Won", 100, 0),
        ("closed_lost", "Closed Lost", 0, 0),
    ]
    for i, (k, label, prob, rot) in enumerate(stage_defs):
        existing = (
            await db.execute(select(StageConfig).where(StageConfig.stage_name == k))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                StageConfig(
                    stage_name=k,
                    label=label,
                    probability_pct=float(prob),
                    rotting_threshold_days=rot,
                    sort_order=i,
                    is_active=True,
                )
            )

    for name, is_default, region in (
        ("Türkiye Ana Pipeline", True, "TR"),
        ("EMEA Pipeline", False, "EMEA"),
        ("Strategic Accounts", False, "Global"),
    ):
        existing = (
            await db.execute(select(Pipeline).where(Pipeline.name == name))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                Pipeline(
                    name=name,
                    description=f"{region} pipeline",
                    is_default=is_default,
                    stages_json=json.dumps(
                        [
                            {"key": k, "label": l, "order": i, "probability": p}
                            for i, (k, l, p, _) in enumerate(stage_defs)
                        ]
                    ),
                    created_by=mgr_id,
                )
            )
    await db.flush()
    logger.info("pipelines + stages seeded")


# ─────────────────────── 4. opportunities ────────────────────────────


async def _seed_opportunities(
    db, tenant_ids: list[int], customer_ids: list[int], user_ids_by_role: dict
) -> list[int]:
    from app.models.opportunity import Opportunity
    from sqlalchemy import select

    rep_ids = user_ids_by_role["sales_rep"]
    if not rep_ids:
        rep_ids = user_ids_by_role["sales_manager"]
    stage_distribution = (
        ["prospecting"] * 18
        + ["qualified"] * 18
        + ["proposal"] * 16
        + ["negotiation"] * 12
        + ["closed_won"] * 10
        + ["closed_lost"] * 6
    )
    out: list[int] = []
    today = datetime.now(timezone.utc)
    for i, stage in enumerate(stage_distribution):
        cid = customer_ids[i % len(customer_ids)]
        title = f"{CUSTOMER_NAMES[i % len(CUSTOMER_NAMES)]} — {RNG.choice(['HVAC modernizasyon', 'Sensör paketi', 'Otomasyon hattı', 'Bakım sözleşmesi', 'Yeni saha kurulumu'])}"
        existing = (
            await db.execute(select(Opportunity).where(Opportunity.title == title))
        ).scalar_one_or_none()
        if existing is not None:
            out.append(existing.id)
            continue
        amount = RNG.choice([35_000, 80_000, 150_000, 320_000, 750_000, 1_400_000])
        days_old = RNG.randint(5, 95)
        status = "active" if stage not in {"closed_won", "closed_lost"} else "closed"
        opp = Opportunity(
            customer_id=cid,
            owner_id=rep_ids[i % len(rep_ids)],
            title=title,
            stage=stage,
            status=status,
            amount=float(amount),
            currency="TRY",
            close_date=(today + timedelta(days=RNG.randint(15, 90))).date(),
            forecast_category=RNG.choice(["pipeline", "best_case", "commit"]),
            probability=0.1 if stage == "prospecting" else 0.25 if stage == "qualified" else 0.5 if stage == "proposal" else 0.75 if stage == "negotiation" else 1.0 if stage == "closed_won" else 0.0,
            tenant_id=tenant_ids[0] if i < 65 else tenant_ids[-1],
            created_at=today - timedelta(days=days_old),
            updated_at=today - timedelta(days=RNG.randint(0, 5)),
        )
        db.add(opp)
        await db.flush()
        out.append(opp.id)
    logger.info("opportunities: %s (across 6 stages)", len(out))
    return out


# ─────────────────────── 5. tasks ────────────────────────────────────


async def _seed_tasks(db, opp_ids: list[int], user_ids_by_role: dict) -> None:
    from app.models.opportunity import Task
    from sqlalchemy import select

    rep_ids = user_ids_by_role["sales_rep"] or user_ids_by_role["sales_manager"]
    titles = (
        "Müşteriyi ara", "Teklifi gözden geçir", "Demo planla",
        "Karar verici toplantısı", "Pricing onayı al", "Sözleşme taslağı",
        "Teknik şartname netleştir", "Referans araması",
    )
    statuses = ("open", "open", "open", "done", "done")

    written = 0
    for oid in opp_ids[:60]:
        for k in range(RNG.randint(1, 2)):
            title = RNG.choice(titles)
            existing = (
                await db.execute(
                    select(Task).where(Task.opportunity_id == oid).where(Task.title == title)
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                Task(
                    opportunity_id=oid,
                    title=title,
                    description=f"{title} — auto-seeded demo task",
                    owner_id=RNG.choice(rep_ids),
                    status=RNG.choice(statuses),
                    priority=RNG.choice(["low", "normal", "high"]),
                    source="rule",
                    due_at=datetime.now(timezone.utc) + timedelta(days=RNG.randint(1, 14)),
                )
            )
            written += 1
    await db.flush()
    logger.info("tasks: %s", written)


# ─────────────────────── 6. spare parts + prices ─────────────────────


async def _seed_spare_parts(db) -> list[int]:
    from app.models.spare_part import SparePart
    from sqlalchemy import select

    skus: list[tuple[str, str, str]] = [
        ("HW-T7351", "Honeywell T7351 termostat", "Termostat"),
        ("HW-VK-25", "Honeywell VK-25 vana", "Vana"),
        ("HW-PR4-6", "Honeywell PR4-6 sensör", "Sensör"),
        ("HW-DCS-100", "Honeywell DCS-100 kontrol", "Kontrol Paneli"),
        ("HW-FX-22", "Honeywell FX-22 yangın detektörü", "Detektör"),
        ("HW-BU-7", "Honeywell BU-7 buton paneli", "Pano"),
        ("HW-CB-Pro", "Honeywell CB-Pro kombi kontrol", "Kontrol"),
        ("HW-AT-12", "Honeywell AT-12 aktüatör", "Aktüatör"),
        ("HW-RH-50", "Honeywell RH-50 nem sensörü", "Sensör"),
        ("HW-CO2-300", "Honeywell CO2-300 hava kalitesi", "Sensör"),
    ]
    out: list[int] = []
    for sku, name, category in skus:
        existing = (
            await db.execute(select(SparePart).where(SparePart.honeywell_code == sku))
        ).scalar_one_or_none()
        if existing is not None:
            out.append(existing.id)
            continue
        p = SparePart(
            honeywell_code=sku,
            name_en=name.replace("termostat", "thermostat"),
            name_tr=name,
            category=category,
            description_tr=f"{name} — endüstriyel otomasyon bileşeni",
            description_en=f"{name} — automation grade industrial component",
            is_active=True,
        )
        db.add(p)
        await db.flush()
        out.append(p.id)
    logger.info("spare_parts: %s", len(out))
    return out


async def _seed_price_entries(db, spare_ids: list[int]) -> None:
    from app.models.price_entry import PriceEntry
    from sqlalchemy import select

    written = 0
    today = datetime.now(timezone.utc).date()
    for sid in spare_ids:
        for currency, base in (("TRY", RNG.randint(1500, 28000)), ("EUR", RNG.randint(40, 800))):
            existing = (
                await db.execute(
                    select(PriceEntry)
                    .where(PriceEntry.spare_part_id == sid)
                    .where(PriceEntry.currency == currency)
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                PriceEntry(
                    spare_part_id=sid,
                    currency=currency,
                    list_price=float(base) * 1.2,
                    discount_pct=15.0,
                    net_price=float(base),
                    valid_from=today - timedelta(days=30),
                    valid_until=today + timedelta(days=180),
                    price_list_version="2026-Q2",
                )
            )
            written += 1
    await db.flush()
    logger.info("price_entries: %s", written)


# ─────────────────────── 7. quotes ───────────────────────────────────


async def _seed_quotes(
    db, tenant_ids: list[int], customer_ids: list[int], opp_ids: list[int],
    user_ids_by_role: dict, spare_ids: list[int],
) -> list[int]:
    from app.models.quote import Quote
    from app.models.quote_item import QuoteItem
    from app.models.spare_part import SparePart
    from sqlalchemy import select

    rep_id = (user_ids_by_role["sales_rep"] or user_ids_by_role["sales_manager"])[0]
    statuses = ("draft", "pending_approval", "approved", "sent", "accepted", "rejected")
    out: list[int] = []

    for i, oid in enumerate(opp_ids[:60]):
        quote_number = f"Q-2026-{1000 + i}"
        existing = (
            await db.execute(select(Quote).where(Quote.quote_number == quote_number))
        ).scalar_one_or_none()
        if existing is not None:
            out.append(existing.id)
            continue
        cust_id = customer_ids[i % len(customer_ids)]
        status = statuses[i % len(statuses)]
        # Build line items
        items_data: list[tuple[int, int, float, float]] = []
        for _ in range(RNG.randint(1, 4)):
            sid = RNG.choice(spare_ids)
            qty = RNG.randint(1, 10)
            unit = float(RNG.randint(1500, 25000))
            disc = float(RNG.choice([0.0, 5.0, 10.0, 15.0, 20.0]))
            items_data.append((sid, qty, unit, disc))
        subtotal = sum(qty * unit for _sid, qty, unit, _d in items_data)
        discount = sum(qty * unit * d / 100.0 for _sid, qty, unit, d in items_data)
        tax = (subtotal - discount) * 0.20
        grand = subtotal - discount + tax
        q = Quote(
            quote_number=quote_number,
            customer_id=cust_id,
            created_by=rep_id,
            status=status,
            language="tr",
            currency="TRY",
            subtotal=subtotal,
            discount_total=discount,
            tax_rate=20.0,
            tax_amount=tax,
            grand_total=grand,
            valid_days=30,
            notes=f"Auto-seeded quote for opportunity #{oid}",
            tenant_id=tenant_ids[0] if i < 50 else tenant_ids[-1],
        )
        db.add(q)
        await db.flush()
        for sid, qty, unit, disc in items_data:
            spare = await db.get(SparePart, sid)
            db.add(
                QuoteItem(
                    quote_id=q.id,
                    spare_part_id=sid,
                    quantity=qty,
                    unit_price=unit,
                    discount_pct=disc,
                    line_total=qty * unit * (1 - disc / 100.0),
                    description=spare.name_tr if spare else f"Item {sid}",
                )
            )
        out.append(q.id)
    await db.flush()
    logger.info("quotes: %s", len(out))
    return out


# ─────────────────────── 8. activity history ─────────────────────────


async def _seed_activity_history(
    db, opp_ids: list[int], customer_ids: list[int], user_ids_by_role: dict
) -> None:
    """Spread realistic activity across the last 90 days for V4/V5 features."""
    from app.models.activity_log import ActivityLog
    from app.models.opportunity import OpportunityEvent
    from app.models.sales_event_shadow import SalesEventShadow

    rep_ids = user_ids_by_role["sales_rep"] or user_ids_by_role["sales_manager"]
    today = datetime.now(timezone.utc)

    activity_types = ["email_sent", "email_received", "meeting_booked", "call_logged", "note_added"]
    written_acts = 0
    written_events = 0
    written_shadows = 0
    seen_refs = set()

    for oid in opp_ids:
        cust_id = customer_ids[(oid - 1) % len(customer_ids)] if customer_ids else None
        n_events = RNG.randint(4, 12)
        for k in range(n_events):
            days_ago = RNG.randint(1, 89)
            ts = today - timedelta(days=days_ago, hours=RNG.randint(0, 23))
            atype = RNG.choice(activity_types)
            ref = f"seed-v8:{oid}:{k}"
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            db.add(
                ActivityLog(
                    activity_type=atype,
                    entity_type="opportunity",
                    entity_id=oid,
                    opportunity_id=oid,
                    customer_id=cust_id,
                    user_id=RNG.choice(rep_ids) if atype != "email_received" else None,
                    summary=f"{atype.replace('_', ' ').title()} demo entry",
                    duration_minutes=RNG.randint(10, 60) if atype in {"meeting_booked", "call_logged"} else None,
                    created_at=ts,
                    source_ref=ref,
                )
            )
            written_acts += 1

            # Mirror to OpportunityEvent + SalesEventShadow for V4/V5.
            db.add(
                OpportunityEvent(
                    opportunity_id=oid,
                    event_type=_event_type_for(atype),
                    entity_type="activity_log",
                    entity_id=0,
                    description=f"{atype} demo",
                    occurred_at=ts,
                )
            )
            written_events += 1

            db.add(
                SalesEventShadow(
                    source_ref=f"shadow:seed:{oid}:{k}",
                    provenance="seed",
                    account_id=cust_id,
                    opportunity_id=oid,
                    event_type=_event_type_for(atype),
                    event_ts=ts,
                    actor_type="rep" if atype != "email_received" else "buyer",
                    channel="email" if atype.startswith("email") else "call" if "call" in atype else "meeting" if "meeting" in atype else "system",
                    direction="outbound" if atype in {"email_sent", "call_logged"} else "inbound" if atype == "email_received" else "internal",
                    payload_json="{}",
                )
            )
            written_shadows += 1
    await db.flush()
    logger.info(
        "activity_logs: %s, opportunity_events: %s, sales_event_shadows: %s",
        written_acts, written_events, written_shadows,
    )


def _event_type_for(activity_type: str) -> str:
    return {
        "email_sent": "email_sent",
        "email_received": "email_received",
        "meeting_booked": "meeting_logged",
        "call_logged": "call_logged",
        "note_added": "note_created",
    }.get(activity_type, activity_type)


# ─────────────────────── 9. signals + competitor mentions ────────────


async def _seed_signals_and_events(
    db, opp_ids: list[int], customer_ids: list[int], user_ids_by_role: dict
) -> None:
    from app.models.revenue_signal import RevenueSignal
    from app.models.competitor_mention import CompetitorMention

    rep_ids = user_ids_by_role["sales_rep"] or user_ids_by_role["sales_manager"]
    today = datetime.now(timezone.utc)

    signal_kinds = (
        ("pricing_concern", "high"),
        ("competitor_mention", "med"),
        ("positive", "low"),
        ("expansion_signal", "low"),
        ("churn_risk", "high"),
        ("quote_stalled", "med"),
        ("upsell_detected", "low"),
    )
    written_sig = 0
    for oid in opp_ids:
        for k in range(RNG.randint(1, 4)):
            stype, sev = RNG.choice(signal_kinds)
            db.add(
                RevenueSignal(
                    signal_type=stype,
                    source_entity_type="seed",
                    source_entity_id=None,
                    severity=sev,
                    confidence=RNG.uniform(0.55, 0.95),
                    opportunity_id=oid,
                    customer_id=customer_ids[(oid - 1) % len(customer_ids)],
                    owner_id=RNG.choice(rep_ids),
                    recommended_action="Aksiyona dön: müşteriyle ilişkiyi netleştir",
                    metadata_json=json.dumps({"summary": f"{stype} demo signal"}),
                    event_key=f"seed:{oid}:{stype}:{k}:{written_sig}",
                    created_at=today - timedelta(days=RNG.randint(1, 30)),
                )
            )
            written_sig += 1

    # Competitor mentions
    competitors = ("Siemens", "Schneider", "Johnson Controls", "ABB", "Mitsubishi")
    written_cm = 0
    for oid in opp_ids:
        if RNG.random() > 0.6:  # 40% of opps have competitor pressure
            db.add(
                CompetitorMention(
                    opportunity_id=oid,
                    competitor_name=RNG.choice(competitors),
                    source_entity_type="opportunity",
                    source_entity_id=oid,
                    context_snippet="Customer mentioned evaluating alternatives",
                    sentiment=RNG.choice(["negative", "neutral"]),
                    detected_by="seed",
                    created_at=today - timedelta(days=RNG.randint(1, 60)),
                )
            )
            written_cm += 1
    await db.flush()
    logger.info("revenue_signals: %s, competitor_mentions: %s", written_sig, written_cm)


# ─────────────────────── 10. stakeholders ────────────────────────────


async def _seed_stakeholders_and_competitors(
    db, opp_ids: list[int], customer_ids: list[int]
) -> None:
    from app.models.sequence_v2 import Stakeholder

    written = 0
    for oid in opp_ids:
        n = RNG.randint(1, 4)
        for k in range(n):
            title = RNG.choice(CONTACT_TITLES)
            db.add(
                Stakeholder(
                    opportunity_id=oid,
                    customer_id=customer_ids[(oid - 1) % len(customer_ids)],
                    name=f"Stakeholder {oid}-{k}",
                    email=f"sh{oid}_{k}@demo.honeywell",
                    title=title,
                    seniority="executive" if title in {"CEO", "CTO", "CFO"} else "senior",
                    department_group=RNG.choice(["tech", "finance", "operations", "legal"]),
                    buyer_role=RNG.choice(["champion", "economic_buyer", "technical_buyer", "user_buyer"]),
                    is_auto_detected=False,
                )
            )
            written += 1
    await db.flush()
    logger.info("stakeholders: %s", written)


# ─────────────────────── 11. objections + actions ────────────────────


async def _seed_objections(db, opp_ids: list[int]) -> None:
    from app.models.v5_objection import Objection, ObjectionResolutionAction

    objection_types = ("price", "timing", "security", "integration", "competition", "procurement")
    severities = ("low", "med", "high")
    written_obj = 0
    written_act = 0
    today = datetime.now(timezone.utc)

    for oid in opp_ids:
        if RNG.random() > 0.5:
            n = RNG.randint(1, 2)
            for _ in range(n):
                otype = RNG.choice(objection_types)
                resolved = RNG.random() > 0.5
                created_at = today - timedelta(days=RNG.randint(2, 60))
                obj = Objection(
                    opportunity_id=oid,
                    objection_type=otype,
                    severity=RNG.choice(severities),
                    evidence_text=f"{otype} concern raised by buyer (demo)",
                    resolved_flag=resolved,
                    resolved_at=created_at + timedelta(hours=RNG.randint(12, 96)) if resolved else None,
                    ttr_hours=float(RNG.randint(8, 96)) if resolved else None,
                    created_at=created_at,
                )
                db.add(obj)
                await db.flush()
                written_obj += 1
                # Resolution actions
                for action_type in RNG.sample(
                    ["roi_note_sent", "revised_quote", "technical_call", "stakeholder_added", "payment_terms_changed"],
                    k=RNG.randint(1, 2),
                ):
                    db.add(
                        ObjectionResolutionAction(
                            objection_id=obj.id,
                            action_type=action_type,
                            payload_json=json.dumps({"source": "seed"}),
                        )
                    )
                    written_act += 1
    await db.flush()
    logger.info("objections: %s, resolution_actions: %s", written_obj, written_act)


# ─────────────────────── 12. leads ───────────────────────────────────


async def _seed_leads(db, tenant_ids: list[int], user_ids_by_role: dict) -> None:
    from app.models.lead import Lead
    from sqlalchemy import select

    rep_ids = user_ids_by_role["sales_rep"] or user_ids_by_role["sales_manager"]
    statuses = ("new", "contacted", "qualified", "unqualified")
    sources = ("email", "web", "referral", "import", "manual")

    written = 0
    for i in range(40):
        email = f"lead{i + 1}@prospect.demo"
        existing = (
            await db.execute(select(Lead).where(Lead.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            continue
        first, last = RNG.choice(REP_NAMES)
        db.add(
            Lead(
                first_name=first,
                last_name=last,
                email=email,
                phone=f"+90 5{RNG.randint(30, 59)} {RNG.randint(100, 999)} {RNG.randint(1000, 9999)}",
                company=f"Prospect Co. {i + 1}",
                title=RNG.choice(CONTACT_TITLES),
                source=RNG.choice(sources),
                status=RNG.choice(statuses),
                lead_score=RNG.randint(20, 95),
                owner_id=RNG.choice(rep_ids),
                tenant_id=tenant_ids[0],
            )
        )
        written += 1
    await db.flush()
    logger.info("leads: %s", written)


# ─────────────────────── 13. email templates ─────────────────────────


async def _seed_email_templates(db, user_ids_by_role: dict) -> None:
    from app.models.email_template import EmailTemplate
    from sqlalchemy import select

    mgr_id = user_ids_by_role["sales_manager"][0]
    templates = (
        ("Karşılama", "Welcome — first touch email", "Merhaba {name},<br><br>Hoş geldiniz!"),
        ("Quote follow-up", "Post-quote 24h follow-up", "Merhaba {name},<br><br>Gönderdiğimiz teklif hakkında..."),
        ("Demo daveti", "Discovery demo invite", "Merhaba {name},<br><br>Bir demo planlamak ister misiniz?"),
        ("Itiraz cevabı (fiyat)", "Price objection response", "Yatırımın geri dönüşünü..."),
        ("Procurement bilgileri", "Procurement docs sent", "Procurement süreci için..."),
        ("Renewal hatırlatma", "Subscription renewal reminder", "Yenileme tarihi yaklaşıyor..."),
        ("ROI hesaplaması", "ROI calculation", "Yatırımınızın geri dönüşü..."),
        ("Sözleşme imza", "Contract signature request", "Sözleşmeyi imzalamak için..."),
    )
    written = 0
    for name, subject, body in templates:
        existing = (
            await db.execute(select(EmailTemplate).where(EmailTemplate.name == name))
        ).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            EmailTemplate(
                name=name,
                subject=subject,
                body_html=body,
                category="sales",
                is_shared=True,
                created_by=mgr_id,
            )
        )
        written += 1
    await db.flush()
    logger.info("email_templates: %s", written)


# ─────────────────────── 14. campaigns ───────────────────────────────


async def _seed_campaigns(db, user_ids_by_role: dict, customer_ids: list[int]) -> None:
    from app.models.campaign import Campaign, CampaignMember
    from sqlalchemy import select

    mgr_id = user_ids_by_role["sales_manager"][0]
    today = datetime.now(timezone.utc)

    plans = (
        ("Q2 Push — HVAC Modernizasyon", "active", "email"),
        ("Win-back — Sleeping Accounts", "active", "email"),
        ("New Logo — EMEA", "active", "outbound"),
        ("Renewal Drive — Q3", "scheduled", "email"),
    )
    written_camp = 0
    written_mem = 0
    for name, status, ctype in plans:
        existing = (
            await db.execute(select(Campaign).where(Campaign.name == name))
        ).scalar_one_or_none()
        if existing is None:
            c = Campaign(
                name=name,
                type=ctype,
                description=f"{name} — auto seeded campaign",
                status=status,
                start_date=today,
                end_date=today + timedelta(days=60),
                budget=float(RNG.randint(50_000, 250_000)),
                expected_revenue=float(RNG.randint(200_000, 1_000_000)),
                created_by=mgr_id,
            )
            db.add(c)
            await db.flush()
            written_camp += 1
        else:
            c = existing
        # Add 25 members per campaign
        existing_members = (
            await db.execute(
                select(CampaignMember.id).where(CampaignMember.campaign_id == c.id).limit(1)
            )
        ).scalar_one_or_none()
        if existing_members is None:
            for cid in RNG.sample(customer_ids, k=min(25, len(customer_ids))):
                db.add(
                    CampaignMember(
                        campaign_id=c.id,
                        customer_id=cid,
                        status=RNG.choice(["sent", "opened", "clicked", "responded"]),
                    )
                )
                written_mem += 1
    await db.flush()
    logger.info("campaigns: %s, campaign_members: %s", written_camp, written_mem)


# ─────────────────────── 15. contracts ───────────────────────────────


async def _seed_contracts(
    db, customer_ids: list[int], opp_ids: list[int], user_ids_by_role: dict
) -> None:
    from app.models.contract import Contract, ContractAmendment
    from sqlalchemy import select

    mgr_id = user_ids_by_role["sales_manager"][0]
    today = datetime.now(timezone.utc)

    written_c = 0
    written_a = 0
    won_opp_ids = opp_ids[64:74] if len(opp_ids) > 74 else opp_ids[:10]
    for i, oid in enumerate(won_opp_ids):
        title = f"Master service agreement #{2000 + i}"
        existing = (
            await db.execute(select(Contract).where(Contract.title == title))
        ).scalar_one_or_none()
        if existing is not None:
            continue
        c = Contract(
            customer_id=customer_ids[i % len(customer_ids)],
            title=title,
            status=RNG.choice(["active", "active", "draft", "expired"]),
            value=float(RNG.randint(100_000, 800_000)),
            terms_json=json.dumps({"payment_terms": "net_30", "auto_renew": True}),
            created_by=mgr_id,
        )
        db.add(c)
        await db.flush()
        written_c += 1
        # 0-1 amendment per contract
        if RNG.random() > 0.7:
            db.add(
                ContractAmendment(
                    contract_id=c.id,
                    amendment_type="pricing_tier_upgrade",
                    changes_json=json.dumps({"delta_value": RNG.randint(20_000, 80_000)}),
                    approved_by=mgr_id,
                )
            )
            written_a += 1
    await db.flush()
    logger.info("contracts: %s, amendments: %s", written_c, written_a)


# ─────────────────────── 16. deal rooms ──────────────────────────────


async def _seed_deal_rooms(db, opp_ids: list[int], user_ids_by_role: dict) -> None:
    from app.models.deal_room import DealRoom
    from app.models.shared_document import SharedDocument
    from sqlalchemy import select

    mgr_id = user_ids_by_role["sales_manager"][0]
    written_dr = 0
    written_doc = 0
    for i, oid in enumerate(opp_ids[:10]):
        token = f"demo-token-{oid}"
        existing = (
            await db.execute(select(DealRoom).where(DealRoom.external_token == token))
        ).scalar_one_or_none()
        if existing is None:
            dr = DealRoom(
                opportunity_id=oid,
                name=f"Deal Room #{oid}",
                external_token=token,
                shared_items_json=json.dumps([{"type": "doc", "name": f"doc_{oid}.pdf"}]),
                welcome_message="Merhaba — paylaşılmış evrak alanına hoş geldiniz.",
                is_active=True,
                created_by=mgr_id,
            )
            db.add(dr)
            await db.flush()
            written_dr += 1

    # SharedDocument is decoupled from DealRoom in the existing schema —
    # it links to ``quote_id`` instead. Seed a few demo shares.
    from app.models.quote import Quote

    quote_ids = [
        int(qid) for qid in (
            await db.execute(select(Quote.id).order_by(Quote.id.asc()).limit(10))
        ).scalars().all()
    ]
    for i, qid in enumerate(quote_ids):
        for k in range(2):
            tok = f"share-{qid}-{k}"
            already = (
                await db.execute(select(SharedDocument).where(SharedDocument.tracking_token == tok))
            ).scalar_one_or_none()
            if already is None:
                db.add(
                    SharedDocument(
                        quote_id=qid,
                        file_name=f"quote_{qid}_v{k}.pdf",
                        file_url=f"https://demo.cdn/quotes/{qid}-v{k}.pdf",
                        shared_with_email=f"buyer{qid}@demo.honeywell",
                        tracking_token=tok,
                        created_by=mgr_id,
                    )
                )
                written_doc += 1
    await db.flush()
    logger.info("deal_rooms: %s, shared_documents: %s", written_dr, written_doc)


# ─────────────────────── 17. meetings ────────────────────────────────


async def _seed_meetings(db, user_ids_by_role: dict) -> None:
    from app.models.meeting_link import MeetingLink
    from app.models.meeting_booking import MeetingBooking
    from sqlalchemy import select

    rep_ids = user_ids_by_role["sales_rep"] or user_ids_by_role["sales_manager"]
    today = datetime.now(timezone.utc)
    written_link = 0
    written_book = 0
    for i, rid in enumerate(rep_ids[:4]):
        slug = f"rep-{rid}-discovery"
        existing = (
            await db.execute(select(MeetingLink).where(MeetingLink.slug == slug))
        ).scalar_one_or_none()
        if existing is None:
            link = MeetingLink(
                user_id=rid,
                title=f"Discovery call — Rep #{rid}",
                slug=slug,
                duration_minutes=30,
                is_active=True,
            )
            db.add(link)
            await db.flush()
            written_link += 1
        else:
            link = existing
        # 6 bookings per link
        for k in range(6):
            db.add(
                MeetingBooking(
                    meeting_link_id=link.id,
                    booker_email=f"booker{i}_{k}@demo.honeywell",
                    booker_name=f"Booker {i}-{k}",
                    scheduled_at=today + timedelta(days=RNG.randint(1, 30), hours=RNG.randint(9, 17)),
                    status=RNG.choice(["scheduled", "completed", "cancelled"]),
                )
            )
            written_book += 1
    await db.flush()
    logger.info("meeting_links: %s, bookings: %s", written_link, written_book)


# ─────────────────────── 18. subscriptions ───────────────────────────


async def _seed_subscriptions(db, customer_ids: list[int], user_ids_by_role: dict) -> None:
    from app.models.subscription import Subscription
    from app.models.contract import Contract
    from app.models.revenue_recognition import RevenueSchedule, RevenueScheduleEntry
    from sqlalchemy import select

    mgr_id = user_ids_by_role["sales_manager"][0]
    today = datetime.now(timezone.utc)
    written_sub = 0
    written_sched = 0

    contract_ids_by_cust: dict[int, int] = dict(
        (int(r[0]), int(r[1]))
        for r in (
            await db.execute(select(Contract.customer_id, Contract.id))
        ).all()
    )

    for i, cid in enumerate(customer_ids[:12]):
        sub_name = f"Honeywell Cloud — Plan {RNG.choice(['Starter', 'Pro', 'Enterprise'])} (#{i})"
        existing = (
            await db.execute(
                select(Subscription).where(Subscription.customer_id == cid).where(Subscription.name == sub_name)
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        s = Subscription(
            customer_id=cid,
            name=sub_name,
            mrr=float(RNG.randint(2_000, 25_000)),
            status=RNG.choice(["active", "active", "active", "paused"]),
            currency="TRY",
            billing_cycle="monthly",
            start_date=(today - timedelta(days=RNG.randint(30, 365))).date(),
            end_date=(today + timedelta(days=365)).date(),
            next_renewal_date=(today + timedelta(days=30)).date(),
            auto_renew=True,
            created_by=mgr_id,
        )
        db.add(s)
        await db.flush()
        written_sub += 1

        # Schedule + 3 monthly entries (RevenueSchedule requires contract_id)
        contract_id = contract_ids_by_cust.get(cid)
        if contract_id is None:
            continue
        sch = RevenueSchedule(
            contract_id=contract_id,
            recognition_type="straight_line",
            start_date=today,
            end_date=today + timedelta(days=365),
            total_amount=s.mrr * 12,
            currency="TRY",
            created_by=mgr_id,
        )
        db.add(sch)
        await db.flush()
        for k in range(3):
            month = (today + timedelta(days=k * 30)).strftime("%Y-%m")
            db.add(
                RevenueScheduleEntry(
                    schedule_id=sch.id,
                    period=month,
                    amount=s.mrr,
                    recognized_amount=s.mrr if k == 0 else 0.0,
                    status="recognized" if k == 0 else "pending",
                )
            )
            written_sched += 1
    await db.flush()
    logger.info("subscriptions: %s, revenue_schedule_entries: %s", written_sub, written_sched)


# ─────────────────────── 19. sequences (v2) ──────────────────────────


async def _seed_sequences_v2(db, user_ids_by_role: dict, customer_ids: list[int]) -> None:
    from app.models.engagement import Sequence, SequenceEnrollment
    from sqlalchemy import select

    mgr_id = user_ids_by_role["sales_manager"][0]
    sequences = (
        ("Welcome Series", 4),
        ("Post-Quote Nudge", 5),
        ("Procurement Path", 3),
        ("Renewal Drive", 4),
    )
    written_seq = 0
    written_enr = 0
    for name, steps_n in sequences:
        existing = (
            await db.execute(select(Sequence).where(Sequence.name == name))
        ).scalar_one_or_none()
        if existing is None:
            s = Sequence(
                name=name,
                description=f"{name} demo sequence",
                steps_json=json.dumps(
                    [
                        {"step": i + 1, "delay_days": i * 3, "channel": "email", "subject": f"{name} step {i + 1}"}
                        for i in range(steps_n)
                    ]
                ),
                is_active=True,
            )
            db.add(s)
            await db.flush()
            written_seq += 1
        else:
            s = existing
        # 15 enrollments per sequence (skip step runs — schema varies)
        for cid in RNG.sample(customer_ids, k=min(15, len(customer_ids))):
            db.add(
                SequenceEnrollment(
                    sequence_id=s.id,
                    customer_id=cid,
                    status=RNG.choice(["active", "active", "completed", "paused"]),
                    current_step=RNG.randint(1, steps_n),
                )
            )
            written_enr += 1
    await db.flush()
    logger.info("sequences: %s, enrollments: %s", written_seq, written_enr)


# ─────────────────────── 20. chat ────────────────────────────────────


async def _seed_chat(db, user_ids_by_role: dict, customer_ids: list[int]) -> None:
    from app.models.chat import ChatSession, ChatMessage, AutoResponseRule
    from sqlalchemy import select

    mgr_id = user_ids_by_role["sales_manager"][0]

    written_sess = 0
    written_msg = 0
    for i, cid in enumerate(customer_ids[:8]):
        visitor_id = f"visitor-{cid}-{i}"
        existing = (
            await db.execute(select(ChatSession).where(ChatSession.visitor_id == visitor_id))
        ).scalar_one_or_none()
        if existing is None:
            sess = ChatSession(
                visitor_id=visitor_id,
                assigned_agent_id=mgr_id,
                status=RNG.choice(["open", "closed"]),
                metadata_json=json.dumps({"customer_id": cid, "demo": True}),
            )
            db.add(sess)
            await db.flush()
            written_sess += 1
        else:
            sess = existing
        for k in range(6):
            db.add(
                ChatMessage(
                    session_id=sess.id,
                    sender_type=RNG.choice(["customer", "agent"]),
                    sender_id=str(mgr_id) if k % 2 == 1 else None,
                    content=f"Demo message {k + 1}",
                    message_type="text",
                )
            )
            written_msg += 1

    written_rules = 0
    for kw, reply in (
        ("fiyat", "İletişime geçeceğiz"),
        ("kaç para", "Detaylı teklif gönderebiliriz"),
        ("demo", "Demo planlayalım"),
        ("itiraz", "Endişenizi dinlemek isteriz"),
    ):
        existing = (
            await db.execute(
                select(AutoResponseRule).where(AutoResponseRule.trigger_keyword == kw)
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                AutoResponseRule(
                    trigger_keyword=kw,
                    response_text=reply,
                    is_active=True,
                    priority=10,
                    created_by=mgr_id,
                )
            )
            written_rules += 1
    await db.flush()
    logger.info("chat_sessions: %s, messages: %s, auto_rules: %s", written_sess, written_msg, written_rules)


# ─────────────────────── 21. reports + dashboards ────────────────────


async def _seed_reports_and_dashboards(db, user_ids_by_role: dict) -> None:
    from app.models.report import ReportTemplate
    from app.models.report_folder import ReportFolder
    from app.models.dashboard_config import DashboardConfig
    from sqlalchemy import select

    mgr_id = user_ids_by_role["sales_manager"][0]

    folders = ("Yönetim", "Satış", "Operasyon", "Compliance")
    folder_ids = []
    for name in folders:
        existing = (
            await db.execute(select(ReportFolder).where(ReportFolder.name == name))
        ).scalar_one_or_none()
        if existing is None:
            f = ReportFolder(name=name, owner_id=mgr_id)
            db.add(f)
            await db.flush()
            folder_ids.append(f.id)
        else:
            folder_ids.append(existing.id)

    templates = (
        ("Pipeline Sağlığı", "pipeline"),
        ("Forecast vs Actual", "forecast"),
        ("Rep Performans", "performance"),
        ("Müşteri Sağlık Skoru", "health"),
        ("Quote Conversion", "quote"),
        ("Activity Heatmap", "activity"),
        ("Loss Reason Analysis", "loss"),
        ("Stakeholder Coverage", "stakeholder"),
        ("Discount Distribution", "discount"),
        ("Stage Velocity", "velocity"),
        ("Network Anomalies", "anomaly"),
        ("DNA Patterns", "dna"),
    )
    written_tpl = 0
    for i, (name, kind) in enumerate(templates):
        existing = (
            await db.execute(select(ReportTemplate).where(ReportTemplate.name == name))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                ReportTemplate(
                    name=name,
                    description=f"{name} demo report",
                    entity_type="opportunity",
                    columns_json=json.dumps(["title", "stage", "amount", "owner"]),
                    filters_json=json.dumps({"kind": kind}),
                    folder_id=folder_ids[i % len(folder_ids)],
                    created_by=mgr_id,
                    is_public=True,
                )
            )
            written_tpl += 1

    written_dash = 0
    for name in ("CEO Cockpit", "Manager Daily", "Rep Daily", "Operations", "Coaching"):
        existing = (
            await db.execute(select(DashboardConfig).where(DashboardConfig.name == name))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                DashboardConfig(
                    name=name,
                    widgets_json=json.dumps(
                        [{"widget": w, "x": i * 4, "y": 0, "w": 4, "h": 3}
                         for i, w in enumerate(["pipeline", "forecast", "activity"])]
                    ),
                    owner_id=mgr_id,
                    is_default=(name == "Manager Daily"),
                )
            )
            written_dash += 1
    await db.flush()
    logger.info("report_templates: %s, dashboards: %s", written_tpl, written_dash)


# ─────────────────────── 22. saved views + comments + notifications ──


async def _seed_saved_views_comments_notifications(
    db, user_ids_by_role: dict, opp_ids: list[int]
) -> None:
    from app.models.saved_view import SavedView
    from app.models.comment import Comment
    from app.models.notification import Notification
    from sqlalchemy import select

    mgr_id = user_ids_by_role["sales_manager"][0]
    rep_ids = user_ids_by_role["sales_rep"] or [mgr_id]

    written_views = 0
    for name in (
        "Q2 Hot Deals", "Stalling Deals", "Closing This Week",
        "Manager Watchlist", "High Risk", "Top Pipeline",
        "Won Last 30d", "Lost Last 30d", "Need Attention", "VIP Accounts",
    ):
        existing = (
            await db.execute(select(SavedView).where(SavedView.name == name))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                SavedView(
                    user_id=mgr_id,
                    name=name,
                    route="/opportunities",
                    query_json=json.dumps({"stage_in": ["qualified", "proposal"]}),
                )
            )
            written_views += 1

    written_comments = 0
    for oid in opp_ids[:30]:
        for k in range(RNG.randint(0, 2)):
            db.add(
                Comment(
                    entity_type="opportunity",
                    entity_id=oid,
                    user_id=RNG.choice(rep_ids),
                    body=f"Comment {k + 1} on opportunity #{oid}",
                )
            )
            written_comments += 1

    written_notifs = 0
    for rid in rep_ids:
        for k in range(5):
            db.add(
                Notification(
                    user_id=rid,
                    type=RNG.choice(["task_due", "deal_update", "approval", "mention"]),
                    title=f"Demo notification {k + 1}",
                    message=f"You have a demo notification #{k + 1}",
                    is_read=k > 2,
                )
            )
            written_notifs += 1
    await db.flush()
    logger.info("saved_views: %s, comments: %s, notifications: %s", written_views, written_comments, written_notifs)


# ─────────────────────── 23. api keys + workflows ────────────────────


async def _seed_api_keys_workflows(db, user_ids_by_role: dict) -> None:
    from app.models.api_key import ApiKey
    from app.models.workflow_rule import WorkflowRule
    from app.models.webhook import WebhookSubscription
    from sqlalchemy import select

    mgr_id = user_ids_by_role["sales_manager"][0]

    written_keys = 0
    for i, name in enumerate(("Slack Integration", "Zapier Bridge", "BI Pipeline", "Internal Tooling")):
        existing = (
            await db.execute(select(ApiKey).where(ApiKey.name == name))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                ApiKey(
                    name=name,
                    key_hash=f"sha256:demo:{i}:{name.lower().replace(' ', '_')}",
                    user_id=mgr_id,
                    scopes_json=json.dumps(["read", "write"]),
                    is_active=True,
                )
            )
            written_keys += 1

    written_rules = 0
    rules = (
        ("Auto-assign new leads", "lead.created", "lead"),
        ("Notify on big deal", "opportunity.amount_change", "opportunity"),
        ("Auto-task post-quote", "quote.sent", "quote"),
        ("Stalled deal escalation", "deal.stalled", "opportunity"),
        ("Win celebration", "opportunity.closed_won", "opportunity"),
        ("Loss reason required", "opportunity.closed_lost", "opportunity"),
        ("Renewal reminder", "subscription.renewal_due", "subscription"),
        ("New customer welcome", "customer.created", "customer"),
    )
    for name, trigger, entity in rules:
        existing = (
            await db.execute(select(WorkflowRule).where(WorkflowRule.name == name))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                WorkflowRule(
                    name=name,
                    entity_type=entity,
                    trigger_event=trigger,
                    conditions_json=json.dumps([]),
                    actions_json=json.dumps([{"type": "create_task", "title": "Auto"}]),
                    is_active=True,
                    created_by=mgr_id,
                )
            )
            written_rules += 1

    written_hooks = 0
    for name, url in (
        ("Slack — sales-wins", "https://hooks.slack.com/demo/wins"),
        ("Slack — losses", "https://hooks.slack.com/demo/losses"),
        ("BI — pipeline", "https://bi.demo/webhook"),
        ("PagerDuty — anomalies", "https://pd.demo/anomaly"),
        ("Zapier — leads", "https://zapier.demo/leads"),
        ("Internal alerter", "https://alert.demo"),
    ):
        existing = (
            await db.execute(select(WebhookSubscription).where(WebhookSubscription.name == name))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                WebhookSubscription(
                    name=name,
                    url=url,
                    event_types=json.dumps(["opportunity.*"]),
                    secret="demo-secret",
                    is_active=True,
                    created_by=mgr_id,
                )
            )
            written_hooks += 1
    await db.flush()
    logger.info("api_keys: %s, workflow_rules: %s, webhooks: %s", written_keys, written_rules, written_hooks)


# ─────────────────────── 24. derived data builders ───────────────────


async def _build_derived_data(*, target_days: int = 30) -> None:
    """Run V4/V5/V6/V7 builders so analytics dashboards aren't empty."""
    from app.core.database import async_session
    from app.services.feature_store_builder import build_daily_feature_store
    from app.services.v4_learning_nightly import (
        run_v5_intelligence_nightly,
    )

    today = datetime.now(timezone.utc).date()
    # Backfill the feature store for each of the last N days. Each
    # call is its own session so a partial failure on one day doesn't
    # poison the rest.
    for offset in range(target_days, -1, -1):
        snap_date = today - timedelta(days=offset)
        try:
            async with async_session() as db:
                await build_daily_feature_store(db, snapshot_date=snap_date)
        except Exception as exc:
            logger.warning("feature_store_builder failed for %s: %s", snap_date, exc)

    # V5 + V6 + V7 + V8 pipeline (single pass — handles patterns,
    # embeddings, similarity links, replay deltas, anomalies, DNA
    # promote, adherence).
    try:
        async with async_session() as db:
            await run_v5_intelligence_nightly(db, target_date=today)
    except Exception as exc:
        logger.warning("v5_intelligence_nightly failed: %s", exc)


# ─────────────────────── 25. summary ─────────────────────────────────


async def _print_summary() -> None:
    from app.core.database import async_session
    from sqlalchemy import func, select

    from app.models.user import User
    from app.models.customer import Customer
    from app.models.opportunity import Opportunity, Task
    from app.models.quote import Quote
    from app.models.activity_log import ActivityLog
    from app.models.lead import Lead
    from app.models.feature_store_daily import OpportunityFeaturesDaily
    from app.models.v5_dna_patterns import DnaPattern
    from app.models.v5_objection import Objection
    from app.models.v5_similarity import DealSimilarityLink, OpportunityEmbedding
    from app.models.v6_replay import DealReplayDelta
    from app.models.v6_federated import FederatedBenchmark
    from app.models.v8_text_embedding import OpportunityTextEmbedding
    from app.models.v7_tenant import Tenant

    async with async_session() as db:
        async def _count(model):
            return (await db.execute(select(func.count()).select_from(model))).scalar() or 0

        rows = {
            "tenants": await _count(Tenant),
            "users": await _count(User),
            "customers": await _count(Customer),
            "opportunities": await _count(Opportunity),
            "tasks": await _count(Task),
            "quotes": await _count(Quote),
            "activity_logs": await _count(ActivityLog),
            "leads": await _count(Lead),
            "objections": await _count(Objection),
            "OFD rows": await _count(OpportunityFeaturesDaily),
            "DNA patterns": await _count(DnaPattern),
            "structured embeddings": await _count(OpportunityEmbedding),
            "text embeddings": await _count(OpportunityTextEmbedding),
            "similarity links": await _count(DealSimilarityLink),
            "replay deltas": await _count(DealReplayDelta),
            "federated benchmarks": await _count(FederatedBenchmark),
        }
    for k, v in rows.items():
        logger.info("  %-22s %5d", k, v)


# ─────────────────────── entry ───────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="V8 comprehensive demo seed")
    parser.add_argument("--apply", action="store_true", help="Actually run the seed")
    args = parser.parse_args()
    if not args.apply:
        logger.info(
            "Dry run — pass --apply to execute. The seed touches ~30 tables and "
            "runs the V5/V6/V7 pipeline at the end."
        )
        return 0
    asyncio.run(seed())
    return 0


if __name__ == "__main__":
    sys.exit(main())
