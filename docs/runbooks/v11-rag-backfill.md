# V11 RAG — Backfill & Operations Runbook

V11 kapsamı:
- Qdrant'a deal/interaction/competitor koleksiyonları
- ``services/rag_backfill_service.py`` — full + incremental backfill
- ``services/rag_answer_service.py`` — retrieve-then-generate Q&A
- ``api/v1/rag.py`` — ``POST /rag/search/{collection}``,
  ``POST /rag/answer``, ``GET /rag/collections``,
  ``POST /rag/reindex/{name}``
- ``scheduler.py`` — günlük 07:00 UTC incremental backfill cron
- Otomatik ingest hook'ları: stage_change → closed_won/lost ve
  yeni transcript create eventlerinde

---

## 0) Önkoşullar

- ``FEATURE_RAG=true`` (env)
- ``QDRANT_URL`` set edilmiş (Render dashboard) — örn.
  ``https://xxx.eu-central.aws.cloud.qdrant.io:6333``
- ``QDRANT_API_KEY`` (eğer Qdrant Cloud kullanıyorsan)
- ``ANTHROPIC_API_KEY`` (RAG answer pipeline Claude'a soruyor)

```bash
# Sanity
curl -s -H "api-key: $QDRANT_API_KEY" $QDRANT_URL/collections | jq '.result'
# Beklenen: deals, interactions, competitors koleksiyonları
```

---

## 1) İlk full backfill (sıfırdan kurulum)

```bash
# GitHub Actions → "Manual: RAG Backfill" → Run workflow
# (eğer workflow yoksa Render shell:)
FEATURE_RAG=true python -m scripts.backfill_rag --apply
```

Her koleksiyon için Qdrant'a:
- Deals: kapanmış (won/lost) opportunity'ler
- Interactions: transcript + email + meeting note
- Competitors: revenue_signal'da geçen rakip mention'ları

Süre: ~10-15 dk (1k opportunity için). Memory profili ~500MB
(sentence-transformers modeli). Render free tier'da yetersiz olabilir
— starter tier öner.

---

## 2) Incremental backfill (cron — günlük)

Scheduler her gün 07:00 UTC'de son 25 saatte değişen kayıtları
yeniden index'liyor. ``FEATURE_RAG=false`` ise no-op.

```bash
# Manuel tetik (acil senkron için):
FEATURE_RAG=true python -m scripts.backfill_rag --apply --since-hours 25
```

Cron monitoring:
- Scheduler log'unda ``rag_incremental_backfill completed: {...}``
- Hata durumunda Sentry'ye düşer

---

## 3) Tek koleksiyon reindex

Bozuk koleksiyon (ör. embedding modeli güncellendi, vocab hash
drift) durumunda tüm koleksiyonu sıfırlamak gerekebilir:

```bash
# API üzerinden (admin only)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  $API/v1/rag/reindex/deals
```

Bu Qdrant'ta koleksiyonu drop edip yeniden yaratır. Süre koleksiyon
boyutuna bağlı (~1-5 dk).

---

## 4) RAG Q&A test

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"Geçen ay X müşterisinde ne konuştuk?"}' \
  $API/v1/rag/answer
```

Yanıt envelope'u:
```json
{
  "answer": "...",
  "confidence": "high|medium|low",
  "sources": [{"type":"transcript","id":42,"snippet":"..."}],
  "fallback_path": null,  // ya da: empty_question, feature_disabled,
                          // empty_retrieval, claude_not_configured,
                          // claude_breaker_open, claude_error,
                          // parse_failed
}
```

Fallback path'lerinin anlamı:
- ``empty_retrieval`` — Qdrant'ta benzer bir şey bulunamadı; RAG kullanılamadı
- ``claude_breaker_open`` — circuit breaker açık (Claude API rate-limit/error)
- ``parse_failed`` — Claude döndü ama beklenen JSON formatında değildi

---

## 5) Troubleshooting

### Sorgu boş dönüyor
1. Koleksiyon mevcut mu: ``GET /rag/collections``
2. Backfill çalıştı mı: log'da ``run_full_backfill completed``
3. Embedding boyutu uyumlu mu: tüm point'lerin dim'i aynı olmalı

### "claude_breaker_open" sürekli düşüyor
1. Claude API rate-limit'e takılmış: ``CLAUDE_RATE_LIMIT_PER_MINUTE``
   env'i kontrol et
2. ANTHROPIC_API_KEY geçerli mi: ``curl -H "x-api-key: $KEY"
   https://api.anthropic.com/v1/models``
3. Breaker manuel sıfırlama: backend restart (in-memory state)

### Index'te eski veri var
``--since-hours`` ile incremental backfill yetmiyor olabilir.
``POST /rag/reindex/{name}`` ile koleksiyonu sıfırla.

---

## 6) Geri alma

Hızlı: ``FEATURE_RAG=false`` env'i set et, backend restart. RAG
endpoint'leri 404 döner, scheduler cron'u no-op'a geçer.

Tam temizlik:
```bash
# Qdrant'tan koleksiyonları sil
for coll in deals interactions competitors; do
  curl -X DELETE -H "api-key: $QDRANT_API_KEY" \
    "$QDRANT_URL/collections/$coll"
done
```

---

## 7) Maliyet izleme

- Qdrant Cloud free tier 1GB → ~50k point. Üstü ücretli.
- sentence-transformers local CPU: ~80ms/embed → 12k embed/dk
- Claude (sadece RAG answer için): retrieved context ~3k token,
  answer ~500 token → $0.015-0.03 per call

Aylık tahmin: 1k RAG sorusu/ay ≈ $20-30 (Claude) + $0 (Qdrant 1GB
altında).
