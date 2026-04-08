# Honeywell Sales Suite v2 — Teknik Plan (non-breaking)

Bu doküman, v1’i bozmadan v2 SalesBoard + AI katmanını **ekleme** olarak inşa etmek için minimum stratejiyi anlatır.

## 1) Mevcut yapı taşları (v1)
Kaynak: `TECHNICAL-DOCUMENTATION.md`

- **EmailRequest**: inbound talep, parsed_data, review_status, assigned_to
- **Quote / QuoteItem**: teklif yaşam döngüsü, PDF üretim, send
- **Customer**: müşteri master, health raporları
- **Analytics/Reports**: manager odaklı raporlar
- **Notifications**: type, entity_type, entity_id
- **Auth/RBAC**: sales_rep / sales_manager / operations
- **E2E**: Playwright smoke (live Render)

## 2) v2’ye geçiş ilkesi: “Strangler Fig”
Yeni domain (Opportunity, Account360, Board) **v1’in yanına** eklenir.

### 2.1 Non-breaking kuralları
- v1 endpoint’leri değişmez; sadece yeni endpoint’ler eklenir.
- v1 UI route’ları değişmez; v2 route’ları yeni eklenir.
- DB migration’lar additive/nullable olur.

## 3) Minimal domain genişlemesi (hybrid)
### 3.1 Yeni ana obje: Opportunity
- Opportunity, “deal/pipeline”ın birinci sınıf temsilidir.
- Quote’lar opportunity altına bağlanabilir (**nullable FK**).

### 3.2 Quote entegrasyonu (geri uyum)
- `quotes` tablosuna `opportunity_id` nullable eklenir.
- v1 akışları (quote list/detail/edit/send) opportunity olmadan da çalışır.

### 3.3 Email entegrasyonu (event/timeline)
v1’de email → quote bağlantısı `email_request_id` ile var.
v2’de opportunity timeline için 2 seçenek:
- **S1 (hızlı)**: opportunity → quote → email_request zincirinden timeline üret (no new FK).
- **S2 (daha temiz)**: `email_requests.opportunity_id` nullable ekle (faz 3.1).

## 4) Sales Board (UI) bağlama stratejisi
### 4.1 Yeni route’lar
- `/board`: kanban + list + filters
- `/opportunities/:id`: opportunity 360

### 4.2 State & caching
React Query ile:
- board column query (stage buckets)
- list query (pagination)
- opportunity detail query (timeline + signals)

## 5) AI katmanı: suggestive + auditable
### 5.1 Nerede AI kullanacağız?
- Summaries: opportunity/account/quote
- Suggestions: next step, stage update, close_date/amount “update önerisi”
- Signals: objections/pricing/competitor (conversation/email metninden)

### 5.2 Güvenlik ve kontrol
- Varsayılan mod: **suggestive** (onay gerektirir)
- Tüm AI “apply” işlemleri audit log’a yazılır.
- Feature-flag ile “auto-apply” sadece canary grupta.

## 6) Entegrasyonlar (v2.0+)
Her entegrasyon için adaptör katmanı:
- Calendar (Google/Microsoft)
- CRM (Salesforce/Dynamics/HubSpot)
- Meeting transcript (Teams/Zoom)

Hepsi feature-flag ile kapalı başlar.

## 7) Teslimat modeli
Fazlar boyunca:
- Backend: yeni modeller + endpoint’ler
- Frontend: yeni sayfalar + bileşenler
- Test: pytest + vitest + e2e
- Rollout: canary + metrik izleme

