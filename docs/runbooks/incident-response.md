## Incident Response Runbook

### Şiddet seviyesi
- **SEV1**: login yok / veri yazılamıyor / geniş kesinti\n- **SEV2**: kritik sayfa bozuk, sınırlı kullanıcı etkisi\n- **SEV3**: minor bug, workaround var\n
### İlk 10 dakika
1. SEV belirle, kanal aç.\n2. Son deploy / migration var mı?\n3. `/api/health` ve `/metrics` kontrol.\n4. Error rate / p95 latency.\n5. DB bağlantı havuzu, disk, CPU.\n
### Hızlı aksiyonlar
- Rollback (release runbook).\n- Feature flag kapatma (ops/feature-flags görünür; flag yönetimi env üzerinden).\n- AI devre dışı: `AI_ENABLED=false`.\n
### Postmortem
- Root cause, aksiyon maddeleri, takip tarihleri.\n+
