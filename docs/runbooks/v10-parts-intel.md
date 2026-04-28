# V10 Spare Parts Intelligence — Operations Runbook

V10 kapsamı (read-only derivation layer):
- ``services/parts_intelligence_service.py`` — velocity Pareto +
  demand heatmap + dead stock ledger
- ``services/parts_pricing_intel_service.py`` — inflation tax
  projection + stale pricing + margin health
- ``services/parts_obsolescence_watch_service.py`` — EOL risk
  scoring + last-time-buy candidates
- ``services/parts_data_quality_service.py`` — master data health
  + duplicate detection + orphan PriceEntry
- ``services/parts_substitution_service.py`` — quote-revision-tree
  swap patterns + cross-customer demand + segment affinity
- ``api/v1/v10_parts_intel.py`` — 16 read-only endpoint
- ``frontend/src/features/parts-intel/PartsIntelligenceDashboardPage.tsx``
  — manager-only dashboard
- ``FEATURE_V10_PARTS_INTEL`` — default false

V10 **schema değiştirmiyor**. SparePart tablosu Excel-import-driven
ve company-unique; V10 sadece var olan SparePart × PriceEntry ×
QuoteItem × Quote × Opportunity üzerinde derivation yapar.

---

## 0) Aktivasyon

```bash
# Render dashboard → honeywell-backend → Environment
FEATURE_V10_PARTS_INTEL=true
# Save → Auto-deploy
```

Aktive olduktan sonra:
- ``/api/v1/v10/parts-intel/*`` endpoint'leri 200 döner
- Frontend'de "Parça Zekâsı" sidebar entry'si manager+admin için görünür
- Backend'de yeni cron yok, ek dependency yok

Rollback: ``FEATURE_V10_PARTS_INTEL=false`` — endpoint'ler 404
döner, dashboard "Bu özellik henüz açık değil" empty state gösterir.

---

## 1) Doğrulama (smoke test)

```bash
TOKEN=$(curl -sX POST $API/auth/login -d '{"email":"...","password":"..."}' | jq -r .access_token)

# Summary endpoint — manager gerekli
curl -s -H "Authorization: Bearer $TOKEN" $API/v1/v10/parts-intel/summary | jq

# Beklenen yapı:
# {
#   "generated_at": "2026-04-28T...",
#   "tier_counts": {"A": 12, "B": 30, "C": 80},
#   "dead_stock_count": 25,
#   "frozen_capital_total": 124500.0,
#   "heatmap_months_covered": 6,
#   "total_active_parts": 122
# }
```

---

## 2) Operasyonel ipuçları

### Donmuş sermaye değerleri makul mü?
``frozen_capital_total = sum(supplier_price)`` — supplier_price
NULL olan parçalar 0 sayılır. Tutar şişiyorsa:
1. ``GET /v10/parts-intel/dead-stock?limit=500`` ile listeyi al
2. ``supplier_price`` doğru mu spot-check et (en yüksek 10 row)
3. Excel import şablonunda ``supplier_price`` alanı doldurulmamış
   olabilir — data quality endpoint'iyle kontrol:
   ``GET /v10/parts-intel/data-health``

### EOL risk skoru anormal yüksek
``obsolescence-watch`` her parçayı 4 driver'dan değerlendirir
(inactivity / missing_fields / price_age / quote_freq_decay).
Yeni import sonrası tüm parçalar yüksek risk gösteriyorsa:
1. ``inactivity_days`` 9999 = hiç quote'lanmamış parça (yeni
   import normal)
2. ``price_age_days`` 9999 = PriceEntry yok (manuel data entry
   eksik olabilir)
3. ``missing_fields_count`` ≥ 2 = master data quality problemi

### Substitution patterns boş
V9 quote revision tree zorunlu. ``parent_quote_id`` set edilmiş
quote'lar yoksa hiçbir substitution detect edilmez. Test için:
1. Bir quote oluştur, parça A ile
2. Aynı opportunity altında ikinci quote (revision) oluştur, parça B ile
3. ``GET /v10/parts-intel/parts/{A_id}/substitutions`` → B parçasını döner

---

## 3) Performans

V10 endpoint'lerinin hiçbiri caching kullanmıyor — her istek
SparePart × QuoteItem üzerinde aggregate yapar. Tipik prod
yüklerinde:

| Endpoint | Süre | Notlar |
|---|---|---|
| ``/summary`` | 200-400 ms | 3 ayrı sorgu |
| ``/velocity`` | 100-300 ms | tek aggregate |
| ``/dead-stock`` | 100-300 ms | subquery + outer join |
| ``/obsolescence-watch`` | 1-3 sn | per-part composite scoring |
| ``/data-health`` | 200-500 ms | SparePart taraması |
| ``/duplicates`` | 1-5 sn | fuzzy self-join, parça sayısına quadratic |

Catalog 5k parçayı geçince ``duplicates`` sorgusu yavaşlar — o
durumda ya threshold'u yükselt (0.85 → 0.92) ya da limit düşür.

---

## 4) Maliyet etkisi

V10 ek dependency / dış servis kullanmıyor:
- DB load: var olan tablolar üzerinde aggregate (tipik 5-10 ms/sorgu)
- CPU: çok düşük (Python-only, transformer yok)
- Memory: ihmalsiz

Manager dashboard günde ~1 kez açılıyorsa (muhtemel kullanım) prod
yüküne ek maliyet yok. Cockpit widget'larından refetch yapan
sayfalar da var; Long-poll gerekirse caching ekle.

---

## 5) Bilinen sınırlamalar

- ``demand_heatmap``'in PG-spesifik ``to_char()`` yerine Python'da
  bucketing yapan implementasyonu kullanıyor — büyük veri setlerinde
  (>100k QuoteItem) yavaş kalabilir. O zaman PG ``date_trunc()``
  versiyona geçirmek mantıklı.
- ``inflation_tax_summary`` her parça için 2 sorgu (oldest +
  latest list_price) atıyor — ~100 parça > 200 sorgu. CTE'ye
  taşımak mantıklı ama şimdilik prod yükünde acil değil.
- V10 multi-tenant'a tam tenant_id propagation yapıyor — eski
  data tenant_id NULL ise endpoint'ler tüm dataset'i döner. V12
  bootstrap çalıştırılmadan multi-tenant kullanmaya çalışma.
