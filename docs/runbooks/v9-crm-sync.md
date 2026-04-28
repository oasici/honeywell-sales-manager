# V9 CRM Sync (Salesforce / HubSpot) — Operations Runbook

V9 Sprint K kapsamı:
- ``services/crm_sync/`` — base protocol + Salesforce v60.0 + HubSpot v3 adapters
- ``services/crm_sync/orchestrator.py`` — sync job runner
- ``api/v1/v9_gap_closure.py`` — POST/GET ``/v9/crm/connections``,
  ``/v9/crm/connections/{id}/sync/{entity_type}``
- ``models/v9_crm_sync.py`` — ``crm_connections``, ``crm_field_mappings``,
  ``crm_sync_jobs``, ``crm_record_links`` tabloları
- ``FEATURE_V9_CRM_SYNC`` — default false

V9 CRM sync **outbound**: bizim opportunities/customers'ları
Salesforce/HubSpot'a yazıyor (ileri yön sync). Tersine çevirmek
için (inbound polling) ek geliştirme gerekir.

---

## 0) Önkoşullar

- ``FEATURE_V9_CRM_SYNC=true``
- Salesforce için: Connected App + OAuth client credentials veya
  username/password + security token
- HubSpot için: Private App access token (read+write contacts,
  companies, deals)

---

## 1) Salesforce bağlantısı kur

### 1.1 Salesforce-side setup
1. Setup → App Manager → "New Connected App"
2. OAuth Settings: Enable, callback ``https://<our-domain>/api/v1/v9/crm/oauth/callback``
3. Selected scopes: ``api``, ``refresh_token``, ``offline_access``
4. Save → Consumer Key + Consumer Secret kopyala

### 1.2 App-side connection
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "salesforce",
    "label": "Honeywell SF Production",
    "base_url": "https://login.salesforce.com",
    "credentials": {
      "client_id": "...",
      "client_secret": "...",
      "username": "integration@honeywell.com",
      "password": "...",
      "security_token": "..."
    }
  }' \
  $API/v1/v9/crm/connections
```

### 1.3 Test connection
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  $API/v1/v9/crm/connections/<conn_id>/test
# Beklenen: {"ok": true, "user_info": {...}}
```

---

## 2) HubSpot bağlantısı kur

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -d '{
    "provider": "hubspot",
    "label": "Honeywell HubSpot",
    "base_url": "https://api.hubapi.com",
    "credentials": {"private_app_token": "pat-eu1-..."}
  }' \
  $API/v1/v9/crm/connections
```

---

## 3) İlk full sync

```bash
# Customer entity'sini sync et (önce küçük entity ile başla)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  $API/v1/v9/crm/connections/<conn_id>/sync/customer

# Sonra opportunities
curl -X POST -H "Authorization: Bearer $TOKEN" \
  $API/v1/v9/crm/connections/<conn_id>/sync/opportunity
```

Job durumunu izle:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  $API/v1/v9/crm/jobs?conn_id=<conn_id> | jq '.items[]'
```

İlk sync süresi:
- 100 customer ≈ 30 sn (Salesforce rate limit: 100 req/20sn)
- 1000 customer ≈ 5-10 dk (rate limit'e takılır, exponential backoff)

---

## 4) Field mapping

Default mapping ``services/crm_sync/{salesforce,hubspot}_adapter.py``
içinde. Özelleştirmek için:

```sql
-- Custom mapping ekle
INSERT INTO crm_field_mappings (
  connection_id, entity_type, our_field, their_field, transform
) VALUES
  (1, 'customer', 'industry', 'Industry__c', 'identity'),
  (1, 'customer', 'employee_count', 'NumberOfEmployees', 'cast_int');
```

Desteklenen ``transform`` değerleri: ``identity``, ``upper``,
``lower``, ``cast_int``, ``cast_float``, ``date_iso``, ``json_dump``.

---

## 5) Hata yönetimi

### Rate limit (Salesforce 429, HubSpot 429)
Adapter built-in exponential backoff yapar. Sürekli 429 alıyorsan:
1. ``crm_sync_jobs`` tablosunda son N job'un ``error_count`` kontrol et
2. Salesforce'ta ``Setup → System Overview → API Usage`` izle
3. Bulk API'ye geçiş (>50k record sync için) — ileride sprint

### Field mapping mismatch
Adapter NULL'a düşmüş alanları log'lar. ``crm_sync_jobs.error_summary``
JSON'unda hangi field hangi record'ta fail etti görürsün.

### Token süresi dolmuş
- Salesforce refresh_token ile auto-refresh adapter'da
- HubSpot Private App token süresiz (ama rotate edilebilir) —
  yeni token ile ``credentials`` PUT et

---

## 6) Geri alma

```bash
# Bağlantıyı disable et (sync durdurur, data silmez)
curl -X PATCH -H "Authorization: Bearer $TOKEN" \
  -d '{"is_active": false}' \
  $API/v1/v9/crm/connections/<conn_id>

# Tamamen kaldır (record_links da siliniyor — local data dokunulmuyor)
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  $API/v1/v9/crm/connections/<conn_id>
```

---

## 7) Maliyet + sınırlamalar

- Salesforce API call quota: tier'a bağlı (Enterprise 1M call/24h)
- HubSpot Private App: 250k/day (free), 500k+/day (paid)
- Sync büyük veri setlerinde memory yüklü olabilir (tüm batch'i
  RAM'de tutar). 10k+ record için chunked sync (sprint backlog).
- Multi-tenant deploy'larda her tenant'ın kendi connection
  setup'ı olmalı — ``crm_connections.tenant_id`` mevcut.
