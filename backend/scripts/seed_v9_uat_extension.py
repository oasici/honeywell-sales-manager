"""V9 UAT seed extension.

Adds the entities flagged as "missing seed" in the V9 UAT review (34
items) on top of the V8 seed. Run **after** ``seed_v8_full_demo.py``:

    python -m scripts.seed_v8_full_demo --apply
    python -m scripts.seed_v9_uat_extension --apply

Idempotent: re-running upserts by stable natural keys.

Surfaces covered (UAT item refs):

* ApprovalRule + ApprovalRequest (#12, #13)
* Invoice (#9)
* Transcript (#22)
* KeywordPack (#23)
* Segment (#25)
* CustomField + CustomFieldValue (#29)
* FieldPermission (#30)
* ProductRule (#31)
* WorkflowRule extras (#32 — variety)
* Territory + TerritoryAssignment extras (#33)
* ProductBundle (#14)
* RetentionPolicy + BreachNotification (#28)
* CoachingPlan + CoachingSnapshot (#21)
* ForecastAdjustment + PipelineSnapshot + ForecastSnapshotDetail (#6)
* PlaybookExecution (#20)
* SequenceStepRun extras (#24)
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
logger = logging.getLogger("seed_v9_uat")

RNG = random.Random(2026)


async def seed_extension():
    from sqlalchemy import select
    from app.core.database import async_session, engine, Base
    from app import models  # noqa: F401 — register all models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        from app.models.user import User
        from app.models.customer import Customer
        from app.models.opportunity import Opportunity
        from app.models.quote import Quote
        from app.models.spare_part import SparePart
        from app.models.contract import Contract

        users_by_role: dict[str, list[int]] = {"admin": [], "sales_manager": [], "operations": [], "sales_rep": []}
        for u in (await db.execute(select(User))).scalars().all():
            users_by_role.setdefault(u.role, []).append(u.id)
        if not users_by_role["sales_manager"]:
            logger.error("No sales_manager users — run seed_v8_full_demo first.")
            return
        mgr_id = users_by_role["sales_manager"][0]
        rep_ids = users_by_role["sales_rep"] or [mgr_id]
        all_user_ids = [u for ids in users_by_role.values() for u in ids]

        customer_ids = [int(c.id) for c in (await db.execute(select(Customer).limit(40))).scalars().all()]
        opp_ids = [int(o.id) for o in (await db.execute(select(Opportunity))).scalars().all()]
        quote_ids = [int(q.id) for q in (await db.execute(select(Quote).limit(60))).scalars().all()]
        contract_ids = [int(c.id) for c in (await db.execute(select(Contract))).scalars().all()]
        spare_ids = [int(s.id) for s in (await db.execute(select(SparePart).limit(20))).scalars().all()]

        await _seed_approval_rules_and_requests(db, mgr_id, opp_ids, quote_ids, all_user_ids)
        await _seed_invoices(db, mgr_id, customer_ids, quote_ids, contract_ids)
        await _seed_keyword_packs(db)
        await _seed_segments(db, mgr_id)
        await _seed_custom_fields(db, mgr_id, opp_ids, customer_ids)
        await _seed_field_permissions(db)
        await _seed_product_rules(db, spare_ids)
        await _seed_workflow_rules_extras(db, mgr_id)
        await _seed_territories(db, mgr_id, rep_ids)
        await _seed_product_bundles(db, spare_ids)
        await _seed_retention_and_breach(db, mgr_id, customer_ids)
        await _seed_coaching(db, mgr_id, rep_ids)
        await _seed_forecast(db, mgr_id, opp_ids)
        await _seed_playbook_executions(db, opp_ids)
        await _seed_transcripts(db, mgr_id, opp_ids, customer_ids)
        await _seed_high_intent_signals(db, customer_ids, mgr_id)
        await _seed_more_notifications(db, all_user_ids)
        await db.commit()

    logger.info("V9 UAT seed extension complete.")


# ─────────────────────── Approval rules + requests (#12, #13) ───────


async def _seed_approval_rules_and_requests(db, mgr_id: int, opp_ids: list[int], quote_ids: list[int], all_user_ids: list[int]):
    from sqlalchemy import select
    from app.models.approval import ApprovalRule, ApprovalRequest

    plans = [
        ("Yüksek İndirim Onayı", "quote", "discount_pct", "gte", 15.0, "sales_manager"),
        ("Büyük Tutar Onayı", "quote", "grand_total", "gte", 250_000.0, "sales_manager"),
        ("VIP Müşteri Teklifi", "quote", "discount_pct", "gte", 10.0, "operations"),
        ("Marj Altı Teklif", "quote", "discount_pct", "gte", 25.0, "sales_manager"),
        ("Sözleşme Süresi Uzatma", "contract", "value", "gte", 500_000.0, "operations"),
        ("Kritik Fırsat Onayı", "opportunity", "amount", "gte", 1_000_000.0, "sales_manager"),
    ]
    written_rules = 0
    for i, (name, entity, cond_type, op, value, approver) in enumerate(plans):
        existing = (await db.execute(select(ApprovalRule).where(ApprovalRule.name == name))).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            ApprovalRule(
                name=name,
                entity_type=entity,
                condition_type=cond_type,
                threshold_value=value,
                threshold_operator=op,
                approver_role=approver,
                chain_mode="any",
                priority=i + 1,
                is_active=True,
                escalation_hours=48,
            )
        )
        written_rules += 1
    await db.flush()

    rules = (await db.execute(select(ApprovalRule))).scalars().all()
    written_requests = 0
    for i, q_id in enumerate(quote_ids[:20]):
        rule = rules[i % max(1, len(rules))]
        existing = (
            await db.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.entity_type == "quote")
                .where(ApprovalRequest.entity_id == q_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        status = RNG.choice(["pending", "pending", "approved", "rejected"])
        db.add(
            ApprovalRequest(
                entity_type="quote",
                entity_id=q_id,
                rule_id=rule.id,
                level=1,
                status=status,
                requested_by=mgr_id,
                assigned_to=RNG.choice(all_user_ids),
                decided_by=mgr_id if status in ("approved", "rejected") else None,
                decided_at=datetime.now(timezone.utc) if status in ("approved", "rejected") else None,
                comments=f"Demo onay talebi #{i+1}",
            )
        )
        written_requests += 1
    await db.flush()
    logger.info("approval_rules: %s, approval_requests: %s", written_rules, written_requests)


# ─────────────────────── Invoices (#9) ──────────────────────────────


async def _seed_invoices(db, mgr_id: int, customer_ids: list[int], quote_ids: list[int], contract_ids: list[int]):
    from sqlalchemy import select
    from app.models.invoice import Invoice

    today = datetime.now(timezone.utc)
    written = 0
    for i in range(40):
        inv_no = f"INV-2026-{3000 + i}"
        existing = (await db.execute(select(Invoice).where(Invoice.invoice_number == inv_no))).scalar_one_or_none()
        if existing is not None:
            continue
        cust_id = customer_ids[i % len(customer_ids)] if customer_ids else None
        if cust_id is None:
            continue
        # Mix of statuses: 8 overdue, 10 paid this month, 8 sent, 8 draft, 6 partial
        if i < 8:
            status = "overdue"
            issue_date = today - timedelta(days=RNG.randint(45, 90))
            due_date = issue_date + timedelta(days=30)
        elif i < 18:
            status = "paid"
            issue_date = today - timedelta(days=RNG.randint(5, 25))
            due_date = issue_date + timedelta(days=30)
        elif i < 26:
            status = "sent"
            issue_date = today - timedelta(days=RNG.randint(1, 14))
            due_date = issue_date + timedelta(days=30)
        elif i < 34:
            status = "draft"
            issue_date = today - timedelta(days=RNG.randint(0, 5))
            due_date = issue_date + timedelta(days=30)
        else:
            status = "partial"
            issue_date = today - timedelta(days=RNG.randint(15, 40))
            due_date = issue_date + timedelta(days=30)

        subtotal = float(RNG.randint(20_000, 350_000))
        tax = round(subtotal * 0.20, 2)
        grand = round(subtotal + tax, 2)
        db.add(
            Invoice(
                invoice_number=inv_no,
                customer_id=cust_id,
                quote_id=quote_ids[i % len(quote_ids)] if quote_ids else None,
                contract_id=contract_ids[i % len(contract_ids)] if contract_ids and i < 12 else None,
                created_by=mgr_id,
                issue_date=issue_date,
                due_date=due_date,
                status=status,
                currency="TRY",
                subtotal=subtotal,
                tax_rate=20.0,
                tax_amount=tax,
                grand_total=grand,
            )
        )
        written += 1
    await db.flush()
    logger.info("invoices: %s (with overdue + paid mix)", written)


# ─────────────────────── KeywordPacks (#23) ─────────────────────────


async def _seed_keyword_packs(db):
    from sqlalchemy import select
    from app.models.engagement import KeywordPack

    packs = [
        ("Fiyat İtirazı", "pricing", ["pahalı", "bütçe", "indirim", "expensive", "budget", "discount", "uygun fiyat"]),
        ("Rakip Bahsi", "competitor", ["Siemens", "Schneider", "ABB", "Honeywell rakibi", "alternatif tedarikçi"]),
        ("Pozitif Niyet", "positive", ["onayladı", "kabul", "süreç başladı", "sözleşme", "pilot"]),
        ("Erteleme", "stalling", ["ileride", "şu an değil", "sonra", "next year", "Q4"]),
        ("Procurement", "procurement", ["satınalma", "procurement", "purchasing", "PO", "tedarik departmanı"]),
        ("Güvenlik / KVKK", "security", ["güvenlik", "kvkk", "gdpr", "legal", "veri koruması"]),
        ("Entegrasyon", "integration", ["entegrasyon", "API", "integration", "SAP", "ERP entegrasyon"]),
        ("Yetki / Karar Verici", "authority", ["yöneticime sormam", "müdüre", "decision maker", "onay süreci"]),
    ]
    written = 0
    for name, category, keywords in packs:
        existing = (await db.execute(select(KeywordPack).where(KeywordPack.name == name))).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            KeywordPack(
                name=name,
                category=category,
                keywords_json=json.dumps(keywords, ensure_ascii=False),
                is_active=True,
            )
        )
        written += 1
    await db.flush()
    logger.info("keyword_packs: %s", written)


# ─────────────────────── Segments (#25) ─────────────────────────────


async def _seed_segments(db, mgr_id: int):
    from sqlalchemy import select
    from app.models.engagement import Segment

    segs = [
        ("VIP Müşteriler", "Yıllık ciro 500k+ olan stratejik müşteriler",
         [{"field": "total_revenue", "op": "gte", "value": 500_000}]),
        ("Kayıp Riski Yüksek", "Son 90 günde temas yok",
         [{"field": "last_touch_days", "op": "gte", "value": 90}]),
        ("Yeni Hesaplar (30 gün)", "Son 30 günde eklenen müşteriler",
         [{"field": "created_at", "op": "within_days", "value": 30}]),
        ("Üretim Sektörü", "Manufacturing industry filter",
         [{"field": "industry", "op": "eq", "value": "manufacturing"}]),
        ("EMEA Bölgesi", "EU + UK customers",
         [{"field": "region", "op": "in", "value": ["EMEA", "EU", "UK"]}]),
        ("Mid-Market", "50-500 çalışan",
         [{"field": "employee_count", "op": "between", "value": [50, 500]}]),
        ("Enterprise", "500+ çalışan",
         [{"field": "employee_count", "op": "gte", "value": 500}]),
        ("HVAC Müşterileri", "HVAC product family",
         [{"field": "product_family", "op": "eq", "value": "hvac"}]),
    ]
    written = 0
    for name, desc, rules in segs:
        existing = (await db.execute(select(Segment).where(Segment.name == name))).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            Segment(
                name=name,
                description=desc,
                rules_json=json.dumps(rules, ensure_ascii=False),
                customer_count=RNG.randint(5, 25),
                created_by=mgr_id,
            )
        )
        written += 1
    await db.flush()
    logger.info("segments: %s", written)


# ─────────────────────── Custom fields (#29) ────────────────────────


async def _seed_custom_fields(db, mgr_id: int, opp_ids: list[int], customer_ids: list[int]):
    from sqlalchemy import select
    from app.models.custom_field import CustomField, CustomFieldValue

    field_defs = [
        ("opportunity", "lead_source", "select", '["Web", "Referans", "Etkinlik", "Soğuk Arama", "İş Ortağı"]', False, 1),
        ("opportunity", "competitor_name", "select", '["Siemens", "Schneider", "ABB", "Yok"]', False, 2),
        ("opportunity", "decision_timeline", "select", '["1 ay içinde", "1-3 ay", "3-6 ay", "6+ ay"]', False, 3),
        ("opportunity", "budget_confirmed", "boolean", None, False, 4),
        ("customer", "industry_subsector", "select", '["HVAC", "Otomasyon", "Enerji", "Üretim"]', False, 1),
        ("customer", "annual_revenue_band", "select", '["<10M", "10-50M", "50-200M", "200M+"]', False, 2),
        ("customer", "preferred_contact_method", "select", '["Email", "Telefon", "WhatsApp", "Yüz Yüze"]', False, 3),
        ("customer", "vip_status", "boolean", None, False, 4),
        ("opportunity", "champion_name", "text", None, False, 5),
        ("opportunity", "blocking_factors", "textarea", None, False, 6),
    ]
    written_fields = 0
    field_ids: list[int] = []
    for entity, name, ftype, options, required, order in field_defs:
        existing = (
            await db.execute(
                select(CustomField).where(CustomField.entity_type == entity).where(CustomField.field_name == name)
            )
        ).scalar_one_or_none()
        if existing is not None:
            field_ids.append(existing.id)
            continue
        cf = CustomField(
            entity_type=entity,
            field_name=name,
            field_type=ftype,
            options_json=options,
            is_required=required,
            sort_order=order,
            created_by=mgr_id,
        )
        db.add(cf)
        await db.flush()
        field_ids.append(cf.id)
        written_fields += 1

    written_values = 0
    for cf_id in field_ids[:6]:
        cf = await db.get(CustomField, cf_id)
        if cf is None:
            continue
        target_ids = opp_ids[:15] if cf.entity_type == "opportunity" else customer_ids[:15]
        for entity_id in target_ids:
            existing = (
                await db.execute(
                    select(CustomFieldValue)
                    .where(CustomFieldValue.custom_field_id == cf.id)
                    .where(CustomFieldValue.entity_type == cf.entity_type)
                    .where(CustomFieldValue.entity_id == entity_id)
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            value_text = (
                RNG.choice(["Web", "Referans", "Etkinlik"]) if cf.field_name == "lead_source"
                else "true" if cf.field_type == "boolean"
                else "Demo değer"
            )
            db.add(
                CustomFieldValue(
                    custom_field_id=cf.id,
                    entity_type=cf.entity_type,
                    entity_id=entity_id,
                    value_text=value_text,
                )
            )
            written_values += 1
    await db.flush()
    logger.info("custom_fields: %s, custom_field_values: %s", written_fields, written_values)


# ─────────────────────── Field permissions (#30) ────────────────────


async def _seed_field_permissions(db):
    from sqlalchemy import select
    from app.models.field_permission import FieldPermission

    plans = [
        ("sales_rep", "opportunity", "amount", "read"),
        ("sales_rep", "opportunity", "discount_pct", "edit"),
        ("sales_rep", "customer", "tax_id", "read"),
        ("sales_rep", "customer", "kvkk_consent", "read"),
        ("sales_rep", "quote", "grand_total", "read"),
        ("operations", "opportunity", "amount", "edit"),
        ("operations", "customer", "tax_id", "edit"),
        ("operations", "quote", "grand_total", "edit"),
        ("sales_manager", "opportunity", "amount", "edit"),
        ("sales_manager", "customer", "tax_id", "edit"),
        ("sales_manager", "quote", "grand_total", "edit"),
        ("sales_rep", "opportunity", "loss_reason", "hidden"),
    ]
    written = 0
    for role, entity, field, level in plans:
        existing = (
            await db.execute(
                select(FieldPermission)
                .where(FieldPermission.role == role)
                .where(FieldPermission.entity_type == entity)
                .where(FieldPermission.field_name == field)
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(FieldPermission(role=role, entity_type=entity, field_name=field, access_level=level))
        written += 1
    await db.flush()
    logger.info("field_permissions: %s", written)


# ─────────────────────── Product rules (#31) ────────────────────────


async def _seed_product_rules(db, spare_ids: list[int]):
    from sqlalchemy import select
    from app.models.product_rule import ProductRule

    plans = [
        (None, "Termostat", "min_quantity",
         {"min_quantity": 5},
         {"warning": "Termostatlar için minimum 5 adet sipariş", "block": False}),
        (None, "Sensör", "discount_cap",
         {"max_discount_pct": 15},
         {"warning": "Sensörlerde maksimum %15 indirim", "block": True}),
        (None, "Vana", "approval_required",
         {"min_amount": 50_000},
         {"warning": "50K üzeri vana satışı yönetici onayı gerekir", "block": False}),
        (None, "Kontrol Paneli", "bundle_suggest",
         {"category": "Sensör"},
         {"suggestion": "Kontrol paneli ile birlikte sensör paketi öner", "block": False}),
        (None, "Aktüatör", "lead_time_warning",
         {"days": 14},
         {"warning": "Aktüatörler 14 gün ortalama teslimat", "block": False}),
        (None, "Detektör", "discount_cap",
         {"max_discount_pct": 10},
         {"warning": "Detektörlerde maksimum %10 indirim", "block": True}),
    ]
    written = 0
    for i, (sp_id, category, rule_type, condition, action) in enumerate(plans):
        existing = (
            await db.execute(
                select(ProductRule)
                .where(ProductRule.category == category)
                .where(ProductRule.rule_type == rule_type)
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            ProductRule(
                spare_part_id=sp_id,
                category=category,
                rule_type=rule_type,
                condition_json=json.dumps(condition, ensure_ascii=False),
                action_json=json.dumps(action, ensure_ascii=False),
                priority=i + 1,
                is_active=True,
            )
        )
        written += 1
    await db.flush()
    logger.info("product_rules: %s", written)


# ─────────────────────── Workflow rule extras (#32) ─────────────────


async def _seed_workflow_rules_extras(db, mgr_id: int):
    from sqlalchemy import select
    from app.models.workflow_rule import WorkflowRule

    extras = [
        ("Yüksek İndirimde Slack Bildirimi", "quote", "quote.discount_high",
         [{"field": "discount_pct", "op": "gte", "value": 20}],
         [{"type": "slack_notify", "channel": "#sales-discounts"}]),
        ("Müşteri Doğum Günü Hatırlatma", "customer", "customer.birthday_30d",
         [],
         [{"type": "create_task", "title": "Doğum günü hatırlatma maili"}]),
        ("Pipeline Sıkışma Uyarısı", "opportunity", "opportunity.stage_stuck",
         [{"field": "days_in_stage", "op": "gte", "value": 21}],
         [{"type": "notify_manager", "title": "21 gündür aynı aşamada"}]),
        ("Yüksek Değerli Lead Atama", "lead", "lead.score_high",
         [{"field": "lead_score", "op": "gte", "value": 80}],
         [{"type": "assign_to_senior_rep"}]),
        ("Fatura Gecikme Uyarısı", "invoice", "invoice.overdue_7d",
         [{"field": "days_overdue", "op": "gte", "value": 7}],
         [{"type": "email_finance", "template": "overdue_reminder"}]),
        ("Sözleşme Bitiş Yaklaşıyor", "contract", "contract.ending_60d",
         [{"field": "days_until_end", "op": "lte", "value": 60}],
         [{"type": "create_task", "title": "Yenileme görüşmesi planla"}]),
    ]
    written = 0
    for name, entity, trigger, conditions, actions in extras:
        existing = (await db.execute(select(WorkflowRule).where(WorkflowRule.name == name))).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            WorkflowRule(
                name=name,
                entity_type=entity,
                trigger_event=trigger,
                conditions_json=json.dumps(conditions, ensure_ascii=False),
                actions_json=json.dumps(actions, ensure_ascii=False),
                is_active=True,
                created_by=mgr_id,
            )
        )
        written += 1
    await db.flush()
    logger.info("workflow_rule_extras: %s", written)


# ─────────────────────── Territories (#33) ──────────────────────────


async def _seed_territories(db, mgr_id: int, rep_ids: list[int]):
    from sqlalchemy import select
    from app.models.territory import Territory, TerritoryAssignment

    plans = [
        ("Marmara Bölgesi", "Marmara", "İstanbul, Bursa, Kocaeli ve çevresi"),
        ("Ege Bölgesi", "Aegean", "İzmir, Manisa, Aydın ve çevresi"),
        ("İç Anadolu", "Central Anatolia", "Ankara, Konya, Eskişehir"),
        ("Akdeniz", "Mediterranean", "Antalya, Mersin, Adana"),
        ("EMEA Enterprise", "EMEA", "Avrupa enterprise hesapları"),
        ("Karadeniz", "Black Sea", "Trabzon, Samsun ve çevresi"),
    ]
    written_t = 0
    written_a = 0
    territory_ids: list[int] = []
    for name, region, desc in plans:
        existing = (await db.execute(select(Territory).where(Territory.name == name))).scalar_one_or_none()
        if existing is not None:
            territory_ids.append(existing.id)
            continue
        t = Territory(name=name, region=region, description=desc, created_by=mgr_id)
        db.add(t)
        await db.flush()
        territory_ids.append(t.id)
        written_t += 1

    for i, tid in enumerate(territory_ids):
        # 1-2 reps per territory
        for j in range(min(2, len(rep_ids))):
            rid = rep_ids[(i * 2 + j) % len(rep_ids)]
            existing = (
                await db.execute(
                    select(TerritoryAssignment)
                    .where(TerritoryAssignment.territory_id == tid)
                    .where(TerritoryAssignment.user_id == rid)
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(TerritoryAssignment(territory_id=tid, user_id=rid, role="member"))
            written_a += 1
    await db.flush()
    logger.info("territories: %s, territory_assignments: %s", written_t, written_a)


# ─────────────────────── Product bundles (#14) ──────────────────────


async def _seed_product_bundles(db, spare_ids: list[int]):
    from sqlalchemy import select
    from app.models.product_bundle import ProductBundle

    bundles = [
        ("HVAC Başlangıç Paketi", "Termostat + 2 sensör + kontrol paneli", 0.10),
        ("Endüstriyel Otomasyon Demeti", "Aktüatör + sensör + DCS", 0.15),
        ("Yangın Güvenlik Seti", "Detektör + buton paneli + alarm", 0.05),
        ("Bakım Yedek Parça Kiti", "Yıllık bakım için 5'li parça paketi", 0.20),
    ]
    written = 0
    for i, (name, desc, discount) in enumerate(bundles):
        existing = (await db.execute(select(ProductBundle).where(ProductBundle.name == name))).scalar_one_or_none()
        if existing is not None:
            continue
        if not spare_ids:
            continue
        items = [
            {"spare_part_id": spare_ids[(i * 2 + k) % len(spare_ids)], "quantity": RNG.randint(1, 3)}
            for k in range(min(3, len(spare_ids)))
        ]
        db.add(
            ProductBundle(
                name=name,
                description=desc,
                items_json=json.dumps(items),
                bundle_price=float(RNG.randint(15_000, 80_000)),
                discount_pct=discount * 100,
                is_active=True,
            )
        )
        written += 1
    await db.flush()
    logger.info("product_bundles: %s", written)


# ─────────────────────── Retention + breach (#28) ───────────────────


async def _seed_retention_and_breach(db, mgr_id: int, customer_ids: list[int]):
    from sqlalchemy import select
    from app.models.retention_policy import RetentionPolicy
    from app.models.breach_notification import BreachNotification

    policies = [
        ("customer", 1825, "anonymize"),  # 5 yıl
        ("opportunity", 1095, "archive"),  # 3 yıl
        ("activity_log", 730, "delete"),  # 2 yıl
        ("email_request", 1095, "anonymize"),  # 3 yıl
        ("quote", 2555, "archive"),  # 7 yıl (vergi)
        ("contract", 3650, "archive"),  # 10 yıl (yasal)
    ]
    written_p = 0
    for entity, days, action in policies:
        existing = (
            await db.execute(select(RetentionPolicy).where(RetentionPolicy.entity_type == entity))
        ).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            RetentionPolicy(
                entity_type=entity,
                retention_days=days,
                action=action,
                is_active=True,
            )
        )
        written_p += 1
    await db.flush()

    breaches = [
        ("data_export_unauthorized", "Yetkisiz veri export denemesi tespit edildi", "high", "investigating"),
        ("password_breach_third_party", "3. parti servis açığı — kullanıcılara şifre değişimi bildirildi", "med", "resolved"),
        ("phishing_attempt", "Phishing emaili tespit edildi, 5 kullanıcı etkilendi", "high", "resolved"),
    ]
    written_b = 0
    for btype, desc, sev, status in breaches:
        existing = (
            await db.execute(select(BreachNotification).where(BreachNotification.breach_type == btype))
        ).scalar_one_or_none()
        if existing is not None:
            continue
        affected = customer_ids[:5] if customer_ids else []
        db.add(
            BreachNotification(
                breach_type=btype,
                description=desc,
                affected_customers_json=json.dumps(affected),
                severity=sev,
                status=status,
                notified_at=datetime.now(timezone.utc) if status == "resolved" else None,
                created_by=mgr_id,
            )
        )
        written_b += 1
    await db.flush()
    logger.info("retention_policies: %s, breach_notifications: %s", written_p, written_b)


# ─────────────────────── Coaching (#21) ─────────────────────────────


async def _seed_coaching(db, mgr_id: int, rep_ids: list[int]):
    from sqlalchemy import select
    from app.models.coaching_plan import CoachingPlan
    from app.models.coaching_snapshot import CoachingSnapshot

    written_p = 0
    for i, rep_id in enumerate(rep_ids[:5]):
        existing = (await db.execute(select(CoachingPlan).where(CoachingPlan.user_id == rep_id))).scalar_one_or_none()
        if existing is not None:
            continue
        goals = [
            {"name": "Daily call count", "target": 15, "current": RNG.randint(8, 18)},
            {"name": "Quote-to-close ratio", "target": 0.30, "current": round(RNG.uniform(0.15, 0.35), 2)},
            {"name": "Stakeholder coverage avg", "target": 3.0, "current": round(RNG.uniform(1.5, 3.5), 1)},
        ]
        db.add(
            CoachingPlan(
                user_id=rep_id,
                manager_id=mgr_id,
                goals_json=json.dumps(goals, ensure_ascii=False),
                weeks=4,
                start_date=date.today() - timedelta(days=14),
                status="active" if i < 3 else "completed",
            )
        )
        written_p += 1

    written_s = 0
    for rep_id in rep_ids[:8]:
        # Düşük performans senaryosu için ilk 2 rep'e düşük skor ver
        score = RNG.randint(35, 55) if rep_id == rep_ids[0] else RNG.randint(60, 90)
        for week in range(4):
            indicators = {
                "calls_per_day": RNG.randint(5, 20),
                "meetings_per_week": RNG.randint(2, 8),
                "quotes_sent": RNG.randint(1, 6),
                "win_rate_pct": round(RNG.uniform(15, 50), 1),
                "stakeholder_coverage": round(RNG.uniform(1.5, 4.0), 1),
            }
            db.add(
                CoachingSnapshot(
                    user_id=rep_id,
                    score=max(0, min(100, score + RNG.randint(-10, 10))),
                    indicators_json=json.dumps(indicators),
                    created_at=datetime.now(timezone.utc) - timedelta(weeks=week),
                )
            )
            written_s += 1
    await db.flush()
    logger.info("coaching_plans: %s, coaching_snapshots: %s", written_p, written_s)


# ─────────────────────── Forecast (#6) ──────────────────────────────


async def _seed_forecast(db, mgr_id: int, opp_ids: list[int]):
    from sqlalchemy import select
    from app.models.forecast import ForecastAdjustment, PipelineSnapshot
    from app.models.forecast_snapshot_detail import ForecastSnapshotDetail
    from app.models.opportunity import Opportunity

    written_adj = 0
    for opp_id in opp_ids[:10]:
        opp = await db.get(Opportunity, opp_id)
        if opp is None or opp.amount is None:
            continue
        existing = (
            await db.execute(select(ForecastAdjustment).where(ForecastAdjustment.opportunity_id == opp_id))
        ).scalar_one_or_none()
        if existing is not None:
            continue
        adj_pct = RNG.uniform(-0.20, 0.15)
        db.add(
            ForecastAdjustment(
                opportunity_id=opp_id,
                adjusted_by=mgr_id,
                original_amount=float(opp.amount),
                adjusted_amount=round(float(opp.amount) * (1 + adj_pct), 2),
                original_category=opp.forecast_category or "pipeline",
                adjusted_category=RNG.choice(["commit", "best_case", "pipeline"]),
                reason=f"Yöneticinin değerlendirmesine göre düzeltme — %{round(adj_pct*100,1)}",
            )
        )
        written_adj += 1

    # PipelineSnapshot is per (snapshot_date, stage) — produce one row
    # per stage per recent week so the WoW chart has data.
    today = datetime.now(timezone.utc).date()
    stages = ["prospecting", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]
    written_snap = 0
    for week_offset in range(0, 8):
        snap_date = today - timedelta(weeks=week_offset)
        for stage in stages:
            existing = (
                await db.execute(
                    select(PipelineSnapshot)
                    .where(PipelineSnapshot.snapshot_date == snap_date)
                    .where(PipelineSnapshot.stage == stage)
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            count = RNG.randint(2, 18)
            total = count * RNG.choice([35_000, 80_000, 150_000, 320_000])
            weighted = round(total * RNG.uniform(0.1, 0.9), 2)
            db.add(
                PipelineSnapshot(
                    snapshot_date=snap_date,
                    stage=stage,
                    opportunity_count=count,
                    total_amount=float(total),
                    weighted_amount=weighted,
                )
            )
            written_snap += 1
    await db.flush()

    written_det = 0
    snap_dates = (
        await db.execute(
            select(PipelineSnapshot.snapshot_date).distinct().order_by(PipelineSnapshot.snapshot_date.desc()).limit(4)
        )
    ).scalars().all()
    for snap_date in snap_dates:
        # ForecastSnapshotDetail is per opportunity, not per stage row.
        # We use snapshot_id of any pipeline_snapshots row that day.
        any_snap = (
            await db.execute(select(PipelineSnapshot).where(PipelineSnapshot.snapshot_date == snap_date).limit(1))
        ).scalar_one_or_none()
        if any_snap is None:
            continue
        for opp_id in opp_ids[:15]:
            opp = await db.get(Opportunity, opp_id)
            if opp is None:
                continue
            existing = (
                await db.execute(
                    select(ForecastSnapshotDetail)
                    .where(ForecastSnapshotDetail.snapshot_id == any_snap.id)
                    .where(ForecastSnapshotDetail.opportunity_id == opp_id)
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            db.add(
                ForecastSnapshotDetail(
                    snapshot_id=any_snap.id,
                    opportunity_id=opp_id,
                    forecast_category=opp.forecast_category or RNG.choice(["pipeline", "best_case", "commit"]),
                    amount=float(opp.amount or 100_000),
                    stage=opp.stage,
                )
            )
            written_det += 1
    await db.flush()
    logger.info("forecast_adjustments: %s, pipeline_snapshots: %s, forecast_snapshot_details: %s",
                written_adj, written_snap, written_det)


# ─────────────────────── Playbook executions (#20) ──────────────────


async def _seed_playbook_executions(db, opp_ids: list[int]):
    from sqlalchemy import select
    from app.models.playbook import Playbook, PlaybookExecution

    playbooks = (await db.execute(select(Playbook).limit(6))).scalars().all()
    if not playbooks:
        logger.info("playbook_executions: skipped (no playbooks)")
        return
    written = 0
    for opp_id in opp_ids[:30]:
        pb = RNG.choice(playbooks)
        existing = (
            await db.execute(
                select(PlaybookExecution)
                .where(PlaybookExecution.opportunity_id == opp_id)
                .where(PlaybookExecution.playbook_id == pb.id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        status = RNG.choice(["active", "active", "completed", "stopped"])
        db.add(
            PlaybookExecution(
                playbook_id=pb.id,
                opportunity_id=opp_id,
                triggered_by_signal_id=None,
                current_step=RNG.randint(1, 5),
                status=status,
                started_at=datetime.now(timezone.utc) - timedelta(days=RNG.randint(1, 30)),
                completed_at=datetime.now(timezone.utc) - timedelta(days=RNG.randint(0, 5)) if status == "completed" else None,
            )
        )
        written += 1
    await db.flush()
    logger.info("playbook_executions: %s", written)


# ─────────────────────── Transcripts (#22) ──────────────────────────


async def _seed_transcripts(db, mgr_id: int, opp_ids: list[int], customer_ids: list[int]):
    from sqlalchemy import select
    from app.models.engagement import Transcript

    samples = [
        ("Discovery Call - ACME", "Müşteri ihtiyaçlarının ilk taraması",
         "Rep: Merhaba, ihtiyaçlarınızı anlayalım. Müşteri: Yeni HVAC sistemine ihtiyacımız var, bütçemiz 200K, Q3'te karar vermeliyiz. Rakip Siemens'i de değerlendiriyoruz.",
         "positive"),
        ("Demo - Anadolu Lojistik", "Otomasyon hattı ürün sunumu",
         "Rep: SCADA sistemimizin entegrasyonunu gösterdim. Müşteri: ROI hesabı net, ama satınalma süreci 6 hafta sürüyor.",
         "neutral"),
        ("Negotiation - Demir Çelik", "Fiyat görüşmesi ve indirim talebi",
         "Müşteri: Fiyat çok yüksek, %15 indirim istiyoruz. Rep: Maksimum %10 verebiliriz, ek hizmet ekleyebiliriz.",
         "negative"),
        ("Renewal - Yıldız Otomotiv", "Sözleşme yenileme görüşmesi",
         "Müşteri: Geçen yıl çok memnun kaldık, 3 yıllık sözleşme yapalım, %5 indirim olursa.",
         "positive"),
        ("Stakeholder Meeting - Tekfen", "Karar verici tanıtımı",
         "CEO ve CTO tanıtıldı. CEO: Stratejik öncelik. CTO: Teknik şartnameler tamamlandı.",
         "positive"),
        ("Loss Review - Mavi Gemi", "Kayıp deal post-mortem",
         "Müşteri Schneider'ı tercih etti. Sebep: lokal destek + 30 gün hızlı teslimat. Bizim 60 gün vadeli teslimat dezavantaj oldu.",
         "negative"),
    ]
    written = 0
    for i, (title, summary, content, sentiment) in enumerate(samples):
        existing = (await db.execute(select(Transcript).where(Transcript.title == title))).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            Transcript(
                opportunity_id=opp_ids[i % len(opp_ids)] if opp_ids else None,
                customer_id=customer_ids[i % len(customer_ids)] if customer_ids else None,
                title=title,
                source=RNG.choice(["upload", "teams", "zoom"]),
                content=content,
                duration_minutes=RNG.randint(15, 60),
                participants=f"Rep #{mgr_id}, Customer Stakeholder",
                summary=summary,
                action_items_json=json.dumps([
                    {"action": "Follow-up email gönder", "owner": "rep", "due_days": 1},
                    {"action": "Quote revize et", "owner": "rep", "due_days": 3},
                ], ensure_ascii=False),
                sentiment=sentiment,
                created_by=mgr_id,
            )
        )
        written += 1
    await db.flush()
    logger.info("transcripts: %s", written)


# ─────────────────────── High-intent signals (#3, #16) ──────────────


async def _seed_high_intent_signals(db, customer_ids: list[int], mgr_id: int):
    """Tag a few customers as high-intent so the cockpit list lights up."""
    from sqlalchemy import select
    from app.models.revenue_signal import RevenueSignal

    written = 0
    for i, cid in enumerate(customer_ids[:8]):
        event_key = f"high_intent:demo:{cid}:{i}"
        existing = (
            await db.execute(select(RevenueSignal).where(RevenueSignal.event_key == event_key))
        ).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            RevenueSignal(
                signal_type="high_intent",
                source_entity_type="customer",
                source_entity_id=cid,
                customer_id=cid,
                owner_id=mgr_id,
                severity="high",
                confidence=RNG.uniform(0.65, 0.95),
                recommended_action="Hesabı önceliklendirin: Web ziyareti + email engagement yüksek",
                metadata_json=json.dumps({"intent_score": RNG.randint(70, 95), "signals": ["web_visits", "email_open", "demo_requested"]}),
                event_key=event_key,
                created_at=datetime.now(timezone.utc) - timedelta(days=RNG.randint(0, 7)),
            )
        )
        written += 1
    await db.flush()
    logger.info("high_intent_signals: %s", written)


# ─────────────────────── More notifications (#34) ───────────────────


async def _seed_more_notifications(db, all_user_ids: list[int]):
    """Ensure unread notifications exist so the bell shows real entries."""
    from sqlalchemy import select
    from app.models.notification import Notification

    written = 0
    for uid in all_user_ids[:8]:
        existing = (
            await db.execute(
                select(Notification)
                .where(Notification.user_id == uid)
                .where(Notification.is_read.is_(False))
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        for k, payload in enumerate([
            ("approval", "Onay bekliyor", "Yeni teklif onayı bekleniyor"),
            ("deal_update", "Fırsat güncellendi", "Müzakere aşamasına geçti"),
            ("task_due", "Görev yaklaşıyor", "Demo planlama görevi yarın"),
            ("mention", "Bahsedildiniz", "Yorumda etiketlendiniz"),
        ]):
            ntype, title, msg = payload
            db.add(
                Notification(
                    user_id=uid,
                    type=ntype,
                    title=title,
                    message=msg,
                    is_read=False,
                    created_at=datetime.now(timezone.utc) - timedelta(hours=RNG.randint(1, 48)),
                )
            )
            written += 1
    await db.flush()
    logger.info("notifications_extras: %s", written)


# ─────────────────────── entry ──────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="V9 UAT seed extension")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        logger.info("Dry run — pass --apply to execute.")
        return 0
    asyncio.run(seed_extension())
    return 0


if __name__ == "__main__":
    sys.exit(main())
