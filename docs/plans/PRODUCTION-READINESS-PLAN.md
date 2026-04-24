# Production Readiness Plan — Honeywell Sales Suite

**Hedef:** Ürünü "çalışıyor gibi duruyor" seviyesinden "3'te bir müşteri ping'i olmadan uyuyabildiğin" seviyeye çekmek.

**Toplam süre:** ~11 iş günü (solo dev), 5 ayrı PR halinde.
**Kural:** Her PR bağımsız merge edilebilir. Biri fail ederse diğerleri etkilenmez.

---

## PR-0 — Observability Foundation (2 gün)

**Amaç:** Prod'da ne olduğunu bilmemek → her hatanın 30sn içinde haberdar olmak.

### 0.1 Sentry backend entegrasyonu (1.5 saat)

**Yeni dosyalar:** yok
**Değiştirilecek:**
- `backend/requirements.txt` → `sentry-sdk[fastapi]==2.*` ekle
- `backend/app/core/config.py` → `SENTRY_DSN: str = ""`, `SENTRY_TRACES_SAMPLE_RATE: float = 0.1`
- `backend/app/main.py` — lifespan üstünde:

```python
if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENV,
        release=os.getenv("RENDER_GIT_COMMIT", "dev"),
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=0.0,  # enable later if needed
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        before_send=_scrub_pii_before_send,  # strip TCKN/IBAN using ai_trust scrubber
    )
```

**Doğrulama:**
- Staging'e deploy
- `/api/v1/debug/sentry-test` endpoint'i ekle (5xx fırlat) → Sentry dashboard'da görünmeli
- Endpoint'i test sonrası sil

**Rollback:** `SENTRY_DSN=""` set et, SDK no-op'a geçer.

### 0.2 Sentry frontend entegrasyonu (1 saat)

**Değiştirilecek:**
- `frontend/package.json` → `@sentry/react`
- `frontend/src/main.tsx`:

```tsx
import * as Sentry from "@sentry/react";
if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.VITE_ENV,
    release: import.meta.env.VITE_GIT_COMMIT,
    tracesSampleRate: 0.1,
    replaysSessionSampleRate: 0.0,
    replaysOnErrorSampleRate: 1.0,  // only record on errors
    integrations: [Sentry.browserTracingIntegration(), Sentry.replayIntegration()],
  });
}
```

- `App.tsx` → root'u `<Sentry.ErrorBoundary>` ile sar

**Doğrulama:** Test sayfasında `throw new Error("sentry-fe-test")` → 30sn içinde dashboard.

### 0.3 Structured logging + request ID (2 saat)

**Yeni dosyalar:**
- `backend/app/core/logging_config.py` — structlog setup

**Değiştirilecek:**
- `backend/requirements.txt` → `structlog==24.*`
- `backend/app/core/middleware.py` — her request'e UUID atayan `RequestIdMiddleware`:

```python
class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            user_id=getattr(request.state, "user_id", None),
        )
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response
```

- Tüm `print()` + bazı `logger.info("...")` → `log.info("event_name", key=value)` formatına.

**Doğrulama:** `curl -H "x-request-id: test-123"` → Render log'unda `{"event": "...", "request_id": "test-123", ...}` JSON satırı.

### 0.4 Uptime + SLO (1 saat)

**Yeni dosyalar:**
- `docs/SLO.md`:

```markdown
# SLO — Honeywell Sales Suite

| SLI | Target (30d) | Error Budget |
|-----|--------------|--------------|
| Availability (health endpoint) | 99.5% | 3.6 saat / ay |
| API p95 latency | < 500ms | 5% violations |
| API error rate (5xx) | < 1% | - |
| Login success rate | > 95% | - |

Error budget yarısı tükenince: tüm non-critical deploy'lar freeze.
```

**Harici kurulum (Render dashboard dışı):**
- BetterStack Uptime → 3 monitor:
  - `GET https://honeywell-backend.onrender.com/api/health` (60sn)
  - `GET https://honeywell-frontend.onrender.com` (60sn)
  - Playwright synthetic login → dashboard (5dk, mevcut `e2e/auth.spec.ts`)
- Alert kanalı: Slack `#alerts` + email.

### Exit Criteria — PR-0
- [ ] Sentry backend + frontend event gönderiyor
- [ ] Tüm HTTP response'larda `x-request-id` header'ı var
- [ ] Log satırlarının %90+'ı JSON formatında ve request_id içeriyor
- [ ] BetterStack 3 monitor aktif, test alert Slack'e düştü
- [ ] `docs/SLO.md` repo'da

**Tahmini:** 1.5 gün.

---

## PR-1 — Resilience (2 gün)

**Amaç:** Dış bağımlılıklar (Claude, Paraşüt, Logo, Redis) down olunca backend düşmesin; kötü client traffic tüm sistemi patlatmasın.

### 1.1 Circuit breaker — external API calls (3 saat)

**Yeni dosyalar:**
- `backend/app/core/circuit_breaker.py`:

```python
from aiobreaker import CircuitBreaker, CircuitBreakerListener
import structlog

log = structlog.get_logger(__name__)

class LoggingListener(CircuitBreakerListener):
    def state_change(self, cb, old_state, new_state):
        log.warning("circuit_state_change",
                    breaker=cb.name, old=old_state.name, new=new_state.name)

def make_breaker(name: str, fail_max: int = 5, reset_timeout: int = 60) -> CircuitBreaker:
    return CircuitBreaker(name=name, fail_max=fail_max, reset_timeout=reset_timeout,
                          listeners=[LoggingListener()])

claude_breaker = make_breaker("claude", fail_max=5, reset_timeout=60)
parasut_breaker = make_breaker("parasut", fail_max=3, reset_timeout=120)
logo_breaker = make_breaker("logo", fail_max=3, reset_timeout=120)
```

**Değiştirilecek:**
- `backend/app/services/ai_*.py` — Claude client çağrılarını `@claude_breaker` ile sar
- `backend/app/services/erp/adapters/parasut.py` → `@parasut_breaker`
- `backend/app/services/erp/adapters/logo.py` → `@logo_breaker`
- `requirements.txt` → `aiobreaker==1.2.0`

**Graceful degradation:**
- AI endpoint'lerde breaker open → `503` dönüp "AI servisi şu an kullanılamıyor, biraz sonra tekrar deneyin" döndür
- ERP sync breaker open → job'ı queue'da tut, reset timeout sonrası retry

**Doğrulama:**
- Unit test: `tests/test_circuit_breaker.py` — mock 5 failure → breaker open → 6. call fast-fail
- Health endpoint'e breaker state ekle: `"circuits": {"claude": "closed", "parasut": "closed"}`

### 1.2 Rate limit genişletmesi (2 saat)

**Değiştirilecek:**
- `backend/app/core/rate_limit.py` — yeni limiter'lar:

```python
AI_RATE_LIMIT = "60/minute"          # per user, AI endpoint'leri
UPLOAD_RATE_LIMIT = "10/minute"      # per user, PDF/file
WEBHOOK_RATE_LIMIT = "100/minute"    # per IP, webhook
SEARCH_RATE_LIMIT = "120/minute"     # per user, search
```

- `backend/app/api/v1/ai.py` → tüm endpoint'lere `@limiter.limit(AI_RATE_LIMIT, key_func=get_user_id_key)`
- `backend/app/api/v1/quotes.py` (PDF upload) → `@limiter.limit(UPLOAD_RATE_LIMIT)`
- Webhook endpoint'leri (Meta, Slack callbacks) → `@limiter.limit(WEBHOOK_RATE_LIMIT, key_func=get_remote_addr)`

**Doğrulama:** `k6 run` ile 200 req/dk ai endpoint'i → 60 sonrası 429 dönmeli.

### 1.3 DB pool tuning + slow query (1 saat)

**Değiştirilecek:**
- `backend/app/core/database.py`:

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=int(os.getenv("DB_POOL_SIZE", "20")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
    pool_pre_ping=True,
    pool_recycle=300,
    echo_pool=settings.is_development,
)
```

- `.env.example` → yeni env'leri ekle
- `render.yaml` → prod için `DB_POOL_SIZE=20`, `DB_MAX_OVERFLOW=10`

**Slow query log (Render side):**
Render Managed Postgres için custom `postgresql.conf` yok ama Render dashboard → Database → Metrics → Slow Queries otomatik var. Ayda bir top 10'u incele, indeks eksikleri `alembic` revision'a gir.

### 1.4 Redis graceful degradation doğrulama (1 saat)

Sağlık endpoint'i şu anda `redis: error` diyor. Zaten feature-flag'li ama davranış net değil:

**Değiştirilecek:**
- `backend/app/core/redis_client.py` — `get_redis()` None dönünce caller'lar ne yapacak?
- Audit: `grep -r "get_redis()" backend/app/` → her callsite'da `if r is None:` fallback branch'i olmalı
- Unit test: `tests/test_redis_degradation.py` — Redis None iken token revocation, rate limit, session store fallback davranışı.

### Exit Criteria — PR-1
- [ ] Circuit breaker açıkken AI endpoint 503 dönüyor, 60sn sonra otomatik kapanıyor
- [ ] AI rate limit 60/dk test edildi (k6)
- [ ] DB pool 20/10 prod'da aktif
- [ ] Redis down simülasyonu backend'i düşürmüyor
- [ ] Health endpoint circuit state'leri gösteriyor

**Tahmini:** 2 gün.

---

## PR-2 — Data Safety + Compliance (2 gün)

**Amaç:** DB patladığında geri dönecek yerin olsun; KVKK/compliance sorusu geldiğinde evrakın hazır olsun.

### 2.1 Otomatik backup restore drill (3 saat)

**Yeni dosyalar:**
- `backend/scripts/restore_drill.sh`:

```bash
#!/usr/bin/env bash
# Monthly drill: snapshot prod → restore to staging → verify
set -euo pipefail

SNAPSHOT_URL="${PROD_DB_BACKUP_URL}"  # Render → Backups → latest snapshot
STAGING_URL="${STAGING_DATABASE_URL}"

# 1. Create dump from snapshot
pg_dump "${SNAPSHOT_URL}" -Fc -f /tmp/prod-snapshot.dump

# 2. Drop + recreate staging
psql "${STAGING_URL}" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 3. Restore
pg_restore --no-owner --no-acl -d "${STAGING_URL}" /tmp/prod-snapshot.dump

# 4. Verify
USER_COUNT=$(psql "${STAGING_URL}" -tAc "SELECT COUNT(*) FROM users")
OPP_COUNT=$(psql "${STAGING_URL}" -tAc "SELECT COUNT(*) FROM opportunities")
echo "Restored: ${USER_COUNT} users, ${OPP_COUNT} opportunities"
[[ ${USER_COUNT} -gt 0 ]] || { echo "FAIL: no users"; exit 1; }

# 5. Alembic current check
cd backend && DATABASE_URL="${STAGING_URL}" python -m alembic current
```

- `.github/workflows/restore-drill.yml` — ayda 1 kere schedule:

```yaml
name: Monthly Restore Drill
on:
  schedule:
    - cron: "0 3 1 * *"  # her ayın 1'i, 03:00 UTC
  workflow_dispatch:
jobs:
  drill:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: bash backend/scripts/restore_drill.sh
        env:
          PROD_DB_BACKUP_URL: ${{ secrets.PROD_DB_BACKUP_URL }}
          STAGING_DATABASE_URL: ${{ secrets.STAGING_DATABASE_URL }}
      - name: Log result
        if: always()
        run: echo "::notice::Drill $(date +%Y-%m-%d) $([ $? -eq 0 ] && echo PASS || echo FAIL)"
```

- `docs/runbooks/last-restore-drill.md` — her drill sonrası güncellenir (manuel).

### 2.2 Admin audit trail UI (4 saat)

**Yeni dosyalar:**
- `backend/app/api/v1/audit.py`:

```python
router = APIRouter(prefix="/audit", tags=["Audit"])

@router.get("/events")
async def list_audit_events(
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    """Audit trail query for admin/compliance review."""
    # Field audit tablosunu sorgula (SQLAlchemy before_flush listener'ın yazdığı)

@router.get("/export/{user_id}")
async def export_user_data(user_id: int, ...):
    """KVKK: tüm kullanıcı verilerini JSON olarak dön."""
```

- `frontend/src/features/admin/AuditTrailPage.tsx` — filter form + sonuç tablosu + CSV export
- `frontend/src/features/admin/DataExportPage.tsx` — kullanıcı seç → "Export KVKK" → JSON indir

**Değiştirilecek:**
- `backend/app/api/v1/router.py` → audit router'ı mount et
- `frontend/src/app/App.tsx` → `/admin/audit`, `/admin/kvkk-export` route'ları
- `frontend/src/components/layout/Sidebar.tsx` → Admin altında "Audit Trail" + "Data Export"

### 2.3 KVKK data retention cron (1 saat)

`docs/runbooks/kvkk-retention-anonymize.md` var ama job aktif mi?

**Değiştirilecek:**
- `backend/app/services/scheduler.py` → gece 03:00:
  - `OldEmailRequest` (>2 yıl) → PII alanlarını NULL
  - `ClosedOpportunity` (>3 yıl) → customer_email/phone anonimleştir
  - `InactiveUser` (>1 yıl giriş yapmamış) → soft delete (`is_active=false`)
- Her anonimleştirme → audit log satırı

**Doğrulama:** Staging'de eski tarihli test kaydı oluştur, cron'u manuel tetikle, anonim oldu mu bak.

### Exit Criteria — PR-2
- [ ] Monthly restore drill CI'da schedule'lanmış, ilk çalışma başarılı
- [ ] `/admin/audit` UI'da filter + tablo çalışıyor
- [ ] `/admin/kvkk-export/:user_id` JSON döndürüyor
- [ ] KVKK retention cron'u staging'de doğrulandı

**Tahmini:** 2 gün.

---

## PR-3 — Quality Gates + Chaos (3 gün)

**Amaç:** "Çalışıyor olmalı" yerine "kanıtlayarak çalışıyor". Kapasiteni bil, drill yap, automated guard'ları kurgula.

### 3.1 k6 load test suite (1 gün)

**Yeni dosyalar:**
- `load-test/smoke.js` — 10 user, 1 dakika, sanity check
- `load-test/baseline.js` — 50 user, 10 dakika, tipik prod yükü
- `load-test/stress.js` — 100→500 user ramp, kırılma noktası
- `load-test/soak.js` — 30 user, 2 saat, memory leak tespit
- `load-test/scenarios/login-flow.js`, `quote-create.js`, `ai-draft.js` — user journey'leri
- `load-test/README.md` — nasıl çalıştırılır + beklenen sonuçlar

Örnek `baseline.js`:
```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 50 },
    { duration: '10m', target: 50 },
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'https://honeywell-backend.onrender.com';

export function setup() {
  // Login, return token
}

export default function(data) {
  const res = http.get(`${BASE_URL}/api/v1/opportunities/`, {
    headers: { Authorization: `Bearer ${data.token}` },
  });
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(1);
}
```

**CI entegrasyonu:**
- `.github/workflows/load-test.yml` — weekly sunday 02:00 UTC, staging'e koş, sonuçları artifact olarak kaydet
- Regression detection: baseline vs mevcut → p95 %20+ regresyon → GitHub issue aç

**Doğrulama:** İlk koşu sonuçları `docs/performance/baseline.md`'ye yaz.

### 3.2 Dependabot + security audit (2 saat)

**Yeni dosyalar:**
- `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/backend"
    schedule: { interval: "weekly", day: "monday" }
    open-pull-requests-limit: 5
    labels: ["deps", "backend"]
  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule: { interval: "weekly", day: "monday" }
    groups:
      react-ecosystem:
        patterns: ["react*", "@tanstack/*"]
      dev-deps:
        dependency-type: "development"
    labels: ["deps", "frontend"]
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule: { interval: "monthly" }
```

**Değiştirilecek:**
- `.github/workflows/ci.yml` → yeni `security-audit` job:

```yaml
security-audit:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Python audit
      run: |
        cd backend && pip install pip-audit && pip-audit --strict -f json > audit.json
    - name: Node audit
      run: |
        cd frontend && npm audit --audit-level=high --json > audit.json
    - name: Fail on high+
      run: |
        # parse + fail if any HIGH or CRITICAL
```

### 3.3 Incident response game day (1 gün)

**Yeni dosyalar:**
- `docs/runbooks/game-day-scenarios.md` — 5 senaryo:
  1. DB connection lost (Render panelden connection string bozul)
  2. Redis down (container kill)
  3. Claude API 500 (mock ile simulate)
  4. Disk full (/tmp 95%+)
  5. Memory leak (koşturduğunda RAM artıyor)

- `docs/runbooks/game-day-log.md` — her drill sonrası: tarih, senaryo, detection süresi, resolution süresi, iyileştirme listesi

**Koşum:** Her ay bir perşembe 14:00-16:00, staging'de.

### 3.4 Test coverage gate (2 saat)

**Değiştirilecek:**
- `backend/pytest.ini` (yoksa oluştur):

```ini
[pytest]
addopts = --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=80
```

- `.github/workflows/ci.yml` → `backend-test` job:

```yaml
- name: Coverage gate
  run: pytest --cov=app --cov-fail-under=80
- name: Upload coverage
  uses: codecov/codecov-action@v4
```

- Frontend için `vitest.config.ts` → `coverage: { thresholds: { lines: 75, functions: 75, branches: 70 } }`

**Not:** Mevcut coverage'ı ölç → %80 altındaysa threshold'u aşağı başlat, sprint'ler boyunca artır.

### Exit Criteria — PR-3
- [ ] k6 baseline: 50 user 10dk'da p95 < 500ms, error < 1% (staging)
- [ ] Dependabot weekly PR açıyor
- [ ] pip-audit + npm audit CI'da gate
- [ ] İlk game day drill tamamlandı, `game-day-log.md`'ye yazıldı
- [ ] Coverage gate %80+ (backend), %75+ (frontend)

**Tahmini:** 3 gün.

---

## PR-4 — Polish + Process (2 gün)

**Amaç:** Son %5 — dışarıdan profesyonel görünmek + iç operasyonu oturtmak.

### 4.1 CHANGELOG + release automation (2 saat)

**Yeni dosyalar:**
- `CHANGELOG.md` — Keep a Changelog formatı:

```markdown
# Changelog

## [Unreleased]

## [2.1.0] - 2026-04-24
### Added
- Insights dashboard with conversation intelligence
- High-intent account detection
### Security
- Async-safe JWT revocation (Redis-backed)
### Fixed
- PDF parser concurrency bug
```

- `.github/workflows/release.yml` — main'e her merge'de:
  - Conventional commit parse
  - `CHANGELOG.md` otomatik güncelle
  - Git tag `vX.Y.Z` oluştur
  - GitHub Release notes = changelog entry

- `release-please-config.json` veya manuel script.

### 4.2 CSP + security headers tightening (1 saat)

**Değiştirilecek:**
- `render.yaml` → frontend headers:
  - `Content-Security-Policy` → `script-src` nonce bazlı (şu an `'self'`)
  - `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
  - `X-Permitted-Cross-Domain-Policies: none`
- `frontend/vite.config.ts` → build'de CSP nonce placeholder üret

**Sentry için exception:** `connect-src` → `*.sentry.io` eklemen gerek.

**Doğrulama:** https://securityheaders.com'a site URL'i → A+ hedef.

### 4.3 .env.example + flag documentation (1 saat)

**Değiştirilecek:**
- `.env.example` — yeni tüm env'ler:
  - `SENTRY_DSN`, `VITE_SENTRY_DSN`
  - `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`
  - `FEATURE_*` tüm flag'ler + açıklamaları
  - `CLAUDE_RATE_LIMIT`, `AI_RATE_LIMIT`
- `docs/feature-flags.md` — her flag için: default, amaç, bağımlılıklar, rollback.

### 4.4 On-call playbook (2 saat)

**Yeni dosyalar:**
- `docs/runbooks/oncall-playbook.md` — tek sayfa cheatsheet:

```markdown
# On-Call Playbook

## Slack #alerts'e bir şey düştü. İlk 5 dakika:

1. Sentry dashboard aç → son 15dk event volume
2. BetterStack → hangi monitor kırmızı
3. Render → honeywell-backend → Logs son 5dk
4. DB healthy mi: curl /api/health

## Sık karşılaşılan senaryolar

| Alert | Muhtemel sebep | İlk aksiyon |
|-------|----------------|-------------|
| 5xx rate spike | Migration fail veya external API | Sentry → top issue |
| p95 latency > 1s | DB slow query veya N+1 | pg_stat_statements |
| Memory > 80% | Leak veya PDF queue dolmuş | Pod restart + profiling |
| Login 401 spike | Brute force veya JWT rotation | Rate limit log |

## Rollback

```bash
# Render dashboard → Deploys → önceki sürümü "Rollback"
# veya git revert + push
git revert <commit-sha>
git push origin main
```
```

### 4.5 Customer communication templates (1 saat)

**Yeni dosyalar:**
- `docs/customer-comms/incident-template.md` — müşteriye incident bildiği:

```markdown
Konu: Honeywell Sales Suite — Servis Kesintisi [DATE]

Merhaba,

[TIME] itibariyle [DURATION] süreyle servisimizde kesinti yaşanmıştır.
Etkilenen bileşen: [COMPONENT]
Kök sebep: [ROOT_CAUSE]
Alınan önlemler: [MITIGATION]

Üzüntüyle karşıladığımız bu olay için detaylı post-mortem raporumuz
[DATE+7]'de paylaşılacaktır.

İyi günler dileriz,
Honeywell Sales Suite Team
```

- `docs/customer-comms/release-template.md` — feature release için
- `docs/customer-comms/security-disclosure.md` — güvenlik bildirimi için

### Exit Criteria — PR-4
- [ ] `CHANGELOG.md` otomatik güncelleniyor
- [ ] securityheaders.com A+ rating
- [ ] `.env.example` tüm flag'leri içeriyor
- [ ] On-call playbook merge edildi
- [ ] 3 customer comm template'i hazır

**Tahmini:** 1.5 gün.

---

## Bağımlılık grafı

```
PR-0 (observability) ────┐
                         │
                         ▼
           PR-1 (resilience) — Sentry lazım (circuit state'i logla)
                         │
                         ▼
           PR-2 (data safety) — audit UI log'lara bağlı
                         │
                         ▼
           PR-3 (quality) — load test Sentry'ye yansır
                         │
                         ▼
           PR-4 (polish)
```

**PR-0 olmadan diğerleri düzgün validate edilemez.** Sıra: 0 → 1 → 2 → 3 → 4.

---

## Özet tablo

| PR | Odak | Süre | Ana output |
|----|------|------|-----------|
| PR-0 | Observability | 1.5 gün | Sentry + structlog + uptime + SLO |
| PR-1 | Resilience | 2 gün | Circuit breaker + rate limit + pool |
| PR-2 | Data safety | 2 gün | Restore drill + audit UI + KVKK cron |
| PR-3 | Quality gates | 3 gün | k6 + dependabot + game day + coverage |
| PR-4 | Polish | 1.5 gün | CHANGELOG + CSP + playbook + templates |
| **Toplam** | | **~11 gün** | |

---

## Yeni Secret'lar (Render + GitHub)

### Render Environment Variables (backend)
- `SENTRY_DSN` — Sentry project DSN
- `SENTRY_TRACES_SAMPLE_RATE` — default 0.1
- `DB_POOL_SIZE` — default 20
- `DB_MAX_OVERFLOW` — default 10
- `DB_POOL_TIMEOUT` — default 30

### Render Environment Variables (frontend)
- `VITE_SENTRY_DSN`
- `VITE_GIT_COMMIT` — Render otomatik (`RENDER_GIT_COMMIT`)
- `VITE_ENV` — production/sandbox

### GitHub Actions Secrets
- `PROD_DB_BACKUP_URL` — monthly restore drill için
- `STAGING_DATABASE_URL` — restore hedefi
- `CODECOV_TOKEN` — coverage upload
- `SLACK_WEBHOOK_URL` — alert bildirimi

---

## Başlama sırası önerisi

**Hafta 1:** PR-0 (observability) — diğer her şey bunun üzerine kuruluyor.
**Hafta 2:** PR-1 (resilience) — en büyük prod riskini (external API) kapatır.
**Hafta 3:** PR-2 (data safety) — gece uyuyabilmek için.
**Hafta 4:** PR-3 (quality gates) — kapasite bilgisi + drill.
**Hafta 5:** PR-4 (polish) — müşteri görünümü.

Her PR kendi branch'inde, kendi CI run'unda, kendi deploy'unda. Takıldığın PR bir sonraki PR'ı blokalamıyor çünkü bağımlılık tek yönlü.

---

## İlerleme takibi

Her PR bittiğinde bu dosyanın alt kısmına:

```markdown
## Completion Log

- [x] PR-0 merged 2026-04-26 (commit: abc123)
- [ ] PR-1 in progress
- [ ] PR-2 blocked on PR-0
...
```

satırı ekle. Sprint retro'da hangi tahmini tutturmadığına bak, bir sonraki PR için düzelt.
