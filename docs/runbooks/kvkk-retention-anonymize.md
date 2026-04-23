## KVKK Runbook: Retention & Anonymize

Bu projede KVKK için şu bileşenler var:
- **RetentionPolicy** modeli ve CRUD endpoint’leri: `backend/app/api/v1/compliance.py`
- **Retention raporu**: `GET /api/v1/compliance/retention-report`
- **Anonymize**: `POST /api/v1/compliance/anonymize/{customer_id}` (mevcut)
- **Scheduler uyarısı**: `backend/app/tasks/scheduler.py` içindeki `check_data_retention_task` (müşteri saklama süresi dolunca yöneticilere bildirim)

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
