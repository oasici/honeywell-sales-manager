# V9 — V2/V3 Gap Closure Plan

**Status**: 2026-04-28 — sprint plan
**Predecessor**: `docs/v8-final-plan.md`

V8 closed the framework spec (operational/learning/network intelligence)
to ~100% within single-product scope. The remaining gaps live in the
older V2/V3 plans — CRM sync, calendar OAuth, board UX polish, NL
search, quote revisions, slippage dashboard, K8s rollout decision.

V9 closes these P0-P3 gaps. All sprints are additive (no breaking
changes), feature-flagged, and idempotent.

---

## Sprint K (P0) — CRM Sync platform

**Why**: Plan'da V2 Faz 3.4+ olarak vardı, hiç teslim edilmedi. En
büyük entegrasyon scope kaybı.

### Migration `20260428_v9_crm_sync.py`
New tables:
- `crm_connections` (id, provider, base_url, oauth_token_encrypted,
  refresh_token_encrypted, expires_at, sync_state, last_sync_at,
  is_active, created_by, created_at)
- `crm_field_mappings` (connection_id, internal_field, external_field,
  direction, transform_rule_json)
- `crm_sync_jobs` (connection_id, entity_type, status, started_at,
  finished_at, items_pulled, items_pushed, items_failed,
  error_log_json)
- `crm_record_links` (id, connection_id, internal_entity_type,
  internal_id, external_id, last_synced_at, hash_signature)

### New module `app/services/crm_sync/`
- `base.py` — `CRMConnectorProtocol` (auth, list, push, pull, map)
- `salesforce_adapter.py` — REST adapter using simple-salesforce
- `hubspot_adapter.py` — REST adapter using hubspot-api-client (skeleton)
- `mapping_engine.py` — bidirectional field mapper
- `sync_orchestrator.py` — pull + push driver with rate-limit awareness

### Endpoints `/api/v1/v9/crm/...`
- `POST /connections` — create
- `GET /connections` — list
- `POST /connections/{id}/test` — credential probe
- `POST /connections/{id}/sync/{entity_type}` — manual sync (manager only)
- `GET /jobs` — sync history

### Flag: `FEATURE_V9_CRM_SYNC`

---

## Sprint L (P0) — Calendar OAuth + meeting auto-log

**Why**: V2 C1 epic — `calendar_adapter` skeleton vardı, OAuth + auto-log
yok. Meeting prep UX'inin temeli.

### Migration `20260428_v9_calendar_oauth.py`
New tables:
- `calendar_connections` (id, user_id, provider, oauth_token_encrypted,
  refresh_token_encrypted, expires_at, calendar_id, is_active,
  created_at)
- `meeting_auto_links` (id, meeting_booking_id, opportunity_id,
  matched_by, confidence, created_at)

### New module `app/services/calendar_sync_service.py`
- Build on existing `calendar_adapter`
- `link_meeting_to_opportunity` — match by attendee email
- `auto_log_meeting` — create OpportunityEvent + log_activity
- `refresh_token_if_needed` — OAuth refresh

### Endpoints
- `POST /api/v1/v9/calendar/connect` — start OAuth (return auth_url)
- `POST /api/v1/v9/calendar/callback` — finish OAuth
- `GET  /api/v1/v9/calendar/upcoming` — pulled meetings
- `POST /api/v1/v9/calendar/link/{booking_id}` — manual link

### Flag: `FEATURE_V9_CALENDAR_OAUTH`

---

## Sprint M (P1) — Kanban WIP limits + bulk review queue

**Why**: V2 Faz 3.0 backlog #3 (kanban WIP) ve #4 (bulk stage update
review queue). Board UX'inin çıkmaz iki maddesi.

### Migration `20260428_v9_board_ux.py`
- `ALTER TABLE stage_configs ADD COLUMN wip_limit INTEGER` (NULL = no limit)
- New table `pipeline_review_queue` (id, opportunity_id, suggested_stage,
  suggested_close_date, suggested_amount, suggestion_source, suggested_at,
  decided_at, decision, decided_by, evidence_json)

### Service updates
- `app/services/pipeline_review_service.py` — propose/decide/list
- `board_summary` endpoint exposes per-stage `wip_warning` when
  `count > wip_limit`

### Endpoints
- `GET  /api/v1/v9/board/wip-status` — per-stage actual vs. limit
- `GET  /api/v1/v9/board/review-queue` — pending suggestions
- `POST /api/v1/v9/board/review-queue/{id}/decide` — apply / dismiss

### Flag: gates under existing `FEATURE_V2_BOARD`

---

## Sprint N (P1) — NL search semantic upgrade

**Why**: V2 Salesforce mapping #6 (ConversationSearch) — text match
seviyesinde. V8'de eklediğimiz `text_embedder`'ı arama tarafında
kullanmak için.

### New service `app/services/nl_search_service.py`
- Build on `text_embedder` (no new ML dep)
- `embed_query(text)` — encode query
- `search_transcripts(query, limit, ...)` — cosine over Transcript
  embeddings
- `search_opportunities(query, ...)` — cosine over OpportunityTextEmbedding
- `search_emails(query, ...)` — cosine over EmailRequest
- Hybrid mode: combine embedding cosine + keyword match score

### Migration `20260428_v9_nl_search.py`
- New table `transcript_embeddings` (transcript_id PK, embedding_json,
  dim, version, vocab_hash, generated_at)
- New table `email_embeddings` (email_request_id PK, embedding_json, ...)
- Background job populates them

### Endpoints
- `POST /api/v1/v9/search/semantic` — `{ query, scopes: [transcripts, opps, emails], limit }` → ranked items with score breakdown

### Flag: `FEATURE_V9_NL_SEARCH`

---

## Sprint O (P2) — Quote revision tree

**Why**: V2 Faz 3.4 #24 — versioned quotes one opportunity altında. V6'da
`quote_revision_count_30d` eklendi, asıl revision tree yok.

### Migration `20260428_v9_quote_revisions.py`
- `ALTER TABLE quotes ADD COLUMN parent_quote_id INTEGER REFERENCES quotes(id)` (NULL = original)
- `ALTER TABLE quotes ADD COLUMN revision_no INTEGER NOT NULL DEFAULT 1`
- `ALTER TABLE quotes ADD COLUMN superseded_by INTEGER REFERENCES quotes(id)`
- Index on `(parent_quote_id, revision_no)`

### Service `app/services/quote_revision_service.py`
- `create_revision(quote_id)` — clone + bump revision_no + set parent
- `list_revisions(opportunity_id)` — walk the tree
- `mark_superseded(old_id, new_id)` — link

### Endpoints
- `GET  /api/v1/v9/opportunities/{id}/quote-revisions` — full tree
- `POST /api/v1/v9/quotes/{id}/revise` — create revision

### Flag: gates under `FEATURE_V2_BOARD`

---

## Sprint P (P2) — Slippage dashboard

**Why**: V2 Faz 3.3 #19 — slippage data zaten var (`stage_velocity_days`,
`previous_*` columns), dedicated endpoint yok.

### New service `app/services/slippage_service.py`
- Pure aggregation over `Opportunity` + `OpportunityFeaturesDaily`
- Compute: deals that pushed close_date forward, stage regressions,
  amount changes
- Per-rep / per-stage / per-segment breakdowns

### Endpoint
- `GET /api/v1/v9/slippage?owner_id=&stage=&window_days=` — slippage
  envelope (V5 explainability shape)

No migration — read-only over existing data.

### Flag: gates under `FEATURE_V2_BOARD`

---

## Sprint Q (P3) — K8s rollout decision

**Why**: V3 sandbox commit'inde Kubernetes manifests var (`k8s/base`,
`k8s/overlays`, `k8s/jobs`) ama Render kullanılıyor. İki seçenek var
ve karar verilip dokümante edilmesi gerekiyor.

### Deliverable
`docs/decisions/k8s-vs-render.md` — Architecture Decision Record:
- Mevcut durum (Render web + worker, GitHub Actions deploy)
- K8s manifests'in ne sağladığı (multi-region, autoscale, Helm)
- Render'ın yetersiz kaldığı yerler (varsa)
- Karar: **Render'da kal, K8s manifests'i deprecate et veya saklayıp dormant bırak**
- Migration plan'ı (eğer K8s'e geçilecekse)

No code change.

---

## Validation gate

- pytest backend (≥ 677 + ~30 new V9 tests ≈ 707)
- frontend tsc + vitest + production build
- All migrations idempotent
- 3 new feature flags: `FEATURE_V9_CRM_SYNC`, `FEATURE_V9_CALENDAR_OAUTH`,
  `FEATURE_V9_NL_SEARCH`
- No breaking changes — every new column NULLABLE/0/false default

---

## Rollout

V9 ships behind flags. Tenant onboarding order:
1. Sprint M (Kanban WIP + review queue) — flag-on per tenant
2. Sprint O (quote revisions) — flag-on per tenant
3. Sprint P (slippage) — flag-on per tenant
4. Sprint N (NL search) — needs embedding backfill cron once enabled
5. Sprint K (CRM Sync) — manual onboarding per tenant + per provider
6. Sprint L (Calendar OAuth) — manual onboarding per user

Sprint Q (K8s decision) — internal doc only, no rollout.
