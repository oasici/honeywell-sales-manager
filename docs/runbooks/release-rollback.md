## Release Runbook: Staging → Prod

### Ön koşullar
- CI yeşil (migrations + schema audit + backend tests + frontend build + e2e smoke)
- Staging ortamı aktif ve smoke test PASS
- Secrets rotasyonu ve erişim kontrolleri tamam

### 1) Staging deploy
1. Yeni image tag’i staging’e deploy et.\n2. `make db-ensure-aligned` (staging DB).\n3. Smoke: `/api/health`, login, `/board`, `/planning-studio`.\n4. Metrik kontrolü: 5xx oranı, p95 latency.\n
### 2) Prod deploy (onaylı adım)
1. Maintenance gerekiyorsa duyuru.\n2. Prod’a aynı image tag’i deploy et.\n3. Migration job: `deploy/k8s/jobs/migrate-job.yaml` (veya pipeline step).\n4. `/api/health` yeşil olana kadar izle.\n
### 3) Rollback
- RollingUpdate health fail / error spike durumunda:\n  1. Deployment’ı önceki image tag’e döndür.\n  2. Eğer migrasyon **geri uyumsuz** ise rollback yapmadan önce DB restore planı çalıştır.\n  3. Trafik normale dönünce postmortem.\n
### 4) Incident checklist
- Olay zamanı, etkilenen fonksiyonlar, log/trace linkleri\n- DB bağlantıları, Redis/Qdrant sağlık\n- Rate limit / AI circuit breaker etkisi\n+
