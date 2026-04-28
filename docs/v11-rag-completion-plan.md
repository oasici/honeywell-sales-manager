# V11 — Qdrant RAG Completion

**Status**: 2026-04-28 — sprint plan + execution
**Predecessor**: V9 UAT pass-1, V10 spare-parts plan (parked)

---

## Mevcut Qdrant/RAG durumu

✅ **Var olan**:
- `vector_store.py` — 3 collection (deals, interactions, competitors), CRUD'lar
- `qdrant_breaker` — circuit breaker entegrasyonu
- Lazy embedding model load (`paraphrase-multilingual-MiniLM-L12-v2`, 384-dim)
- Pre-load on startup (FEATURE_RAG)
- Docker compose'da qdrant servisi
- `vector_search.py` — pgvector tabanlı (alternatif yol)
- `embedding_service.py`, `semantic_matcher.py` — spare parts catalog için
- `/api/v1/ai/rag/status` — basit Qdrant durum endpoint'i
- `store_deal` çağrısı `ai_deal_risk_service`'te var
- `store_competitor_intel` çağrısı `competitor_crawler`'da var

❌ **Eksik (V11 kapsamı)**:
1. Mevcut deals/transcripts/emails RAG'e backfill edilmiyor
2. `store_interaction` hiçbir yerden çağrılmıyor (transcript / email / call save hook'u yok)
3. Search endpoint'leri sadece `/rag/status` — actual `/rag/search/...` yok
4. Quote/Opportunity close olduğunda RAG'e otomatik girmiyor
5. Pure retrieval var, RAG-augmented generation (retrieve + Claude prompt) yok
6. Collection management endpoint yok (recreate, delete, count)
7. Test coverage zayıf

---

## V11 Sprint Plan

### Sprint A — Backfill jobs

`scripts/backfill_rag.py`:
- `backfill_deals()` — closed_won/closed_lost opportunities → store_deal
- `backfill_interactions()` — transcripts + email_requests + activity_logs (high-signal) → store_interaction
- `backfill_competitors()` — competitor_mentions + competitive intel snippets → store_competitor_intel

`backend/app/tasks/scheduler.py`:
- Yeni cron: `rag_incremental_backfill` günde 1x (07:00 UTC) — son 24 saatte değişen kayıtları RAG'e yansıt

### Sprint B — Search API endpoints

Yeni router: `app/api/v1/rag.py` mounted under `/api/v1/rag/`
- `POST /rag/search/deals` — body: `{query, limit?, filters?}` → similar deals
- `POST /rag/search/interactions` — body: `{query, customer_id?, limit?}`
- `POST /rag/search/competitors` — body: `{competitor, query?, limit?}`
- `GET  /rag/collections` — list with point counts
- `POST /rag/reindex/{collection}` — manager-only, triggers backfill
- All gated by `FEATURE_RAG` + role guards

### Sprint C — Auto-ingest hooks

- `Transcript` save hook → `store_interaction` (existing service: `engagement` or transcript_summarizer)
- `EmailRequest` save hook → `store_interaction` (lighter, only if has body)
- `Opportunity.stage` change to closed_won/closed_lost → `store_deal`
- All hooks best-effort (try/except + log warn)

### Sprint D — RAG-augmented Q&A service

`app/services/rag_answer_service.py`:
- `answer_question(question, scope=...)`:
  1. Retrieve top-K from chosen collection(s)
  2. Build Claude prompt: question + retrieved snippets + instruction
  3. Call `claude_messages_create`
  4. Return `{answer, citations, confidence}`
- `POST /api/v1/rag/answer` endpoint (manager + ops)
- Use `parse_claude_json` for structured output

### Sprint E — Collection mgmt + tests

- `tests/test_rag_services.py`:
  - vector_store CRUD tests (test_mode without real Qdrant)
  - rag_answer_service mocked Claude
  - search endpoints (FEATURE_RAG=true sandbox)
- Collection count utilities for ops dashboard

---

## UAT Pass-2 Sprint (parallel)

### i18n critical batch
- Risk badge component — variant=low/med/high/critical color mapping fix
- AI Assistant tabs (item 17) — i18n keys
- Approval rule modal (item 13) — i18n keys
- Pipeline cards (item 27) — i18n keys
- Most Opportunity detail English strings (item 4 details)

### UI behavior fixes
- Item 27 — Pipeline key dropdown (Select component)
- Item 28 — Customer ID input → Customer select; add Retention/Breach tabs
- Item 34 — Notification fetch consistency

### Deferred to pass-3
- Customer detail deep i18n (item 15) — too many strings, separate pass
- Sequence template flow (item 24) — needs SequenceBuilder query-param wiring
- Playbook page i18n (item 20) — separate pass

---

## Validation

- 697 backend + ~30 new RAG tests
- Frontend tsc + vitest + build
- Backfill script runs clean on demo data
- All new endpoints flag-gated (`FEATURE_RAG`)
