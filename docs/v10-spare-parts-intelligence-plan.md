# V10 — Spare Parts Intelligence Layer

**Status**: 2026-04-28 — sprint plan (parked, will resume after bug-fix queue)
**Predecessor**: `docs/v9-v2-v3-gap-closure-plan.md`
**Trigger**: ANEXPO 2026 "Strategic Resilience" outlook PDF — 6 themes
mapped to existing data sources without touching the SparePart schema.

---

## Hard constraint

**The `SparePart` table is fed by Excel import and is company-unique. We
do NOT add columns to `SparePart`.**

V10 is a pure **read-only intelligence layer** — derived metrics +
aggregation services + UI panels — built on top of existing data:

- `SparePart` (honeywell_code, name, description, category, model_number,
  transfer_price, supplier_price, currency, min_margin_pct, is_active)
- `PriceEntry` (list_price, discount_pct, net_price, valid_from/until, version)
- `QuoteItem` (quantity, unit_price, discount_pct, line_total)
- `Quote` (status, created_at, sent_at, accepted_at, customer_id) +
  V9 revision tree (parent_quote_id, revision_no, superseded_by)
- `Opportunity` (stage, amount, customer_id) — pipeline weighting
- `Customer` (industry, employee_count) — segment affinity

No migrations, no schema changes, no breaking changes.

---

## PDF insight → existing data → UI panel mapping

The 2026 ANEXPO outlook has 6 themes; each maps to one or more
derivations from data we already have:

| PDF theme | Derived metric | Source query | UI surface |
|---|---|---|---|
| §1 Inflation Tax (15%) | Per-part transfer_price drift over 12 months | `PriceEntry.created_at` × `list_price` time series | SparePart detail badge: "Fiyat 12 ayda %X arttı" |
| §1 Frozen capital | Parts never quoted in N months × supplier_price | `SparePart` LEFT JOIN `QuoteItem` | "Dead Stock Ledger" page (manager) |
| §1 Critical-part scoring | Pareto A/B/C tier | `QuoteItem.quantity × unit_price` agg | Dashboard widget "Top 20 Critical Parts" |
| §1 Demand heatmap | Part × month quote frequency | `QuoteItem` + `Quote.created_at` | SparePart detail mini-chart, manager heatmap |
| §1 Lead-time signal | Quote-to-sent latency per part | `Quote.created_at → sent_at` | "Ortalama hazırlık süresi" badge per part |
| §2 Stale pricing | `valid_until` expired or 180+ days idle | `PriceEntry.valid_until` + `created_at` | SparePart list "⚠️ Eski fiyat", Data Quality page |
| §2 Master Data Health | Field completeness % per tenant | `SparePart` NULL counts | Settings → Data Quality dashboard |
| §2 De-duplication | Same name/model + different code | Fuzzy self-join on SparePart | Admin "Olası Duplicate Parts" |
| §3 Refurbished detection | Description keyword scan | `description_tr/en` ILIKE | Quote builder "Refurbished alternatif" suggestion |
| §3 Margin health | Derived margin vs `min_margin_pct` | `PriceEntry.net_price` + `transfer_price` | Quote builder inline margin alert |
| §3 Pricing power | High demand + low avg discount | `QuoteItem.discount_pct` × demand | Pricing strategy page (manager) |
| §4 Obsolescence "late truth" | Quote freq decay over 12 months | `QuoteItem` rolling window | "Obsolescence Watch" cockpit widget |
| §4 EOL risk score | composite (inactivity + missing data + price age) | multi-table | SparePart list filter "🟡 Risk" |
| §4 Migration map (light) | V9 quote-revision diff = part swapped | `Quote.parent_quote_id` + items diff | Quote detail "Eski parça → yeni parça" |
| §5 Customer MRO maturity | Per-customer rating from quote/order patterns | full quote/opp history | Customer 360 new tab |
| Cross-cutting | Cross-customer demand | `QuoteItem` × `Customer` | "Bu parça X müşteride kullanılıyor" |

---

## Sprint plan (V10)

### Sprint AA — `parts_intelligence_service` (foundation)

Read-only aggregates over `SparePart` × `QuoteItem` × `Quote`.

**Functions**
- `velocity_classification()` → Pareto A/B/C tier per part
  (top 20% by line_total → A, next 30% → B, rest → C)
- `demand_heatmap(window_days=180)` → month × part_id frequency matrix
- `dead_stock_ledger(min_idle_days=180)` → list of parts never appearing
  in QuoteItem within window, with supplier_price summed (= frozen capital
  estimate)

**Endpoints**
- `GET /v10/parts-intel/velocity?tier=A`
- `GET /v10/parts-intel/heatmap?window_days=180`
- `GET /v10/parts-intel/dead-stock?min_idle_days=180`

**Tests**
- A/B/C tier sums to 100% of parts
- Heatmap empty when no quotes in window
- Dead stock excludes parts with active QuoteItem

---

### Sprint BB — `parts_pricing_intel_service`

Derives pricing-side intelligence from `PriceEntry` history.

**Functions**
- `inflation_tax_summary()` → per-part 12m drift × current pipeline value
  (returns V5 envelope: value/confidence/drivers/recommended_actions)
- `stale_pricing_alerts(max_age_days=180)` → parts whose latest PriceEntry
  is `valid_until` < today OR `created_at` > N days
- `margin_health_alerts()` → parts where derived margin
  `(net_price - transfer_price) / net_price` < `min_margin_pct × 0.8`

**Endpoints**
- `GET /v10/parts-intel/inflation-tax`
- `GET /v10/parts-intel/stale-pricing`
- `GET /v10/parts-intel/margin-health`

**Tests**
- Stale detection respects `valid_until` even when `created_at` is fresh
- Margin alert tolerates missing transfer_price (no false positives)

---

### Sprint CC — `parts_obsolescence_watch_service`

The §4 "late truth" problem solved with our existing signals.

**Functions**
- `eol_risk_score(part_id)` → V5 envelope shape:
  - value: 0..100 risk score
  - drivers: [inactivity_days, missing_fields_count, price_age_days,
    quote_freq_decay_pct]
  - recommended_actions: ["last_time_buy_review", "data_completion"]
- `obsolescence_watch_list(top_n=20)` → cockpit widget data
- `last_time_buy_recommendations()` → parts where quote freq dropped
  ≥ 50% YoY but pipeline value > threshold

**Endpoints**
- `GET /v10/parts-intel/obsolescence-watch?top_n=20`
- `GET /v10/parts-intel/parts/{id}/eol-risk`
- `GET /v10/parts-intel/last-time-buy`

**Tests**
- Risk score bounded 0..100
- Decay calc handles parts with < 12 months history (returns lower confidence)

---

### Sprint DD — `parts_data_quality_service`

PDF §2 (Trust Gap) — read existing SparePart fields without modifying.

**Functions**
- `master_data_health_score(tenant_id)` → composite 0..100 from field
  completeness (description, category, supplier_price, model_number)
- `duplicate_candidates(threshold=0.85)` → Levenshtein + model_number
  fuzzy match returning candidate pairs
- `orphan_pricing()` → PriceEntry rows pointing to inactive/deleted SparePart

**Endpoints**
- `GET /v10/parts-intel/data-health`
- `GET /v10/parts-intel/duplicates?threshold=0.85`
- `GET /v10/parts-intel/orphan-pricing`

**Tests**
- Health score = 100 when all fields populated
- Duplicate detection ignores intentional aliases (uses `aliases_json`)

---

### Sprint EE — `parts_substitution_service`

Uses V9 quote revision tree to surface "what got swapped".

**Functions**
- `substitution_patterns(part_id)` → list of (replaced_by_part_id, count,
  context) from `quote_revisions` chain diff
- `cross_customer_demand(part_id)` → distinct customers × industries
  using this part in last N months
- `segment_affinity(part_id)` → which `industry`/`size_band` clusters
  consume this part most

**Endpoints**
- `GET /v10/parts-intel/parts/{id}/substitutions`
- `GET /v10/parts-intel/parts/{id}/cross-customer`

**Tests**
- Substitution detection skips revisions where line items unchanged

---

### Sprint FF — UI panels & widgets

Frontend integration of the V10 services.

**New surfaces**
1. **Spare Parts Intelligence Dashboard** (manager-only page)
   - Widget: Velocity Pareto chart (A/B/C distribution)
   - Widget: Dead Stock Ledger (top 20 + frozen capital total)
   - Widget: Obsolescence Watch (top 20 EOL risk)
   - Widget: Master Data Health Score gauge

2. **SparePart detail page enhancements** (existing page, additive)
   - Section: Demand chart (last 12 months × quote frequency)
   - Section: Price drift sparkline (transfer_price + list_price)
   - Section: Cross-customer demand (X müşteri × Y segment)
   - Section: EOL risk envelope card (value, drivers, recommended_actions)

3. **Quote Builder inline hints** (existing builder, additive)
   - Margin alert: "⚠️ %15 altında" inline pill
   - Refurbished suggestion: "💡 Refurbished alternatif: HW-X-REFURB"
   - Hot demand: "📈 Son 30 günde 12 quote'ta yer aldı"
   - Stale price: "⚠️ Fiyat son güncelleme: 8 ay önce"

4. **Manager Cockpit widgets**
   - Top 5 EOL Risk (clickable, drills to obsolescence-watch)
   - Frozen Capital This Quarter pill
   - Data Health Score progress bar

5. **Customer 360 — MRO Maturity tab**
   - PDF §5 diagnostic adapted for our customers
   - Score 0-8 across 8 questions derived from quote/opp history

---

## Validation gate (when V10 ships)

- pytest backend (≥ 697 + ~30 V10 tests ≈ 727)
- frontend tsc + vitest + production build
- All new endpoints under `/v10/parts-intel/*` namespace
- 1 new feature flag `FEATURE_V10_PARTS_INTEL`
- No DB migrations
- No breaking changes — every endpoint is additive

---

## Why this approach is safer than the original V10 plan

The first V10 draft (in chat thread) proposed adding ~6 columns to
SparePart (lifecycle_status, condition_grade, mtbf_hours, co2_kg, etc.).
That breaks the Excel import contract.

This revised V10:
- **Schema-frozen**: zero columns added to SparePart
- **Excel-import-safe**: new columns won't appear in import templates
- **Tenant-isolated**: V8 tenant_id boundary respected on all aggregates
- **Reversible**: pure additive; can be feature-flagged off without data loss
- **Demo-ready**: V8 seed data already populates the underlying quote/price
  tables enough to light up every panel

---

## Out of scope (deferred to V11+)

- **CO₂ tracking** — needs `co2_kg_new`/`co2_kg_refurbished` columns we
  agreed not to add. Can be a separate companion table if needed.
- **Real-time market offers** (PDF §1 100M+ offers) — needs external
  Automa.Net API integration. Skeleton in V9 CRM Sync platform; a
  V11 sprint can extend to spare-part offer feeds.
- **AI nameplate scan** — file upload + OCR (Tesseract or cloud). Skeleton
  endpoint can land but production OCR is V11.
- **3D printing flag** — needs the column we're not adding. Could ride
  on the V11 companion-metadata table.

---

## Resume conditions

V10 work resumes once the bug-fix queue is cleared. When resuming:
1. Re-read this doc.
2. Pick scope (all 6 sprints OR P0 = AA + BB + CC).
3. Build straight through (V5-V9 cadence).
4. Validation gate + commit + push + v1.4.0 release.
