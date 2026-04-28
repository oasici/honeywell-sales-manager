# V9 Calendar OAuth + Meeting Auto-Log — Runbook

V9 Sprint L kapsamı:
- ``services/calendar_sync_service.py`` — Google + Microsoft OAuth + auto-log
- ``models/v9_calendar.py`` — ``calendar_connections``, ``meeting_auto_links``
- ``api/v1/v9_gap_closure.py`` — ``/v9/calendar/connect``,
  ``/v9/calendar/auto-log/{booking_id}``
- ``FEATURE_V9_CALENDAR_OAUTH`` — default false

Toplantı meta-verisini (title, attendees, time) otomatik olarak
opportunity timeline'a ActivityLog olarak yazar — kullanıcı
manuel "Toplantı yapıldı" girmek zorunda değil.

---

## 0) Önkoşullar

- ``FEATURE_V9_CALENDAR_OAUTH=true``
- Google Workspace için: GCP project + OAuth consent screen + client
- Microsoft için: Azure AD App Registration + Graph permissions

---

## 1) Google Calendar bağlantısı

### 1.1 GCP setup
1. https://console.cloud.google.com → New Project
2. APIs & Services → Library → "Google Calendar API" → Enable
3. OAuth consent screen → User type "Internal" (Workspace)
4. Credentials → "OAuth client ID" → Web application
5. Authorized redirect: ``https://<your-domain>/api/v1/v9/calendar/oauth/callback``
6. Client ID + Client Secret kopyala

### 1.2 Env
```bash
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=https://<domain>/api/v1/v9/calendar/oauth/callback
```

### 1.3 Kullanıcı bağlantısı (UI üzerinden)
- Settings → Calendar → "Connect Google" butonu
- OAuth consent ekranı → kabul → callback'te token DB'ye yazılır

API üzerinden test:
```bash
curl -X GET -H "Authorization: Bearer $TOKEN" \
  $API/v1/v9/calendar/connections
# Beklenen: [{"provider": "google", "is_active": true, "expires_at": "..."}]
```

---

## 2) Microsoft Outlook (Graph API)

### 2.1 Azure AD setup
1. portal.azure.com → Azure AD → App Registrations → New
2. Redirect URI (Web): ``https://<domain>/api/v1/v9/calendar/oauth/callback``
3. API Permissions → Add → Microsoft Graph → Delegated:
   - ``Calendars.Read``, ``offline_access``, ``User.Read``
4. Grant admin consent
5. Certificates & secrets → New client secret → kopyala

### 2.2 Env
```bash
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
```

---

## 3) Meeting auto-log akışı

1. Kullanıcı bir meeting booking link'i paylaşıyor (V8 meeting links)
2. Calendar service her 15 dk'da bir bağlı kullanıcının takvimini polluyor
3. Booking'in ``start_at``'i + 30 dk geçtiğinde:
   - Calendar event'in attendee email'leri Customer.email ile eşleştiriliyor
   - Match varsa ``meeting_auto_links`` tablosuna entry düşüyor
   - ``ActivityLog`` (activity_type=``meeting``) opportunity timeline'a yazılıyor
   - Notification scheduling: "X müşterisi ile toplantı tamamlandı" event

Manuel tetikleme (debug için):
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  $API/v1/v9/calendar/auto-log/<booking_id>
```

---

## 4) Doğrulama

```sql
-- Bağlı takvim sayısı
SELECT provider, COUNT(*), MIN(expires_at), MAX(expires_at)
FROM calendar_connections
WHERE is_active = true
GROUP BY provider;

-- Son 24 saatte auto-log'lanmış toplantı
SELECT mal.id, mal.opportunity_id, mal.calendar_event_id, al.summary
FROM meeting_auto_links mal
JOIN activity_logs al ON al.id = mal.activity_log_id
WHERE mal.created_at > now() - interval '1 day'
ORDER BY mal.created_at DESC;
```

---

## 5) Token rotation

OAuth token'lar otomatik refresh oluyor. Refresh hatası alırsan:
1. ``calendar_connections.refresh_error_count`` > 3 = bağlantı re-OAuth gerekli
2. Kullanıcıya "Takvim bağlantısı yenilenmeli" notification düşüyor
3. UI'dan tekrar Connect tıklamak yeterli

Toplu rotation için:
```sql
UPDATE calendar_connections SET is_active = false
WHERE refresh_error_count > 3;
```
Sonra kullanıcılar yeniden bağlasın.

---

## 6) Geri alma

```bash
# Tek kullanıcının bağlantısını kapat
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  $API/v1/v9/calendar/connections/<id>

# Veya feature flag'i kapat
FEATURE_V9_CALENDAR_OAUTH=false
```

OAuth token'lar tabloda kalmaya devam eder ama poller no-op'a düşer.

---

## 7) Bilinen sınırlamalar

- Polling interval 15 dk → en kötü senaryoda 15 dk gecikme ile
  ActivityLog düşer. Webhook (Google Calendar Push, Microsoft
  Graph Subscriptions) ile real-time'a çevirmek için ek geliştirme
  gerekiyor.
- Attendee → Customer matching sadece email exact match. ``@gmail.com``
  gibi public domain'lerde false positive riski yok ama
  customer.email NULL ise match yapılamıyor.
- Multi-tenant deploy'da bağlı user.tenant_id sayılır;
  cross-tenant email match'i imkansız çünkü her tenant'ın kendi
  customer'ları.
