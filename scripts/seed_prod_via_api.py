"""Prod data seeder via HTTP API.

Creates missing mock data on production by calling the running API.
Idempotent-ish: skips creation if endpoint returns 4xx conflict.

Usage:
    python scripts/seed_prod_via_api.py \
        --base-url https://honeywell-backend.onrender.com/api/v1 \
        --admin-email admin@honeywell.com \
        --admin-password 'Honeywell2026!'
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
log = logging.getLogger("seed_prod")

NOW = datetime.now(timezone.utc)


class ApiClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def login_as(self, email: str, password: str) -> str:
        r = requests.post(
            f"{self.base_url}/auth/login",
            data={"username": email, "password": password},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["access_token"]

    def get(self, path: str, params: dict | None = None) -> Any:
        r = self.session.get(f"{self.base_url}{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, payload: dict) -> Any:
        r = self.session.post(f"{self.base_url}{path}", json=payload, timeout=30)
        if r.status_code >= 400:
            log.warning("POST %s failed %d: %s", path, r.status_code, r.text[:200])
            return None
        return r.json()

    def patch(self, path: str, payload: dict) -> Any:
        r = self.session.patch(f"{self.base_url}{path}", json=payload, timeout=30)
        if r.status_code >= 400:
            log.warning("PATCH %s failed %d: %s", path, r.status_code, r.text[:200])
            return None
        return r.json()


def login(base_url: str, email: str, password: str) -> str:
    r = requests.post(
        f"{base_url}/auth/login",
        data={"username": email, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def seed_leads(api: ApiClient) -> None:
    existing = api.get("/leads/?page=1&page_size=1").get("total", 0)
    if existing > 0:
        log.info("leads: %d already exist, skipping", existing)
        return

    leads_data = [
        ("Burak", "Yilmaz", "burak@istanbulmakina.com", "+90 212 555 1001", "Istanbul Makina", "website", "new", 75),
        ("Selin", "Kaya", "selin@anadoluotomasyon.com", "+90 216 555 1002", "Anadolu Otomasyon", "referral", "contacted", 85),
        ("Emre", "Celik", "emre@bursaend.com", "+90 224 555 1003", "Bursa Endustri", "email_campaign", "qualified", 92),
        ("Ayse", "Demir", "ayse@kocaelihvac.com", "+90 262 555 1004", "Kocaeli HVAC", "website", "contacted", 68),
        ("Mehmet", "Ozturk", "mehmet@izmirtermal.com", "+90 232 555 1005", "Izmir Termal", "event", "qualified", 88),
        ("Zeynep", "Arslan", "zeynep@ankaraprosess.com", "+90 312 555 1006", "Ankara Proses", "referral", "new", 55),
    ]
    created = 0
    for first, last, email, phone, company, source, status, score in leads_data:
        res = api.post("/leads/", {
            "first_name": first,
            "last_name": last,
            "email": email,
            "phone": phone,
            "company": company,
            "source": source,
            "status": status,
            "lead_score": score,
        })
        if res:
            created += 1
    log.info("leads: created %d", created)


def seed_campaigns(api: ApiClient) -> None:
    existing = api.get("/campaigns/?page=1&page_size=1")
    items = existing.get("items", []) if isinstance(existing, dict) else []
    total = existing.get("total", len(items)) if isinstance(existing, dict) else len(items)
    if total > 0:
        log.info("campaigns: %d already exist, skipping", total)
        return

    campaigns_data = [
        ("2026 Q1 Yedek Parca Kampanyasi", "email", "active", "Muhendislik sirketleri icin yedek parca indirimleri", 50000, 125000),
        ("HVAC Bahar Sezonu Promosyonu", "event", "active", "Bahar sezonu HVAC sistemi yenileme", 75000, 220000),
        ("Otomasyon Cozumleri Webinar", "webinar", "completed", "PLC ve DCS cozumleri tanitim webinari", 15000, 95000),
    ]
    created = 0
    now = NOW.date()
    for name, ctype, status, desc, budget, expected_rev in campaigns_data:
        res = api.post("/campaigns/", {
            "name": name,
            "type": ctype,
            "status": status,
            "description": desc,
            "budget": budget,
            "expected_revenue": expected_rev,
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=90)).isoformat(),
        })
        if res:
            created += 1
    log.info("campaigns: created %d", created)


def seed_subscriptions(api: ApiClient) -> None:
    existing = api.get("/subscriptions/?page=1&page_size=1")
    total = existing.get("total", 0) if isinstance(existing, dict) else 0
    if total > 0:
        log.info("subscriptions: %d already exist, skipping", total)
        return

    # Fetch customers for subscriptions
    customers = api.get("/customers/?page=1&page_size=50").get("items", [])
    if not customers:
        log.warning("no customers for subscriptions")
        return

    created = 0
    for i, c in enumerate(customers[:5]):
        res = api.post("/subscriptions/", {
            "customer_id": c["id"],
            "plan_name": f"Bakim Paketi {['Bronz','Gumus','Altin','Platin','Kurumsal'][i]}",
            "mrr": 5000 + i * 2500,
            "currency": "TRY",
            "status": "active",
            "start_date": NOW.date().isoformat(),
            "billing_cycle": "monthly",
        })
        if res:
            created += 1
    log.info("subscriptions: created %d", created)


def seed_invoices(api: ApiClient) -> None:
    existing = api.get("/invoices/?page=1&page_size=1")
    total = existing.get("total", 0) if isinstance(existing, dict) else 0
    if total > 0:
        log.info("invoices: %d already exist, skipping", total)
        return

    customers = api.get("/customers/?page=1&page_size=10").get("items", [])
    if not customers:
        log.warning("no customers for invoices")
        return

    created = 0
    for i, c in enumerate(customers[:4]):
        res = api.post("/invoices/", {
            "customer_id": c["id"],
            "issue_date": NOW.date().isoformat(),
            "due_date": (NOW.date() + timedelta(days=30)).isoformat(),
            "status": ["draft", "sent", "paid", "overdue"][i],
            "currency": "TRY",
            "subtotal": 10000 + i * 5000,
            "tax_rate": 18,
            "tax_amount": (10000 + i * 5000) * 0.18,
            "grand_total": (10000 + i * 5000) * 1.18,
            "notes": f"Mock fatura #{i+1}",
            "items_json": "[]",
        })
        if res:
            created += 1
    log.info("invoices: created %d", created)


def seed_dashboards(api: ApiClient) -> None:
    existing = api.get("/dashboards/")
    data = existing.get("data", []) if isinstance(existing, dict) else []
    if len(data) > 0:
        log.info("dashboards: %d already exist, skipping", len(data))
        return

    dashboards_data = [
        ("Satis Genel Bakis", [
            {"type": "kpi", "position": {"x": 0, "y": 0, "w": 6, "h": 2}, "report_id": None},
            {"type": "chart", "position": {"x": 6, "y": 0, "w": 6, "h": 4}, "report_id": None},
        ]),
        ("Rep Performans", [
            {"type": "leaderboard", "position": {"x": 0, "y": 0, "w": 6, "h": 4}, "report_id": None},
            {"type": "chart", "position": {"x": 6, "y": 0, "w": 6, "h": 4}, "report_id": None},
        ]),
    ]
    created = 0
    import json as json_mod
    for name, widgets in dashboards_data:
        res = api.post("/dashboards/", {
            "name": name,
            "widgets_json": json_mod.dumps(widgets),
        })
        if res:
            created += 1
    log.info("dashboards: created %d", created)


def seed_revenue_schedules(api: ApiClient) -> None:
    existing = api.get("/revenue-schedules/")
    schedules = existing.get("schedules", []) if isinstance(existing, dict) else []
    if len(schedules) > 0:
        log.info("revenue-schedules: %d already exist, skipping", len(schedules))
        return

    contracts = api.get("/contracts/?page=1&page_size=10")
    citems = contracts.get("items", []) if isinstance(contracts, dict) else []
    if not citems:
        log.warning("no contracts for revenue schedules")
        return

    created = 0
    for i, c in enumerate(citems[:2]):
        total = 180000 + i * 60000
        res = api.post("/revenue-schedules/", {
            "contract_id": c["id"],
            "recognition_type": "straight_line",
            "start_date": NOW.date().isoformat(),
            "end_date": (NOW.date() + timedelta(days=180)).isoformat(),
            "total_amount": total,
            "currency": "TRY",
        })
        if res:
            created += 1
            # Trigger entry generation
            api.post(f"/revenue-schedules/{res['id']}/generate-entries", {})
    log.info("revenue-schedules: created %d", created)


def seed_playbooks(api: ApiClient) -> None:
    existing = api.get("/playbooks/?page=1&page_size=1")
    total = existing.get("total", 0) if isinstance(existing, dict) else 0
    if total > 0:
        log.info("playbooks: %d already exist, skipping", total)
        return

    playbooks_data = [
        ("Yeni Firsat - Kalifikasyon", "opportunity", "Firsat ilk olusturulduktan sonra nitelendirme adimlari", [
            "Karar vericiyi belirle",
            "Butceyi dogrula",
            "Timing'i netlestir",
            "Rakip durumunu degerlendir",
        ]),
        ("Teklif Sonrasi Takip", "quote", "Teklif gonderildikten sonraki 7 gun", [
            "1. gun: Onay teyit maili",
            "3. gun: Goruselme teklifi",
            "7. gun: Son nokta takip",
        ]),
        ("Fiyat Itirazi Yanit Klavuzu", "opportunity", "Musteri fiyat itirazi geldiginde kullanilacak", [
            "Deger propozisyonunu hatirlat",
            "TCO analizi sun",
            "Referans musteri hikayesi paylas",
        ]),
    ]
    created = 0
    for name, trigger, desc, steps in playbooks_data:
        res = api.post("/playbooks/", {
            "name": name,
            "trigger_entity": trigger,
            "description": desc,
            "steps_json": str(steps).replace("'", '"'),
            "is_active": True,
        })
        if res:
            created += 1
    log.info("playbooks: created %d", created)


def seed_coaching_plans(api: ApiClient) -> None:
    existing = api.get("/coaching-plans/?page=1&page_size=1")
    total = existing.get("total", 0) if isinstance(existing, dict) else 0
    if total > 0:
        log.info("coaching-plans: %d already exist, skipping", total)
        return

    # Need a sales rep user id
    users = api.get("/users/?page=1&page_size=10").get("items", [])
    rep = next((u for u in users if u["role"] == "sales_rep"), None)
    if not rep:
        log.warning("no sales_rep for coaching plan")
        return

    plans = [
        ("Q1 Hedef: Win Rate %50+", "Temsilcinin kazanma oranini artirmaya yonelik haftalik aktiviteler", [
            {"title": "Haftada 5 yeni discovery call", "done": False, "target_date": None},
            {"title": "Her firsatta karar vericiyi belirle", "done": False, "target_date": None},
        ]),
        ("Buyuk Musteri Yonetimi", "Kilit hesaplar icin ayliklik rutin", [
            {"title": "Aylik QBR toplantisi", "done": False, "target_date": None},
            {"title": "Yillik genisleme plani olustur", "done": False, "target_date": None},
        ]),
    ]
    created = 0
    for title, desc, goals in plans:
        import json as json_mod
        res = api.post("/coaching-plans/", {
            "rep_id": rep["id"],
            "title": title,
            "description": desc,
            "goals_json": json_mod.dumps(goals),
            "status": "active",
        })
        if res:
            created += 1
    log.info("coaching-plans: created %d", created)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    args = parser.parse_args()

    log.info("Logging in as %s", args.admin_email)
    token = login(args.base_url, args.admin_email, args.admin_password)
    log.info("Token obtained")

    api = ApiClient(args.base_url, token)

    seeders = [
        ("leads", seed_leads),
        ("campaigns", seed_campaigns),
        ("subscriptions", seed_subscriptions),
        ("invoices", seed_invoices),
        ("playbooks", seed_playbooks),
        ("coaching_plans", seed_coaching_plans),
        ("revenue_schedules", seed_revenue_schedules),
        ("dashboards", seed_dashboards),
    ]

    for name, fn in seeders:
        try:
            log.info("--- Seeding %s ---", name)
            fn(api)
        except Exception as e:
            log.exception("seeder %s failed: %s", name, e)

    log.info("Done.")


if __name__ == "__main__":
    sys.exit(main())
