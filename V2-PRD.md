# Honeywell Sales Suite v2 — SalesBoard + AI (PRD)

**Versiyon:** 2.0 (taslak)  
**Kapsam:** Opportunity + Quote hybrid Sales Board + AI katmanı + entegrasyonlar  
**İlke:** Mevcut v1 akışlarını bozma, her adımı test ederek geliştirme

## Ürün vizyonu
Honeywell Sales Suite v2, mevcut **email → quote** motorunu korurken, satış sürecini **Opportunity (deal)** merkezli bir pipeline/board üzerinde görünür ve yönetilebilir hale getirir. Quote’lar opportunity altında birer “çıktı/artefact” olarak gruplanır (hybrid).

V2’nin ana farkı: yalnızca geçmiş rapor değil, **öneri + otomasyon + “next best action”** sağlayan bir satış komuta merkezi.

## Hedef kullanıcılar
- **Sales Rep**: günlük iş listesi, fırsat takibi, teklif hazırlama, follow-up.
- **Sales Manager**: pipeline sağlık, forecast, onay/koçluk, riskler.
- **Ops/RevOps**: veri kalitesi, SLA/queue, süreç ve entegrasyonlar.
- **Exec**: üst seviye KPI’lar ve risk özetleri.

## Başarı metrikleri (North-star)
- **Meeting prep time** azalması (örn. %30) — v2 özetleri/brief’ler ile
- **Cycle length** düşüşü (örn. %10–20)
- **Win-rate** artışı (örn. +3–10 puan) (doğrudan/indirekt)
- **Manual data entry** azalması (pipeline alanları, next step)
- **Forecast accuracy** artışı (manager görünümü)

## Sorun tanımı (v1 boşlukları)
- Pipeline “deal” objesi yok → teklif/eposta üzerinden dolaylı takip
- Board yok → riskli deal / rotting / next step görünürlüğü sınırlı
- AI yalnızca parsing ağırlıklı → **pipeline management + account research + summarisation** eksik
- Entegrasyonlar (calendar/CRM) yok → veriler dağınık kalıyor

## Kapsam dışı (v2.0 için)
- Tam kapsamlı billing/invoicing (quote-to-cash tamamı) — sadece entegrasyon hook’ları
- Büyük veri ambarı / tam Data Cloud muadili
- Full conversation recording (Gong muadili) — v2.2+ faz

## Bilgi mimarisi (IA) / ekranlar
- `/board`: Sales Board (Kanban + list + analytics)
- `/opportunities/:id`: Opportunity 360 (timeline + signals + next steps)
- `/quotes/:id`: mevcut quote editör (korunur)
- `/accounts/:id`: Account 360 (customer/enrichment)
- `/insights`: Signals & Coaching (manager)
- `/settings/integrations`: Entegrasyon yönetimi (ops/manager)

## Ana kullanıcı hikayeleri (epic seviyesinde)
### Epic A — Sales Board (Opportunity + Quote hybrid)
- **A1**: Rep olarak pipeline’ı kanban board’da görüp fırsatları stage’lerde yönetebilmeliyim.
- **A2**: Opportunity içinde ilgili quote’ları (taslak/approved/sent) ve email touchpoint’lerini timeline’da görebilmeliyim.
- **A3**: Manager olarak stage bazında coverage, rotting, risk ve forecast özetlerini görebilmeliyim.

### Epic B — AI Assist (Salesforce AI parity hedefli)
- **B1 Embedded summarisation**: Opportunity/Account/Quote için tek tık özet + kaynak linkleri.
- **B2 Pipeline management**: stage/next-step alanları için AI önerisi (suggestive mod).
- **B3 Deal insights**: risk flag (pricing concern, competitor, no-touch) + öneri.
- **B4 Prospecting**: high-intent account listeleri (entegrasyon + web sinyali) (faz 3.3+).

### Epic C — Entegrasyonlar (feature-flag)
- **C1 Calendar**: meeting scheduling + meeting notes → opportunity event.
- **C2 CRM sync (Salesforce/Dynamics/HubSpot)**: opportunity + account temel alanlarını çift yönlü sync (faz 3.4+).
- **C3 Telephony/meeting transcript ingestion**: call highlights (faz 3.2+).

## Fonksiyonel gereksinimler (seçilmiş)
- **FR-01 Opportunity CRUD**: stage, owner, amount, close_date, account/customer ilişki.
- **FR-02 Board query & filters**: stage, owner, date window, health score, rotting.
- **FR-03 Quote ilişkilendirme**: quote → opportunity (nullable ilişki, backward compatible).
- **FR-04 Next best action**: kural tabanlı başlar; AI önerileri opsiyonel.
- **FR-05 AI summaries**: kaynak linkli, kısa, güvenli (PII guard).
- **FR-06 Explainability**: score/prediction varsa faktör listesi (şeffaflık).

## Non-functional gereksinimler
- **Performans**: Board açılış P95 < 2sn; API aggregate P95 < 500ms hedef.
- **Güvenlik**: RBAC + audit; entegrasyon secret’ları şifreli.
- **Dayanıklılık**: entegrasyonlar best-effort; çekirdek akışlar kırılmaz.
- **Gözlemlenebilirlik**: AI çağrıları cost/latency loglanır.

## Riskler ve mitigasyon
- **Scope creep**: Fazlara böl, feature-flag ile dağıt.
- **Entegrasyon karmaşıklığı**: önce internal model; sync adaptörleri sonra.
- **AI güvenilirlik**: suggestive mod + audit + rollback.

## Faz planı (yüksek seviye)
- **Faz 3.0**: Opportunity foundation + board + quote ilişkilendirme + rotting + rule-based next steps
- **Faz 3.1**: embedded summaries + “suggested CRM updates” (UI kartları)
- **Faz 3.2**: conversation ingestion + signals + NL search
- **Faz 3.3**: predictive scoring + explainability + coaching dashboard
- **Faz 3.4**: segment/formula/territory planning + CRM sync adaptörleri

