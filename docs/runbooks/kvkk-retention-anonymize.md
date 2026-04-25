## KVKK Runbook: Retention & Anonymize

Bu projede KVKK için şu bileşenler var:
- **RetentionPolicy** modeli ve CRUD endpoint’leri: `backend/app/api/v1/compliance.py`
- **Retention raporu**: `GET /api/v1/compliance/retention-report`
- **Anonymize**: `POST /api/v1/compliance/anonymize/{customer_id}` (mevcut, manuel)
- **Scheduler uyarısı**: `backend/app/tasks/scheduler.py` içindeki `check_data_retention_task` (müşteri saklama süresi dolunca yöneticilere bildirim)
- **Otomatik anonimleştirme**: `kvkk_anonymization_task` — günlük 03:00 cron, `KVKK_AUTO_ANONYMIZE_ENABLED=true` iken `EmailRequest` (>2y) ve `Customer` (>3y kapalı fırsat, aktif fırsat yok) kayıtlarını otomatik anonimleştirir

### 0) Otomatik Anonimleştirme — Aktivasyon

Cron varsayılan olarak **kapalı**. Açmadan önce dry-run ile etki tahmin et:

```python
# backend/scripts/kvkk_dry_run.py veya admin shell
from app.core.database import async_session
from app.services.kvkk_retention_service import run_retention_anonymization

async with async_session() as db:
    summary = await run_retention_anonymization(
        db,
        email_retention_days=730,
        opportunity_retention_days=1095,
        dry_run=True,
    )
    print(summary)  # {"email_count": N, "customer_count": M}
```

Sayılar makul ise:
1. `KVKK_AUTO_ANONYMIZE_ENABLED=true` env'ini set et (Render dashboard).
2. Backend'i yeniden başlat (cron job okunur).
3. İlk gece sonrasında log'da `KVKK auto-anonymize completed: ...` satırını ara.
4. `audit_logs` tablosunda `action LIKE 'kvkk_%_auto_anonymize'` satırlarını kontrol et.

**Geri alma:** Cron'u durdurmak için `KVKK_AUTO_ANONYMIZE_ENABLED=false`. Anonimleşmiş kayıtlar geri gelmez — ancak son backup'tan restore edilebilir (PR-2.1 restore drill garantisi).

### 1) Retention politikası oluşturma
1. `GET /api/v1/compliance/retention-policies` ile mevcut politikaları listele.\n2. Gerekirse `POST /api/v1/compliance/retention-policies` ile yeni policy ekle.\n3. `entity_type` ve `action` alanlarını doğrula (`anonymize|archive|notify`).\n
### 2) Süresi dolan kayıtları tespit
1. `GET /api/v1/compliance/retention-report`\n2. Overdue listesi üzerinden müşteri bazında aksiyon kararı.\n
### 3) Anonymize prosedürü (müşteri)
1. İlgili müşteri için `POST /api/v1/compliance/anonymize/{customer_id}` çağır.\n2. Yanıtı doğrula (audit log entry).\n3. Uygulamada ilgili müşteri kayıtlarının anonim hale geldiğini doğrula.\n
### 4) Denetim izi (audit)
- Her KVKK aksiyonu için `audit_logs` kaydı oluşmalı.\n- Denetim raporu üretmek için `audit_logs` tablosu üzerinden filtreleme yapılır (aksiyon: `kvkk_*`).\n
### 5) Güvenlik notları
- Export endpoint’leri (varsa) yalnızca yetkili rollere açık olmalı.\n- Anonymize geri alınamaz; prod’da “break-glass onay” prosedürü önerilir.\n
