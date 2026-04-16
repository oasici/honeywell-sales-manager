"""Seed data for remaining empty pages: Dashboards, Coaching Plans,
Transcripts, Reports, KVKK Compliance.

Run AFTER seed_demo_data.py, seed_uat_data.py, AND seed_uat_gaps.py:
    cd backend && source venv/bin/activate && python -m scripts.seed_uat_pages

Creates:
1.  Dashboard Configs (2) — Saved dashboard layouts
2.  Coaching Plans (2)    — Rep improvement plans
3.  Transcripts (3)       — Call / meeting transcripts
4.  Report Templates (3)  — Saved report definitions
5.  Retention Policies (3) + Breach Notification (1) — KVKK / Compliance
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
logger = logging.getLogger("seed-pages")


async def seed_pages() -> None:
    from sqlalchemy import select, func

    from app.core.database import async_session, engine, Base
    from app.models.user import User
    from app.models.customer import Customer
    from app.models.opportunity import Opportunity
    from app.models.dashboard_config import DashboardConfig
    from app.models.coaching_plan import CoachingPlan
    from app.models.engagement import Transcript
    from app.models.report import ReportTemplate
    from app.models.retention_policy import RetentionPolicy
    from app.models.breach_notification import BreachNotification

    # Ensure all tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        now = datetime.now(timezone.utc)

        # ── Idempotency guard ──
        plan_count = (
            await db.execute(select(func.count(CoachingPlan.id)))
        ).scalar() or 0
        if plan_count > 0:
            logger.info(
                "Page data already seeded (%d coaching plans). Skipping.", plan_count
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
        opps = list(
            (
                await db.execute(select(Opportunity).order_by(Opportunity.id))
            ).scalars().all()
        )

        logger.info(
            "Loaded: %d customers, %d opps",
            len(customers),
            len(opps),
        )

        # ── 1. DASHBOARD CONFIGS ──
        logger.info("Creating dashboard configs...")

        dashboards = [
            DashboardConfig(
                name="Satis Genel Bakis",
                owner_id=admin_id,
                widgets_json=json.dumps([
                    {
                        "type": "kpi",
                        "title": "Pipeline Toplam",
                        "metric": "pipeline_total",
                        "w": 3,
                        "h": 1,
                        "x": 0,
                        "y": 0,
                    },
                    {
                        "type": "kpi",
                        "title": "Kazanma Orani",
                        "metric": "win_rate",
                        "w": 3,
                        "h": 1,
                        "x": 3,
                        "y": 0,
                    },
                    {
                        "type": "chart",
                        "title": "Aylik Trend",
                        "chart_type": "bar",
                        "metric": "monthly_revenue",
                        "w": 6,
                        "h": 2,
                        "x": 0,
                        "y": 1,
                    },
                    {
                        "type": "table",
                        "title": "En Iyi Firsatlar",
                        "source": "top_opportunities",
                        "w": 6,
                        "h": 2,
                        "x": 6,
                        "y": 1,
                    },
                ]),
                is_default=True,
            ),
            DashboardConfig(
                name="Rep Performans",
                owner_id=admin_id,
                widgets_json=json.dumps([
                    {
                        "type": "leaderboard",
                        "title": "Siralama",
                        "metric": "revenue",
                        "w": 4,
                        "h": 2,
                        "x": 0,
                        "y": 0,
                    },
                    {
                        "type": "chart",
                        "title": "Aktivite Dagilimi",
                        "chart_type": "pie",
                        "metric": "activities_by_type",
                        "w": 4,
                        "h": 2,
                        "x": 4,
                        "y": 0,
                    },
                ]),
                is_default=False,
            ),
        ]

        for dash in dashboards:
            db.add(dash)

        await db.flush()
        logger.info("Created %d dashboard configs", len(dashboards))

        # ── 2. COACHING PLANS ──
        logger.info("Creating coaching plans...")

        plans = [
            CoachingPlan(
                user_id=rep_id,
                manager_id=admin_id,
                status="active",
                start_date=(now - timedelta(days=14)).date(),
                weeks=8,
                goals_json=json.dumps([
                    {
                        "goal": "Aylik kapanan firsat sayisini 3'e cikar",
                        "target": "3 firsat/ay",
                    },
                    {
                        "goal": "Ortalama firsat buyuklugunu %20 artir",
                        "target": "50K TRY",
                    },
                    {
                        "goal": "Musteri yanit suresini 4 saatin altina indir",
                        "target": "< 4 saat",
                    },
                ]),
                created_at=now - timedelta(days=14),
            ),
            CoachingPlan(
                user_id=rep_id,
                manager_id=admin_id,
                status="completed",
                start_date=(now - timedelta(days=60)).date(),
                weeks=4,
                goals_json=json.dumps([
                    {
                        "goal": "DCS urun grubunu ogrenme",
                        "target": "Sertifika",
                    },
                    {
                        "goal": "3 demo toplantisi yapma",
                        "target": "3 demo",
                    },
                ]),
                created_at=now - timedelta(days=60),
            ),
        ]

        for plan in plans:
            db.add(plan)

        await db.flush()
        logger.info("Created %d coaching plans", len(plans))

        # ── 3. TRANSCRIPTS ──
        logger.info("Creating transcripts...")

        transcripts = [
            Transcript(
                title="Anadolu Endustri - HVAC Gorusmesi",
                source="zoom",
                duration_minutes=30,
                content=(
                    "Satici: Merhaba, Ahmet Bey. HVAC sisteminiz icin yeni vana teklifimizi "
                    "gorusmek istiyoruz.\n"
                    "Musteri: Evet, mevcut sistemimiz 5 yillik ve yenileme zamani geldi.\n"
                    "Satici: HW-VALVE-001 ve HW-VALVE-002 modellerimiz tam bu ihtiyaca uygun. "
                    "Size detayli teknik dokumantasyonu paylasmak istiyorum.\n"
                    "Musteri: Fiyat karsilastirmasi yapabilir miyiz?\n"
                    "Satici: Evet, rakip teklifleri de dikkate alarak size ozel bir fiyat hazirlayacagiz."
                ),
                summary=(
                    "Musteri HVAC yenileme projesi icin 2 adet vana modeli gorusuldu. "
                    "Musteri fiyat karsilastirmasi istedi."
                ),
                sentiment="positive",
                participants="Ahmet Yilmaz (Satici), Kemal Ozbek (Musteri)",
                opportunity_id=opps[0].id,
                customer_id=customers[0].id,
                created_by=admin_id,
                created_at=now - timedelta(days=7),
            ),
            Transcript(
                title="Ege Mekatronik - PLC Demo",
                source="teams",
                duration_minutes=45,
                content=(
                    "Satici: HC900 PLC kontrolorumuzu canli demo ile gostermek istiyoruz. "
                    "Sistemin konfigürasyon kolayligini goreceksiniz.\n"
                    "Musteri: Mevcut Siemens PLC'miz var, neden degistirelim?\n"
                    "Satici: HC900'un konfigürasyon kolayligi ve maliyet avantaji oldukca onemli. "
                    "Ek olarak destek ve yedek parca maliyetleri de daha dusuk.\n"
                    "Musteri: Fiyat karsilastirmasi gonderir misiniz?\n"
                    "Satici: Tabii, hafta sonuna kadar ayrintili karsilastirmayi paylasirim."
                ),
                summary=(
                    "PLC demo gorusmesi yapildi. Musteri Siemens'ten gecis konusunda cekimser. "
                    "Fiyat karsilastirmasi gonderilecek."
                ),
                sentiment="neutral",
                participants="Elif Kaya (Satici), Derya Koc (Musteri)",
                opportunity_id=opps[1].id,
                customer_id=customers[1].id,
                created_by=rep_id,
                created_at=now - timedelta(days=4),
            ),
            Transcript(
                title="GAP Muhendislik - Sozlesme Kapanisi",
                source="phone",
                duration_minutes=15,
                content=(
                    "Satici: Proses otomasyon projemiz icin final teklifimizi sunduk. "
                    "Sozlesme kosullarini goruselim.\n"
                    "Musteri: Kosullari kabul ediyoruz. Odeme takvimi uygundur.\n"
                    "Satici: Harika! Sozlesmeyi hazirlayin, imzalanmaya hazir.\n"
                    "Musteri: Proje baslangic tarihi ne olacak?\n"
                    "Satici: Sozlesme imzalandigindan itibaren 2 hafta icinde baslayabiliriz."
                ),
                summary=(
                    "Sozlesme onaylandi. GAP Muhendislik proses otomasyon projesi 350K TRY kapandi."
                ),
                sentiment="positive",
                participants="Ahmet Yilmaz (Satici), Murat Esen (Musteri)",
                opportunity_id=opps[4].id if len(opps) >= 5 else opps[0].id,
                customer_id=customers[7].id if len(customers) >= 8 else customers[0].id,
                created_by=admin_id,
                created_at=now - timedelta(days=2),
            ),
        ]

        for transcript in transcripts:
            db.add(transcript)

        await db.flush()
        logger.info("Created %d transcripts", len(transcripts))

        # ── 4. REPORT TEMPLATES ──
        logger.info("Creating report templates...")

        reports = [
            ReportTemplate(
                name="Aylik Satis Raporu",
                description="Tum satis temsilcilerinin aylik performansi",
                entity_type="opportunity",
                columns_json=json.dumps(
                    ["title", "stage", "amount", "close_date", "status"]
                ),
                filters_json=json.dumps(
                    [{"field": "status", "operator": "eq", "value": "active"}]
                ),
                sort_by="amount",
                sort_order="desc",
                group_by="stage",
                chart_type="bar",
                is_system=False,
                is_public=True,
                created_by=admin_id,
            ),
            ReportTemplate(
                name="Teklif Durum Ozeti",
                description="Tum tekliflerin durum bazli dagilimi",
                entity_type="quote",
                columns_json=json.dumps(
                    ["quote_number", "customer_name", "status", "grand_total", "created_at"]
                ),
                filters_json=json.dumps([]),
                sort_by="created_at",
                sort_order="desc",
                group_by="status",
                chart_type="pie",
                is_system=False,
                is_public=True,
                created_by=admin_id,
            ),
            ReportTemplate(
                name="Musteri Saglik Raporu",
                description="Musteri saglik skorlari ve risk degerlendirmesi",
                entity_type="customer",
                columns_json=json.dumps(
                    ["name", "company", "health_score", "last_contact_date", "total_revenue"]
                ),
                filters_json=json.dumps(
                    [{"field": "health_score", "operator": "lt", "value": 70}]
                ),
                sort_by="health_score",
                sort_order="asc",
                group_by=None,
                chart_type="table",
                is_system=False,
                is_public=False,
                created_by=admin_id,
            ),
        ]

        for report in reports:
            db.add(report)

        await db.flush()
        logger.info("Created %d report templates", len(reports))

        # ── 5. RETENTION POLICIES + BREACH NOTIFICATION ──
        logger.info("Creating retention policies...")

        retention_policies = [
            RetentionPolicy(
                entity_type="customer",
                retention_days=1095,  # 3 years
                action="notify",
                is_active=True,
            ),
            RetentionPolicy(
                entity_type="email_request",
                retention_days=730,  # 2 years
                action="archive",
                is_active=True,
            ),
            RetentionPolicy(
                entity_type="activity_log",
                retention_days=2555,  # 7 years
                action="notify",
                is_active=True,
            ),
        ]

        for policy in retention_policies:
            db.add(policy)

        await db.flush()
        logger.info("Created %d retention policies", len(retention_policies))

        logger.info("Creating breach notification...")

        breach = BreachNotification(
            breach_type="unauthorized_access",
            description="Yetkisiz erisim tespiti - test verisi. Sistem gunluklerinde anormal erisim deseni goruldu.",
            affected_customers_json=json.dumps(
                [customers[0].id, customers[1].id, customers[2].id]
                if len(customers) >= 3
                else [customers[0].id]
            ),
            severity="medium",
            status="investigating",
            created_by=admin_id,
            created_at=now - timedelta(days=3),
        )
        db.add(breach)

        await db.flush()
        logger.info("Created 1 breach notification")

        # ── COMMIT ──
        await db.commit()

        logger.info("=" * 60)
        logger.info("UAT PAGES SEED COMPLETE")
        logger.info("=" * 60)
        logger.info("  Dashboard Configs:   2")
        logger.info("  Coaching Plans:      2")
        logger.info("  Transcripts:         3")
        logger.info("  Report Templates:    3")
        logger.info("  Retention Policies:  3")
        logger.info("  Breach Notifications: 1")
        logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed_pages())
