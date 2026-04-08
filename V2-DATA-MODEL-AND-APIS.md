# Honeywell Sales Suite v2 — Veri Modeli + API Kontratları (non-breaking)

Bu doküman, v2 hybrid (Opportunity + Quote) SalesBoard için **additive** veri modeli ve API yüzeyini tanımlar.

## Tasarım ilkeleri
- **Additive migrations**: yeni tablolar + nullable kolonlar.
- **Geriye uyum**: v1 quote/email akışları opportunity olmadan çalışır.
- **Auditability**: AI önerisi uygulama işlemleri audit log’a yazılır.
- **Feature flags**: entegrasyonlar ve “auto-apply” default kapalı.

## 1) Veri modeli (öneri)

### 1.1 `opportunities`
Pipeline deal objesi.
- `id` (PK)
- `title` (string)
- `stage` (enum/string) — ör: prospecting, qualified, proposal, negotiation, closed_won, closed_lost
- `amount` (numeric, nullable)
- `currency` (string, default mevcut)
- `close_date` (date, nullable)
- `owner_id` (FK users.id)
- `customer_id` (FK customers.id, nullable) — “account” eşlemesi için
- `status` (active/closed)
- `created_at`, `updated_at`

Index’ler: `(owner_id, stage)`, `(customer_id)`, `(close_date)`

### 1.2 `opportunity_events`
Opportunity timeline.
- `id`
- `opportunity_id`
- `event_type` (email|quote|call|meeting|note|task)
- `entity_type` (email_request|quote|...) nullable
- `entity_id` (int) nullable
- `occurred_at` (datetime)
- `payload_json` (text/json) — minimal, PII guard

### 1.3 `opportunity_signals`
Signal/insight kayıtları.
- `id`
- `opportunity_id`
- `signal_type` (pricing_concern|competitor|no_touch|discount_risk|sla_breach|objection)
- `severity` (low|med|high)
- `evidence` (text/json) — snippet + kaynak link
- `created_at`

### 1.4 `account_enrichment`
External enrichment cache.
- `id`
- `customer_id` (FK customers.id)
- `provider` (string)
- `data_json` (json)
- `fetched_at` (datetime)
- `ttl_seconds`

### 1.5 `tasks` (opsiyonel ama önerilir)
Next-best-action ve playbook için.
- `id`
- `owner_id`
- `opportunity_id` nullable
- `title`, `due_at`, `status` (open/done)
- `source` (manual|rule|ai)
- `created_at`

### 1.6 Mevcut tablolarla bağlama (minimum değişiklik)
#### `quotes`
- Nullable `opportunity_id` ekle.

#### `email_requests`
Faz 3.0’da eklemek şart değil:
- Seçenek S1: email timeline’ı quote üzerinden bağla.
- Seçenek S2: nullable `opportunity_id` ekle (faz 3.1).

## 2) API kontratları (öneri, /api/v1 altında)

### 2.1 Opportunities
**GET** `/api/v1/opportunities/?stage=&owner_id=&q=&page=&page_size=`
- Paginated list

**POST** `/api/v1/opportunities/`
- Create opportunity

**GET** `/api/v1/opportunities/{id}`
- Detail + computed fields: rotting_days, health_score, open_quotes_count

**PATCH** `/api/v1/opportunities/{id}`
- Update fields

**GET** `/api/v1/opportunities/{id}/timeline?limit=&cursor=`
- Events list

**GET** `/api/v1/opportunities/{id}/signals`
- Signals list

### 2.2 Board
**GET** `/api/v1/board/kanban?owner_id=&stages=...&q=...`
- Response:
  - columns: [{ stage, count, total_amount, items:[...] }]
  - items minimal payload

**GET** `/api/v1/board/summary?window=30`
- KPI: coverage, forecast, rotting, win-rate

### 2.3 AI endpoints (guarded + rate limited)
**POST** `/api/v1/ai/summarize`
- Input: { entity_type, entity_id, focus? }
- Output: { summary, sources[] }

**POST** `/api/v1/ai/suggest-pipeline-update`
- Input: { opportunity_id }
- Output: { suggested_stage?, suggested_next_steps[], factors[] }

**POST** `/api/v1/ai/extract-signals`
- Input: { opportunity_id } or { email_id } etc.
- Output: signals[]

### 2.4 Integrations (feature-flag)
**POST** `/api/v1/integrations/{provider}/connect`
**POST** `/api/v1/integrations/{provider}/sync`

## 3) Migration stratejisi
- 3.0: yeni tablolar + `quotes.opportunity_id`
- 3.1: opsiyonel `email_requests.opportunity_id`, tasks tablosu
- 3.2+: enrichment/signals genişleme

## 4) Feature-flag stratejisi
Minimum:
- `FEATURE_V2_BOARD`
- `FEATURE_AI_SUMMARIES`
- `FEATURE_AI_PIPELINE_SUGGESTIONS`
- `FEATURE_INTEGRATIONS_*`
- `FEATURE_AI_AUTO_APPLY` (default false)

Flag storage:
- basit: `settings` tablosu (key/value)
- gelişmiş: env + db override

