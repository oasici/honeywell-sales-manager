## Güvenlik Runbook: Secrets & Rotasyon

Bu ürün (regülasyonlu prod hedefi) için **hiçbir secret** (DB şifresi, JWT secret, ENCRYPTION_KEY, API key) git’e veya CI loglarına yazılmamalıdır.

### 1) Minimum secret listesi
- **DATABASE_URL**: yalnızca Secret Manager/K8s Secret üzerinden
- **JWT_SECRET_KEY**: uzun (≥32 karakter) ve rotasyon planlı
- **ENCRYPTION_KEY**: KMS/Secret Manager; rotasyon prosedürü yazılı olmalı
- **ANTHROPIC_API_KEY** (varsa)
- **SMTP_PASSWORD** (varsa)

### 2) Rotasyon prosedürü (DB şifresi örneği)
1. Yeni şifre oluştur (uzun/rasgele).
2. DB’de kullanıcı şifresini değiştir.
3. **Staging** ortamında secret güncelle ve smoke test çalıştır.
4. **Prod** ortamında secret güncelle.
5. Uygulama pod’larını rolling restart ile yenile.
6. Hata oranı artarsa rollback:
   - Secret’i eski değerine al
   - Pod’ları yeniden başlat

### 3) “Break-glass” erişim
- Prod DB için ayrı bir **break-glass** kullanıcı (minimum yetki) + IP allowlist
- Erişim logları toplanmalı

### 4) CI/CD’de sızıntı önleme
- PR/branch’lerde secret taraması (gitleaks benzeri)
- `render.yaml`/manifest’lerde plaintext secret olmamalı

