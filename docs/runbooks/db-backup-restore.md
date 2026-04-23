## DB Runbook: Backup / PITR / Restore

Bu runbook, Kubernetes üzerinde yönetilen Postgres (önerilen) veya kendi Postgres kurulumunda
geri dönüş (restore) prosedürünü standartlaştırır.

### Hedefler
- **RPO**: maksimum veri kaybı toleransı (örn. 15 dk)
- **RTO**: servis geri dönüş süresi (örn. 60 dk)

### 1) Yedekleme stratejisi
- **Günlük tam yedek** + **WAL arşivi** (PITR)
- Yedekler şifreli ve ayrı bir storage’a (S3/GCS) yazılmalı
- Retention: ör. 30 gün

### 2) Migrasyon politikası (regülasyonlu prod)
- Prod’da şema değişikliği **sadece Alembic** ile yapılır.
- Deploy pipeline’da:\n  1) staging’de `make db-ensure-aligned`\n  2) smoke test\n  3) prod’da onaylı adım: `make db-ensure-aligned`\n- “expand/contract” prensibi: önce ekle, sonra kullan, en son kaldır.

### 3) Restore (genel akış)
1. Incident kaydı aç, durumu “sev1/sev2” sınıflandır.\n2. Prod yazma trafiğini durdur (maintenance mode / ingress deny).\n3. Restore hedef zamanını belirle (PITR timestamp).\n4. Yeni DB instance’a restore et.\n5. Uygulamayı staging benzeri smoke test ile doğrula.\n6. DNS/connection string’i yeni DB’ye çevir.\n7. Trafiği aç ve metrikleri izle.\n
### 4) Doğrulama checklist’i
- `alembic current` beklenen head mi?\n- Kritik tablolar satır sayıları anomali var mı?\n- Uygulama health: `/api/health`\n- Login + board + planning-studio smoke\n+
