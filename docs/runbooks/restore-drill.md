# Restore Drill Runbook

Aylık prod backup → staging restore tatbikatı. Backup integrity'yi gerçek
incident anında değil, kontrollü ortamda doğrular.

## Workflow

- **Cron:** Her ayın 1'inde 03:00 UTC (06:00 TR)
- **CI:** [`.github/workflows/restore-drill.yml`](../../.github/workflows/restore-drill.yml)
- **Script:** [`backend/scripts/restore_drill.sh`](../../backend/scripts/restore_drill.sh)

## Required GitHub Secrets

| Secret | Açıklama |
|--------|---------|
| `PROD_DB_BACKUP_URL` | Read-only Postgres URL — drill `pg_dump` ile bunu okur. Render dashboard → Database → Connection String → "External". |
| `STAGING_DATABASE_URL` | Drill restore hedefi. **Asla prod URL koyma.** Script `prod`/`production` substring varsa fatal hata atar. |

> Setup: GitHub repo → Settings → Secrets and variables → Actions → New
> repository secret. Hem secret değerinin doğru olduğundan hem de
> hedeflerin gerçekten ayrı olduğundan emin ol.

## Manual Trigger

CI sayfasından "Run workflow" → opsiyonel olarak `MIN_USERS` ve
`MIN_OPPORTUNITIES` floor'larını override et.

```bash
gh workflow run restore-drill.yml \
  -f min_users=50 \
  -f min_opportunities=20
```

## Drill PASS

CI logu `Drill PASSED in Ns (users=N, opportunities=N)` çıkarır. Sonuç
`docs/runbooks/last-restore-drill.md`'ye manuel olarak yazılır:

```markdown
## 2026-05-01

- Status: PASS
- Duration: 142s
- Restored: 1,847 users / 3,219 opportunities
- Alembic head: matched
- Notes: clean run.
```

## Drill FAIL — Triage

Drill fail → **backup integrity at risk**. 4 olası senaryo:

### 1. `pg_dump` failed

Prod DB'ye erişim koptu, credentials expired veya network filter
değişti. Çözüm:

1. `PROD_DB_BACKUP_URL` secret'ı Render dashboard'daki güncel string ile
   değiştir.
2. Read-only kullanıcı login yapabiliyor mu doğrula:
   `psql "$PROD_DB_BACKUP_URL" -c "SELECT 1"`.

### 2. `pg_restore` failed

Dump dosyası corrupt veya staging'de uyumsuz Postgres versiyonu.
Çözüm:

1. CI logundan dump boyutunu kontrol et — < 1KB ise prod'da real backup
   yok demektir, P1 incident.
2. Workflow'da `postgresql-client-16` versiyonunu prod cluster ile
   eşleştir.

### 3. Row floor breached

Restored DB'de `users` veya `opportunities` sayısı `MIN_*` altında. Üç
olasılık:

- **Backup boş veya kısmi:** Render dashboard'da en son backup
  timestamp'ine bak. Saatler önce tamamlanan bir backup beklenmiyor.
- **Floor yanlış set edilmiş:** Üretim küçük tutuluyorsa
  `MIN_OPPORTUNITIES=0` set et (default).
- **Anonymization cron prod'u sildi:** KVKK retention cron'u
  yanlışlıkla aktif satırları silmiş olabilir, audit log'a bak.

### 4. Alembic head mismatch

Restored DB code'un beklediği migration head'inden farklı revision'da.
Genellikle alarm değil:

- Backup zaman damgası deploy öncesi olabilir.
- Üst üste deploy varsa beklenen davranış.

`(head)` görünmüyorsa CI sadece `WARN` basar, fail etmez. Drill
PASS sayılır.

## Eksik / Geliştirme

- [ ] Slack/email bildirimi (workflow başında/sonunda webhook çağrısı).
- [ ] `last-restore-drill.md` otomatik update — şu an manuel.
- [ ] Production-grade drill: restore edilen staging'e backend'i de bağla,
      synthetic login geçtiğini doğrula.
