# Game Day Scenarios

Aylık 2 saatlik kontrollü kaos tatbikatı. Her senaryo staging'de
gerçekleştirilir; prod'a asla dokunulmaz. Amaç:

- Detection süresini ölç (alarm tetikleme süresi)
- Resolution süresini ölç (recovery süresi)
- Runbook eksiklerini bul
- On-call rotasyonunu pratiğe sok

> **Asla prod'da koşma.** Her senaryo staging deployment'ında
> çalıştırılır. Prod-benzeri davranış almak için staging'in DB ve
> Redis tier'larını mümkün olduğunca prod'a yakın tut.

## Genel Akış

1. **Hazırlık (10 dk)**
   - Slack `#alerts`'i aç
   - Sentry dashboard'ı aç
   - Render staging logs'u aç
   - Stop watch hazırla
2. **Senaryo (5-15 dk)**
   - Failure'ı tetikle
   - Detection süresini kaydet (ilk alarm gelene kadar)
3. **Triage + Recovery (15-30 dk)**
   - Runbook'u takip et
   - Resolution süresini kaydet
4. **Retro (15 dk)**
   - `last-game-day.md`'ye sonuçları yaz
   - Eksik runbook adımlarını TODO'ya at

## Senaryo 1: DB connection lost

**Tetikleme:**
Render dashboard → staging Postgres → "Suspend". Backend connection
pool yenilenmeyi 5-10sn içinde keşfeder.

**Beklenen davranış:**
- Health endpoint `database: error` raporlar
- Sentry'de `OperationalError` event'leri spike
- Yeni request'ler 500 döner ama backend süreci çalışır kalır
- Resume sonrası 60-90sn içinde recovery

**Ölçüm:**
- Detection: ilk Sentry alert'ten itibaren süre
- Recovery: DB resume sonrası ilk başarılı health check

**Triage:** [`db-backup-restore.md`](db-backup-restore.md) — connection
loss değil ama DB-side incident playbook aynı.

## Senaryo 2: Redis down

**Tetikleme:**
Render dashboard → Redis instance → restart (veya Docker compose
varsa `docker stop redis`).

**Beklenen davranış:**
- Health endpoint `redis: error` raporlar (PR-1.4 fix sayesinde gerçek
  durumu yansıtır, eski "error" mismatch'i değil)
- Token revocation memory fallback'e düşer (PR-1 testleri kapsıyor)
- Rate limit memory'e düşer — multi-worker'da rate limit "leaky"
- AI summary cache miss → her istek backend hit eder, latency artar
- App ayağa kalkmaya devam eder, 5xx rate < %1 kalmalı

**Ölçüm:**
- AI endpoint p95 latency artışı (Redis cache miss etkisi)
- Token revocation davranışı: revoked token hâlâ reject ediliyor mu?

**Triage:** Redis down ise alarm; ancak fallback sayesinde page-out
gerekmez. Saatler içinde restart.

## Senaryo 3: Claude API 500

**Tetikleme:**
Bir mock proxy ile Anthropic'i 5xx döndürmeye zorla. Veya hızlı
yöntem: `ANTHROPIC_API_KEY` env'ini geçersiz bir değerle değiştir
ve backend'i restart et.

**Beklenen davranış:**
- 3 ardışık fail sonrası `claude_breaker` open'a geçer (PR-1.1)
- Health endpoint `circuits.claude_api.state: "open"` döner
- Status `degraded`, UptimeRobot/BetterStack alarm verir
- AI endpoint'leri `_empty_result()` veya rule-based fallback döner
  — 500 değil, graceful degradation
- 30sn sonra half_open, bir başarılı çağrıdan sonra closed

**Ölçüm:**
- Detection: ilk breaker open log'u → ilk degraded health response
- Recovery: API restore sonrası ilk başarılı Claude call'a kadar süre
  (≤ 60sn olmalı)

**Triage:** Breaker open log + Sentry → Anthropic status page kontrolü.

## Senaryo 4: Disk dolu

**Tetikleme:**
Staging container'da `/tmp` doldur:

```bash
dd if=/dev/zero of=/tmp/filler bs=1M count=4096
```

PDF parser semaphore kullanıyor, /tmp'ye yazıyor.

**Beklenen davranış:**
- PDF upload endpoint 500 döner (`No space left on device`)
- Diğer endpoint'ler etkilenmez (cache + temp dosyalar)
- Sentry'de upload-spesifik error spike
- App restart gerekmez; `rm /tmp/filler` ile çözülür

**Ölçüm:**
- PDF endpoint error rate spike → diğer endpoint'lerde bağımsızlık

**Triage:** Disk monitor kurulu mu? Render free tier metrik vermez —
manuel `df -h` ile doğrula. Long-term: alert kuralı + temp cleanup
cron.

## Senaryo 5: Memory leak / RSS climb

**Tetikleme:**
Soak load test'i çalıştır (`k6 run soak.js`, 2 saat). RSS
metric'lerini izle.

**Beklenen davranış (sağlıklı):**
- RSS ilk 30dk'da plato (warmup)
- Sonra düz kalır, ±50MB oynar
- Cron'lar tetiklendiğinde geçici ±100MB

**Beklenen davranış (sızıntı):**
- Saatte ~50MB veya daha fazla doğrusal artış
- 2 saat sonunda OOM kill veya restart

**Ölçüm:**
- 2 saatte RSS değişimi
- p95 latency drift (ilk 10 dk vs son 10 dk)

**Triage:** Sızıntı bulunursa `py-spy dump --pid <PID>` veya
`tracemalloc` ile heap snapshot. Modeller, claude_parser'ın
LRU cache'i, vector store eviction kontrolü.

## Game Day Log Şablonu

Her tatbikatın sonunda `docs/runbooks/last-game-day.md`'ye ekle:

```markdown
## YYYY-MM-DD — Game Day

**Operatör:** <name>
**Süre:** 14:00–16:00 TR
**Senaryolar:** 1, 3 (other 3 deferred to next month)

### Senaryo 1: DB connection lost
- Detection: 2dk 14sn
- Recovery: 1dk 47sn (resume sonrası)
- Sentry alert ulaştı: ✓
- Health endpoint `database: error` döndü: ✓
- Notes: Render suspend butonu reactivation 30sn sürdü, beklenenden uzun

### Senaryo 3: Claude API 500
- Detection: 1dk 03sn (3 ardışık fail için)
- Recovery: 35sn (half_open → closed)
- Breaker davranışı plana uydu: ✓
- Notes: Status `degraded`'a geçti, BetterStack alarm verdi.
  Half_open testi: ilk başarılı request 28sn sonra geçti.

### Aksiyon Listesi
- [ ] Render reactivation süresi runbook'a eklenecek (DB)
- [ ] PDF upload disk-full senaryosu monitor eksik — Sentry custom error
      tag eklenmeli
```

## Senaryo 6: Qdrant down (V11 RAG)

**Failure:** Qdrant servisini durdur (docker stop veya QDRANT_URL'i
geçersiz hostname'e çevir).

**Beklenen davranış:**
- `POST /v1/rag/answer` 200 döner ama envelope'da
  `fallback_path: "empty_retrieval"` set olur (RAG değil keyword fallback)
- `POST /v1/rag/search/*` 200 döner, `items: []`
- Scheduler `rag_incremental_backfill` cron'u Sentry'ye exception düşer
  ama backend health'i etkilenmez

**Detection:** Sentry `qdrant_search_failed` event spike.

**Recovery:** Qdrant ayağa kalkınca otomatik düzelir; manuel veri
kaybı yoksa reindex gerekmez (V11 backfill cron sonraki gün delta'yı
tamamlar).

**Beklenen süre:** Detection ≤ 2 dk, recovery = Qdrant restart süresi.

**Runbook:** `docs/runbooks/v11-rag-backfill.md`

---

## Senaryo 7: Transformer model load fail (V12 sequence embedding)

**Failure:** ``sentence-transformers`` paketini venv'den kaldır
(`pip uninstall sentence-transformers`) ya da disk'i model cache'i
silinerek download'ı bloklar hâle getir.

**Beklenen davranış:**
- ``deal_similarity_service.refresh_similarity_links`` her opp için
  V8 3-component blend'e fallback yapar (cosine + LCS + text BoW)
- Sentry'de ``transformer encoder unavailable for opp ...`` warning
- ``DealSimilarityLink.method`` field'i ``cosine+lcs+text`` (not +xfm)

**Detection:** Sentry warning rate spike + Sales analytics dashboard'da
similarity refresh süresi düşer (transformer encode skip).

**Recovery:** Paketi reinstall + backend restart. Model ilk request'te
re-download.

**Beklenen süre:** Detection ≤ 5 dk, recovery ≈ 2-3 dk (model download).

**Runbook:** `docs/runbooks/v12-transformer-backfill.md`

---

## Senaryo 8: Cross-tenant ID enumeration attack (V12 multi-tenant)

**Failure:** Kullanıcı A (tenant 1) ile token al, sırayla
``GET /opportunities/1``, ``GET /opportunities/2``, ... probe et.
Tenant 2'nin ID'lerine kadar git.

**Beklenen davranış:**
- Tüm cross-tenant probe'lar 404 döner (assert_same_tenant guard)
- ``http_requests_total{status="404"}`` artar ama tenant 2'nin
  hassas verisi sızmaz
- Audit log'da hiçbir cross-tenant access kaydedilmez (V13 tenant scoped read)

**Detection:** Custom Sentry alert: tek user'dan dakikada 10+ 404
geliyorsa potansiyel ID enumeration. Henüz kurulu değil → P3 backlog.

**Recovery:** Patolojikse user'ı suspend; rate-limit otomatik
devreye girer (P2.5 per-tenant rate limit).

**Beklenen süre:** Detection ≤ 5 dk (manuel log inceleme),
recovery = anında.

**Runbook:** `docs/runbooks/v12-multi-tenant-rollout.md`

---

## Senaryo 9: V10 parts intel data drift

**Failure:** Bir gecede 100+ yeni SparePart import et (Excel ile);
hepsinin ``supplier_price=NULL``.

**Beklenen davranış:**
- ``GET /v10/parts-intel/dead-stock`` listesi şişer (yeni parçalar
  hiç quote'lanmadı + supplier_price=0 → frozen capital total = 0)
- ``GET /v10/parts-intel/data-health`` ``value`` puanı 100'den ~60'a
  düşer (supplier_price field doldurulma oranı düşer)
- Manager dashboard'da "Veri Sağlığı" kartında driver breakdown
  ``supplier_price`` bar'ı kırmızıya geçer

**Detection:** Manager dashboard veya alert kuralı (data_health < 75).

**Recovery:** Excel import'ta ``supplier_price`` kolonu eksik —
import şablonu güncellenmeli, eski rows ``UPDATE spare_parts SET
supplier_price = ...`` ile arkadan doldurulmalı.

**Beklenen süre:** Detection ≤ 24 saat (next-day data health
review), recovery = elle.

**Runbook:** `docs/runbooks/v10-parts-intel.md`

---

## Eksik / Gelecek

- Otomatik runner (chaos engineering tool) — şu an manuel
- Prod canary trafiği ile entegrasyon
- Synthetic transaction (login → opportunity create) Game Day'in
  içinde otomatik koşsun
- Cross-tenant ID enumeration için Sentry alert kuralı (P3 backlog)
- V11/V12/V13 senaryolarının staging'de gerçekten koşturulması
