# V4 on V1 Blueprint (Event Omurgası + Feature Store)

Bu doküman, V4 mimarisini **mevcut V1 ürün** üzerinde uygulamak için “yeniden kurmadan”, var olan omurgayı **canonical** ilan ederek ilerleyen uygulama planıdır.

## 1) V1 → V4 eşleme (gerçek tablo/dosya bazında)

### 1.1 Event omurgası

V4 `sales_events` tablosu için V1’de iki kaynak var:

- **`activity_logs`** (`backend/app/models/activity_log.py`)
  - V4 `sales_events` MVP karşılığıdır.
  - `activity_type` → V4 `event_type`
  - `created_at` → V4 `event_ts`
  - `opportunity_id`, `customer_id`, `user_id` zaten mevcut
  - `metadata_json` → V4 `payload_json`
- **`opportunity_events`** (`backend/app/models/opportunity.py`)
  - Deal timeline (replay için ideal).
  - `event_type` (email/quote/task/stage_change/...) V4 tokenization/replay için kullanılır.

**Karar (MVP):** yeni `sales_events` açmıyoruz. V4 ingest yerine, V1’in `activity_logger.log_activity()` çağrıları event yazımının canonical noktasıdır.

### 1.2 Signals

- **`revenue_signals`** (`backend/app/models/revenue_signal.py`, `backend/app/services/revenue_signal_service.py`)
  - V4 `conversation_signals` için canonical tablodur.
  - `event_key` ile idempotency zaten var.
  - `metadata_json` explainability standardını taşımak için kullanılır.
- **`competitor_mentions`** (`backend/app/models/competitor_mention.py`)
  - `competitor_mention` sinyali için kanıt (evidence) kaynağıdır.
- (legacy) **`opportunity_signals`** (`backend/app/models/opportunity.py`)
  - Opportunity detail intelligence payload’ında kullanılıyor.
  - Uzun vadede `revenue_signals` ile birleşik okunabilir; MVP’de dokunmuyoruz.

### 1.3 Feature store

V4:
- `opportunity_features_daily`
- `account_features_daily`
- `rep_features_daily`

V1’de bugün feature store yok. V4’ün “kalıcı analitik/learning/network” katmanlarını güvenli biçimde üretmek için bu tabloları **ekleyeceğiz** (alembic).

### 1.4 Cockpit / Board / Opportunity detail bağlantıları

- Cockpit KPI + aksiyonlar:
  - `backend/app/api/v1/cockpit.py`
  - `revenue_signals`, `tasks`, `activity_logs` kullanıyor.
- Activity drought:
  - `backend/app/api/v1/analytics.py` `/activity-drought`
  - `activity_logs` üzerinden “last rep touch” mantığına yakın bir view sağlıyor.
- Deal health:
  - `backend/app/services/deal_health_service.py`
  - Risk/score üretimi için V4 feature store ile beslenebilir.

## 2) En kritik tasarım standartları

### 2.1 Explainability sözleşmesi (tek format)

Tüm V4 intelligence çıktıları `revenue_signals.metadata_json` içinde şu shape ile tutulur:

```json
{
  "value": "...",
  "confidence": 0.0,
  "drivers": [{"label": "...", "impact": 0.0}],
  "benchmark_context": {},
  "recommended_actions": [],
  "model_version": "v4-mvp"
}
```

### 2.2 İdempotency standardı

Tüm signal üretimleri `event_key` üretir:

- Ör: `v4:{signal_type}:{source_entity_type}:{source_entity_id}`
- Aynı kaynaktan aynı sinyal tekrar üretilirse `emit_signal()` duplicate’ı yutar.

## 3) Uygulama sırası (V1 üzerinde)

1. Feature store tabloları (daily snapshots) + nightly builder job
2. Momentum (daily snapshot alanı + cockpit feed)
3. Buyer state (history tablosu)
4. Decision gaps (stakeholder_roles + decision_gaps)
5. Network benchmarks (segment_benchmarks_daily)

## 4) İlgili: additive hizalama yol haritası

Hedef mimariyi **mevcut yazım yollarını bozmadan** kapatmak için ayrıntılı faz/strateji: `docs/v4-additive-alignment-roadmap.md`.

