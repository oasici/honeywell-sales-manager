# V12 Transformer Sequence Embedding — Operations Runbook

V12 kapsamı:
- ``services/transformer_sequence_embedder.py`` — sentence-transformers
  paraphrase-multilingual-MiniLM-L12-v2 ile 384-dim sequence embedding
- ``services/transformer_seq_repository.py`` — upsert + bulk backfill
- ``models/v12_transformer_seq_embedding.py`` — yeni tablo
  ``opportunity_transformer_seq_embeddings``
- ``alembic/20260428_v12_transformer_seq_embedding.py`` — migration
- ``services/deal_similarity_service.refresh_similarity_links`` —
  4-component blend (V8 BoW + V12 transformer + LCS + structured)
- ``scripts/backfill_transformer_seq.py`` — backfill CLI
- ``FEATURE_TRANSFORMER_SEQ_EMBEDDING`` — default false

V12 = V8'in 256-dim BoW *şekil* embedding'inin üzerine, semantik
**transformer-based** embedding katmanı. Aynı multilingual MiniLM
modeli spare parts catalog'da zaten yüklü; ek RAM/disk maliyeti yok.

---

## 0) Önkoşullar

- Migration head: ``20260428_v12_transformer_seq``
- ``sentence-transformers`` paketi requirements'ta (zaten var,
  RAG için)
- ``FEATURE_TRANSFORMER_SEQ_EMBEDDING=false`` başlangıçta kapalı
  bırakılır — backfill çalışmadan blend devreye girmez

---

## 1) İlk backfill

### 1.1 Smoke test (local'den prod'a)
```bash
DATABASE_URL=<prod_url> FEATURE_TRANSFORMER_SEQ_EMBEDDING=true \
  python -m scripts.backfill_transformer_seq \
  --opp 42 --apply
# Tek opportunity → tek embedding row
```

Çıktı:
```
processed=1 written=1 skipped=0
```

### 1.2 Full backfill
```bash
DATABASE_URL=<prod_url> FEATURE_TRANSFORMER_SEQ_EMBEDDING=true \
  python -m scripts.backfill_transformer_seq --apply
```

Süre tahmini:
- 100 opportunity → ~30 sn (model warm + 100 encode)
- 1000 opp → ~3-5 dk
- 10k opp → ~30-50 dk

Idempotent — re-running aynı satırları upsert eder. Çalışırken
``processed`` ile ``written + skipped`` toplamı eşleşmeli.

### 1.3 Veriyi doğrula
```sql
SELECT COUNT(*) AS total,
       MIN(generated_at) AS oldest,
       MAX(generated_at) AS newest
FROM opportunity_transformer_seq_embeddings;
```

---

## 2) Feature flag açma

Backfill tamamlandıktan **sonra**:

```bash
# Render dashboard
FEATURE_TRANSFORMER_SEQ_EMBEDDING=true
# Backend restart
```

Şimdi ``deal_similarity_service.refresh_similarity_links`` 4-component
blend kullanır:
```
final = 0.4·cos_struct + 0.15·LCS + 0.25·cos_text + 0.2·cos_xfm
```

Transformer satırı yoksa otomatik V8 3-component'e (0.5+0.2+0.3)
fallback yapar — yani mixed state güvenli.

---

## 3) Doğrulama

```bash
# Bir opportunity için similarity refresh çağır
curl -X POST -H "Authorization: Bearer $TOKEN" \
  $API/v1/v5-intelligence/opportunities/<id>/refresh-similarity

# Sonra similar links'e bak — reason JSON'unda
# "method":"cosine+lcs+text+xfm" geçmesi gerek
curl -s -H "Authorization: Bearer $TOKEN" \
  $API/v1/v5-intelligence/opportunities/<id>/similar | jq '.items[0]'
```

Beklenen yapı:
```json
{
  "similar_opportunity_id": 42,
  "similarity_score": 0.847,
  "similarity_reason_json": {
    "method": "cosine+lcs+text+xfm",
    "cosine_score": 0.82,
    "sequence_score": 0.71,
    "text_score": 0.85,
    "transformer_score": 0.93
  }
}
```

``method`` ``cosine+lcs+text`` ise → V12 vektörü o opportunity için
yok, V8 fallback kullanılıyor. Backfill kontrolü gerek.

---

## 4) Vocab drift

Tokenizer vocabulary değişirse (``sequence_tokenizer`` updated)
mevcut vektörler geçerliliğini yitirir. Detect:

```sql
SELECT vocab_hash, COUNT(*)
FROM opportunity_transformer_seq_embeddings
GROUP BY vocab_hash
ORDER BY 2 DESC;
```

Birden fazla farklı vocab_hash görünüyorsa (özellikle 1 hakim ve
küçük bir azınlık varsa) → azınlık eski vocab'tan kalma. Re-encode:

```bash
python -m scripts.backfill_transformer_seq --apply
# Yeni vocab tüm satırlara yazılır (upsert)
```

---

## 5) Maliyet + performans

- Model (paraphrase-multilingual-MiniLM-L12-v2): ~90MB disk, ~400MB
  RAM warm, ilk encode ~2-3 sn, sonraki ~50ms (CPU)
- Render starter tier (512MB RAM) yetersiz olabilir → standard tier
  öner
- Encode sıklığı: opportunity events stream'inde ``stage_change``
  etmenleri tetiklerse ortalama günde ~10 encode/opportunity
- Backfill'i nightly cron'a koymadık çünkü on-write hooks yeterli;
  ihtiyaç olursa scheduler.py'a 03:00 cron eklenebilir

---

## 6) Geri alma

```bash
# Kapalı duruma çek
FEATURE_TRANSFORMER_SEQ_EMBEDDING=false
# Backend restart
# Blend otomatik V8 3-component'e düşer
```

Tablo silmek istersen migration downgrade:
```bash
DATABASE_URL=<prod> python -m alembic downgrade 20260428_v9_quote_revisions
# Tabloyu siler — geri almak için tekrar upgrade + backfill
```

---

## 7) Bilinen sınırlamalar

- Model cold start ilk request'te ~2-3 sn — eğer blend "tek-shot"
  request'te tetikleniyorsa lazy load ilk kullanıcıya yansır.
  Workaround: backend startup'ta ``transformer_sequence_embedder._get_model()``
  çağırarak warm yap.
- Vektör boyutu 384 sabit — model değişikliği migration gerektirir.
- Multilingual model TR + EN için iyi ama domain-spesifik (spare
  parts) terimlerde fine-tune yok. Production accuracy ölçümü için
  V13 backlog'unda eval suite var.
