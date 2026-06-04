# Honeywell Sales Suite — Kullanıcı Kılavuzu ve UAT El Kitabı

> **Sürüm:** Round-19+ Hardening · Phase 12 (2026-06-03) · **Dil:** Türkçe · **Hedef Kitle:** Saha satış ekibi, satış müdürleri, operasyon ekibi, UAT/QA test mühendisleri
>
> **Phase 12'de yeni / değişen:** Fırsat toplu içe aktarım (D-031 opps), Reports Builder CSV streaming (D-035), tenant-yerel forecast snapshot cron (D-034), tüm 11 mutable entity'de OCC `row_version` (D-009), login'de JWT rotation (D-007 — session-fixation savunması), email pipeline başarısızlığı → DLQ (D-028).
>
> **2026-06-01 — Yedek parça çıkarımı sıfır-tolerans sertleştirmesi:** E-postadan parça çıkarımı → katalog eşleştirme → teklif fiyatlandırma zinciri baştan sona denetlendi ve düzeltildi (bkz. `docs/audits/2026-06-01-spare-parts-extraction-audit.md`). Teklif artık asla maliyetten fiyatlanmaz; satır SKU'su gate'in değerlendirdiği parçayla aynıdır; ek adetleri başlık-duyarlı okunur; tire varyasyonları çift saymaz; gerçek bir koda 1 hane uzaklıktaki farklı parça otomatik seçilmez (incelemeye yönlendirilir). Bkz. §4.10 "Parça çıkarımı & fiyatlandırma garantileri".
>
> **2026-06-02 — E-posta özelliği sertleştirmesi:** E-posta hattı baştan sona denetlendi (bkz. `docs/audits/2026-06-02-email-feature-hardening-audit.md`). Manuel `/poll` ve zamanlanmış cron poll artık **tek ortak alım yolunu** (`email_ingestion_service`) kullanır; zamanlanmış poll'ün auth/tenant/ek verisini düşürmesi (auth-gate atlatma) giderildi. AV tarama kancası alım hattına bağlandı (infected ek nötralize edilir + incelemeye düşer). `list_emails` ve thread görünümü artık tenant ile filtrelenir (yöneticiler başka tenant'ın postasını göremez).
>
> **2026-06-02 — Yedek parça yeniden denetimleri (R1–R5, T1–T5):** Çıkarım → eşleştirme → fiyatlandırma → teklif akışı iki kez daha denetlendi (`docs/audits/2026-06-02-spare-parts-extraction-reaudit.md`, `…-reaudit-3.md`). Eklenenler: katalog çözücü yalnızca **aktif** parçaları eşler (T1); aynı kanonik koda ait satırlar tek satıra toplanır (T2 — dedup); teklif onayında satırlar **`is_confirmed` + fiyatlı** olmak zorunda, değilse 400 döner (`?force=true` ile denetlenebilir override) (T3); fiyat penceresi dışı (süresi geçmiş) fiyat girişine düşülmez (T4); tüm para işlemleri `Decimal` ile yapılır (R5); katalog satış fiyatları TRY'ye çevrilir (R2/T5). Gerçek müşteri RFQ'ları ile uçtan uca test koşuldu (`docs/audits/2026-06-02-real-rfq-e2e-findings.md`).
>
> **2026-06-03 — E-posta hızı + maliyet optimizasyonu:** (1) **"Email Kontrol" artık hızlı döner** — manuel poll yalnızca mailleri alıp kuyruğa yazar; ağır Claude ayrıştırması arka plana (`BackgroundTasks`) ertelenir. (2) **Çöp/toplu posta ön-filtresi (junk filter)** — no-reply, bülten, makbuz ve promosyon mailleri (RFC 3834 bulk başlıkları + no-reply gönderen tespiti) Claude'a hiç gönderilmeden, alımda elenir: sıfır LLM maliyeti, temiz inceleme kuyruğu. (3) **Rate-limit savunması (3 katman):** 429 `Retry-After` geri-çekilme + toplu işlem throttle + çağrı başına girdi karakteri tavanı. Bkz. §4.10.
>
> **Önceki Round-19+ değişiklikleri:** Kalıcı login lockout (D-006), gerçek SMTP gönderimi (D-014), KVKK export worker + iki-kişi onayı (D-015/D-016), arka plan iş başarısızlıkları için DLQ (D-019), 7 entity için Trash/Restore (F-007), e-İmza OTP doğrulama akışı (F-006), Lead toplu içe aktarım (D-031), onay forensik audit (D-012), kvorum onay politikası (F-018), onay SLA escalation (F-028), teklif supersede zinciri (F-026), workflow döngü algılama (D-013), düşük-veri için health skor bias düzeltme (D-033), cross-tenant ihlal tespiti (D-010), aktif oturum yönetimi.

Bu doküman, ürünü hiç kullanmamış bir kişinin baştan sona her özelliği doğru kullanabilmesi ve QA ekibinin her özelliği UAT testine tabi tutabilmesi için tek kaynak olacak şekilde hazırlanmıştır.

**Kullanım notu**
- Her özellik bölümünde **Adım adım** + **Beklenen sonuç** + **UAT test tablosu** + **Doğrulama kuralları** + **Sınır durumları** vardır.
- "**[VARSAYIM]**" etiketi: Kod tabanında kesin tanım bulamadığım ve sahada doğrulanması gereken davranış.
- Türkçe arayüz isimleri tırnak içinde (örn. "Yeni Müşteri"), İngilizce route/teknik isimler `code` formatında.

---

## İçindekiler

1. [Ürün Genel Bakışı](#1-ürün-genel-bakışı)
2. [Kullanıcı Rolleri ve Yetkiler](#2-kullanıcı-rolleri-ve-yetkiler)
3. [Arayüz Tanıtımı](#3-arayüz-tanıtımı)
4. [Özellik Rehberi (Modül Modül)](#4-özellik-rehberi-modül-modül)
   - 4.1 [Kimlik Doğrulama (Auth)](#41-kimlik-doğrulama)
   - 4.2 [Cockpit / Ana Panel](#42-cockpit--ana-panel)
   - 4.3 [Müşteriler (Customers)](#43-müşteriler)
   - 4.4 [Leadler (Potansiyel Müşteriler)](#44-leadler)
   - 4.5 [Fırsatlar (Opportunities) ve Deal Room](#45-fırsatlar-ve-deal-room)
   - 4.6 [Teklifler (Quotes)](#46-teklifler)
   - 4.7 [Sözleşmeler (Contracts) ve e-İmza](#47-sözleşmeler-ve-e-i̇mza)
   - 4.8 [Abonelikler (Subscriptions)](#48-abonelikler)
   - 4.9 [Faturalar (Invoices) ve Gelir Tahakkuku](#49-faturalar-ve-gelir-tahakkuku)
   - 4.10 [E-posta Hattı (Emails — IMAP Polling + RFQ)](#410-e-posta-hattı)
   - 4.11 [Yedek Parçalar (Parts) ve Parts Intel](#411-yedek-parçalar-ve-parts-intel)
   - 4.12 [Onay Akışları (Approvals)](#412-onay-akışları)
   - 4.13 [Pano / Kanban (Board)](#413-pano-kanban)
   - 4.14 [Planning Studio](#414-planning-studio)
   - 4.15 [Raporlar (Reports + Builder)](#415-raporlar)
   - 4.16 [Forecast (Tahmin)](#416-forecast)
   - 4.17 [Dashboards (Özel Panolar)](#417-dashboards)
   - 4.18 [Playbooks (Oyun Planları)](#418-playbooks)
   - 4.19 [Coaching (Koçluk)](#419-coaching)
   - 4.20 [Engagement (Transkriptler, Sıralar, Segmentler)](#420-engagement)
   - 4.21 [Insights / AI Tasks](#421-insights--ai-tasks)
   - 4.22 [Network Intelligence](#422-network-intelligence)
   - 4.23 [Sales Analytics](#423-sales-analytics)
   - 4.24 [Customer Health / At-Risk](#424-customer-health--at-risk)
   - 4.25 [Leaderboard](#425-leaderboard)
   - 4.26 [Campaigns (Kampanyalar)](#426-campaigns)
   - 4.27 [Compliance (Uyumluluk, Retention, Breaches)](#427-compliance)
   - 4.28 [Integrations](#428-integrations)
   - 4.29 [KVKK Export](#429-kvkk-export)
   - 4.30 [Settings (Ayarlar)](#430-settings)
   - 4.31 [Admin: Kullanıcılar, Audit, Field Permissions, vb.](#431-admin)
5. [Uçtan Uca Senaryolar (E2E UAT)](#5-uçtan-uca-senaryolar)
6. [Algoritmalar ve Hesaplama Mantığı](#6-algoritmalar-ve-hesaplama-mantığı)
7. [En İyi Uygulamalar](#7-en-iyi-uygulamalar)
8. [Sorun Giderme ve SSS](#8-sorun-giderme-ve-sss)

---

## 1. Ürün Genel Bakışı

### Ne Yapar?

Honeywell Sales Suite, Honeywell yedek parça satışı yapan ekipler için tasarlanmış **çok kiracılı (multi-tenant) bir B2B satış yönetim platformudur**. Tek bir uygulamada şu işleri birlikte yönetir:

- **Müşteri ilişkisi yönetimi (CRM)** — müşteri, lead, fırsat, stakeholder
- **Otomatik e-posta hattı** — IMAP'tan parça talebi e-postalarını çeker, ekleri (Excel/CSV/PDF/görsel) ayrıştırır, yedek parça katalogu ile eşleştirir, taslak teklif üretir
- **Teklif → sözleşme → fatura döngüsü** — quote oluştur, e-imza ile sözleşmeye dönüştür, ardından faturaya bağla
- **AI Coach + Playbook'lar** — satış görüşmesi transkriptlerinden koçluk önerileri çıkarır
- **Çok katmanlı raporlama** — özel dashboard, forecast, leaderboard, customer health
- **Yönetim arayüzleri** — onay kuralları, alan bazlı maskeleme, audit log, kullanıcı yönetimi

### Kim Kullanır?

| Rol | Tipik Kullanım |
|---|---|
| **Satış Temsilcisi (Sales Rep)** | Günlük müşteri/teklif/sipariş işlemleri, e-posta inceleme, kendi forecast'ı |
| **Satış Müdürü (Sales Manager)** | Ekip performansı, leaderboard, onay verme, coaching, forecast roll-up |
| **Operasyon (Operations)** | Parça katalogu, fiyat listesi, IMAP kimlik bilgileri, entegrasyon ayarları, audit log |

### Ana İş Değeri

1. **Manuel veri girişini ortadan kaldırır** — Müşteri e-postasıyla gelen "5 adet C7061A1012 lütfen" gibi talepler otomatik olarak teklife dönüşür.
2. **Onay süreçlerini şeffaflaştırır** — Kim hangi indirimi onayladı, ne zaman onayladı, hepsi izlenebilir.
3. **Riskleri öne çıkarır** — Customer Health skoru, churn riski olan müşterileri haftalık olarak panoda gösterir.
4. **AI ile koçluk yapar** — Görüşme transkriptlerini analiz edip "şu cümleyi şu şekilde söylemeliydin" tavsiyeleri verir.

---

## 2. Kullanıcı Rolleri ve Yetkiler

Sistemde üç temel rol vardır (`UserRole` enum'una göre): `sales_rep`, `sales_manager`, `operations`.

### 2.1 Rol Bazlı Yetki Matrisi

> **[VARSAYIM]** Birim testlerde tek tek rol-kapı çiftleri doğrulanmıştır; aşağıdaki matris kod tabanındaki `RoleGuard` + `_FIELD_PERMS_CV` (Field Permission Service) davranışından türetilmiştir. Tam liste için Admin → Field Permissions sayfasına bakın.

| Modül / İşlem | Sales Rep | Sales Manager | Operations |
|---|---|---|---|
| Cockpit görüntüleme | ✓ | ✓ | ✓ |
| Müşteri görüntüleme | Kendi müşterileri | Tüm ekip | Tümü |
| Müşteri oluşturma/düzenleme | ✓ | ✓ | ✓ |
| Müşteri silme | ✗ | ✓ | ✓ |
| Lead görüntüleme | Kendi leadleri | Tüm ekip | Tümü |
| Fırsat oluşturma | ✓ | ✓ | ✓ |
| Fırsat aşaması "closed_won"a alma | ✓ (onay gerekebilir) | ✓ | ✗ |
| Teklif oluşturma | ✓ | ✓ | ✗ |
| Teklif onaylama (yüksek indirim) | ✗ | ✓ | ✗ |
| Sözleşme oluşturma | ✓ | ✓ | ✗ |
| Sözleşme e-imza gönderme | ✗ | ✓ | ✗ |
| Fatura görüntüleme | ✓ | ✓ | ✓ |
| Fatura oluşturma | ✗ | ✓ | ✓ |
| E-posta inceleme kuyruğu (Emails) | Kendi atanmışları | Tüm ekip | Tümü |
| Onay verme/red | ✗ | ✓ | Bazı kurallarda ✓ |
| Reports (kendi raporları) | ✓ | ✓ | ✓ |
| Reports — Builder (özel rapor) | ✗ | ✓ | ✓ |
| Forecast (kendi) | ✓ | — | — |
| Forecast (ekip toplamı) | ✗ | ✓ | ✓ |
| Coaching (kendi geri bildirimleri) | ✓ | ✓ | ✗ |
| Coaching (ekibe geri bildirim verme) | ✗ | ✓ | ✗ |
| Playbooks oluşturma | ✗ | ✓ | ✓ |
| Network Intelligence | ✓ | ✓ | ✓ |
| Engagement → Transcripts | ✓ | ✓ | ✗ |
| Engagement → Sequences (otomatik mail dizisi) | ✗ | ✓ | ✓ |
| Compliance / Breaches | ✗ | ✓ | ✓ |
| KVKK Export | ✗ | ✓ | ✓ |
| Integrations (IMAP, Twilio vb.) | ✗ | ✗ | ✓ |
| Admin → Kullanıcılar | ✗ | ✗ | ✓ |
| Admin → Field Permissions | ✗ | ✗ | ✓ |
| Admin → Workflow Rules | ✗ | ✓ | ✓ |
| Admin → Custom Fields | ✗ | ✗ | ✓ |
| Admin → Territories | ✗ | ✓ | ✓ |
| Admin → Pricing | ✗ | ✗ | ✓ |
| Audit Log | ✗ | ✓ | ✓ |
| Çöp Kutusu / Restore | ✗ | ✓ | ✓ |
| DLQ (arka plan iş hataları) | ✗ | ✗ | ✓ |
| Login Lockout Yönetimi | ✗ | ✗ | ✓ |
| Aktif Oturumlar (Kendi) | ✓ | ✓ | ✓ |
| Aktif Oturumlar (Başka kullanıcı) | ✗ | ✗ | ✓ |
| Onay Forensik Audit | ✗ | ✓ | ✓ |
| Cross-Tenant Probe Raporu | ✗ | ✗ | ✓ |
| Lead Toplu İçe Aktar (CSV) | ✗ | ✓ | ✓ |

### 2.2 Çok Kiracılılık (Tenant) Sınırı

- Her kullanıcı yalnızca **kendi `tenant_id`'sine ait** verileri görür.
- Başka tenant'a ait bir kayda URL ile doğrudan gitmeye çalışırsanız sistem **404 Bulunamadı** döner (varlığı bile sızdırmaz).
- Tenant ID değiştirme yetkisi **hiçbir rolde yoktur**; bu yalnızca veritabanı yöneticisi tarafından yapılır.

**D-010 — Cross-Tenant Probe Tespiti:**
Bir kullanıcı kasıtlı/kasıtsız olarak başka tenant'ın id'sini URL'e yazarsa, sistem 404 dönmenin yanı sıra olayı `cross_tenant_attempts` tablosuna kaydeder (user_id, hedef entity, hedef id, IP, User-Agent, timestamp). Operations rolündeki kullanıcı `/admin/security/cross-tenant-attempts` üzerinden bu denemelerin raporunu görür. 1 saat içinde aynı kullanıcıdan 10+ probe gelirse otomatik security alert tetiklenir.

### 2.3 Alan Bazlı Maskeleme (Field Permissions)

Admin → Field Permissions sayfasında kurallar tanımlanır. Örnek:
- "Sales Rep, müşteri telefon numarasını `+90 5** *** **45` olarak görsün."
- "Operations, fatura tutarını maskeleme olmadan görsün."

Maskeleme **gönderme zamanında** uygulanır; veri kaynağı her zaman tam değerdir. Maskelenmiş bir alanı düzenleyemezsiniz (form alanı disable görünür).

---

## 3. Arayüz Tanıtımı

### 3.1 Ana Çerçeve

```
┌─────────────────────────────────────────────────────────────────┐
│ [Logo] Honeywell Sales Suite          [🔔] [👤 Onur Asıcı ▼]     │  ← Üst bar
├──────────┬──────────────────────────────────────────────────────┤
│          │                                                       │
│  ☰ Menü  │              Aktif Sayfanın İçeriği                  │
│          │                                                       │
│ Cockpit  │                                                       │
│ Customers│                                                       │
│ Leads    │                                                       │
│ Opps     │                                                       │
│ Quotes   │                                                       │
│ Contracts│                                                       │
│ Invoices │                                                       │
│ Emails   │                                                       │
│ Parts    │                                                       │
│ ...      │                                                       │
│          │                                                       │
└──────────┴──────────────────────────────────────────────────────┘
```

### 3.2 Üst Bar (Header) Bileşenleri

| Eleman | Açıklama |
|---|---|
| **Logo** (sol) | Tıklayınca Cockpit'e döner |
| **Arama** (üstte ortada) | Global arama: müşteri, fırsat, teklif, parça (kısayol: `/`) |
| **🔔 Bildirim** | Yeni onay, yeni e-posta talebi, sistem uyarısı |
| **👤 Profil** | Profil, ayarlar, çıkış |

### 3.3 Sol Menü (Sidebar)

Menü, **feature flag**'lere ve **role**'e göre dinamik açılır/kapanır. Örneğin `FEATURE_REV_REC` kapalıysa "Revenue Recognition" menüsü görünmez.

### 3.4 Liste Sayfaları (DataTable) — Ortak Bileşenler

| Bileşen | Konum | Davranış |
|---|---|---|
| **Arama Kutusu** | Üst sol | Anahtar kelime ile satır filtreler (case-insensitive, 300ms debounce) |
| **Filtre Çipleri** | Aramanın sağı | Tıklayınca açılır; çoklu seçim destekler |
| **"Yeni" Butonu** | Üst sağ | Yeni kayıt formu modal açar |
| **Toplu Eylem Çubuğu** | Tablonun üstünde, seçim varsa görünür | Sil, durum değiştir, dışa aktar |
| **Sayfalama** | Tablonun altı | Sayfa başına 50 kayıt varsayılan (10/50/100/200) |
| **Satır Tıklama** | Satırın herhangi bir yeri | Detay sayfasına götürür (`/customers/:id` gibi) |
| **Sütun Sıralama** | Sütun başlığı | Tıklayınca artan, tekrar tıklayınca azalan |

### 3.5 Form Alanları — Standart Davranışlar

| Alan Tipi | Doğrulama |
|---|---|
| **Zorunlu alan** | Boş gönderirseniz kırmızı kenarlık + "Bu alan zorunludur" mesajı |
| **E-posta** | RFC 5322 formatı; `EmailStr` ile sunucu tarafında ayrıca doğrulanır |
| **Telefon** | E.164 formatı tercih edilir; `+90 5XX XXX XX XX` |
| **Tutar / Para Birimi** | Sayısal, en fazla 2 ondalık; binlik ayracı arayüzde `1.234,56` (TR locale) |
| **Tarih** | ISO 8601 backend'de (`2026-05-25`); kullanıcıya `25 Mayıs 2026` gösterilir |
| **Seçim (Dropdown)** | Type-ahead arama; en fazla 100 sonuç |

### 3.6 Bildirim ve Durum Etiketleri (Badge)

| Renk | Anlam | Örnek |
|---|---|---|
| 🟢 Yeşil | Başarılı / aktif / onaylandı | "Aktif", "Onaylandı" |
| 🟡 Sarı | Bekliyor / uyarı | "Onay Bekliyor", "Eksik Bilgi" |
| 🔴 Kırmızı | Hata / red / kritik | "Reddedildi", "İptal" |
| ⚪ Gri | Pasif / arşivlenmiş | "Arşiv", "Closed Lost" |
| 🔵 Mavi | Bilgi / yeni | "Yeni", "Taslak" |

### 3.7 Modal ve Onay Diyalogları

- Modallar **ESC tuşu** ile kapatılır.
- Kritik silme/iptal işlemleri için **ConfirmDialog** çıkar; yazılı onay (`SİL` yazın) istenebilir.

---

## 4. Özellik Rehberi (Modül Modül)

### 4.1 Kimlik Doğrulama

#### Özellik: Giriş Yap (Login)

**Amaç:** Kullanıcının e-posta + şifresi ile sisteme erişim sağlaması.

**Nerede:** `https://<deploy-url>/login` (otomatik yönlendirme)

**Önkoşullar:**
- Geçerli bir kullanıcı hesabı (Operations rolündeki kişi tarafından `users` sayfasından oluşturulmuş)
- Geçici şifre veya kalıcı şifre

**Adım Adım:**
1. Tarayıcıyı açın, ürünün URL'sine gidin.
2. "E-posta" alanına e-posta adresinizi yazın.
3. "Şifre" alanına şifrenizi yazın.
4. "Giriş Yap" butonuna basın.
5. **Eğer ilk girişiniz ise** → "Şifre Değiştir" sayfasına yönlendirilirsiniz; yeni şifre belirleyin.
6. **Eğer kayıtlı kullanıcı iseniz** → Cockpit sayfası açılır.

**Beklenen Sonuç:** Cockpit görüntülenir, üst barda kendi adınız çıkar.

**UAT Test Senaryosu:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | `/login` sayfasını aç | - | Form görünür |
| 2 | Geçerli e-posta gir | `satis@firma.com` | Hata yok |
| 3 | Geçerli şifre gir | `Honeywell2026!` | Hata yok |
| 4 | "Giriş Yap" tıkla | - | Cockpit'e yönlendirme + sağ üstte kullanıcı adı |
| 5 | Yanlış şifre dene | `wrongpass` | "Geçersiz kimlik bilgileri" hata mesajı, 401 |
| 6 | 5 defa yanlış şifre dene | - | Hesap 15 dakika kilitlenir (rate-limit) |

**Doğrulama Kuralları:**
- E-posta zorunlu, geçerli format.
- Şifre zorunlu, minimum 8 karakter.
- 1 dakikada 10 deneme sonrası IP başına 429 dönülür.
- **Hesap bazlı kalıcı lockout (D-006):** 15 dakika içinde 5 başarısız deneme sonrası hesap 15 dakika kilitlenir. Lockout kaydı `login_lockouts` tablosunda kalıcıdır (server restart'tan etkilenmez).

**Sınır Durumları:**
- **Şifre süresi dolmuş:** Otomatik "Şifre Değiştir" sayfasına yönlendirir.
- **Hesap pasif:** "Hesabınız pasif. Yöneticinizle iletişime geçin."
- **Hesap kilitli:** "Bu hesap çok fazla başarısız deneme nedeniyle geçici olarak kilitlendi. Lütfen 15 dk sonra yeniden deneyin." Operations rolündeki kullanıcı `/admin/login-lockouts` üzerinden kilidi manuel açabilir.
- **Çoklu tenant kullanıcısı [VARSAYIM]:** Bir e-posta tek tenant'a bağlı; çoklu tenant desteklenmez.
- **Cookie kapalı:** Login sonrası tekrar login sayfasına döner; tarayıcı uyarısı çıkar.
- **JWT rotation:** Her başarılı login'de eski JTI revoke edilir (token-fixation koruması).

#### Özellik: Şifre Değiştir

**Nerede:** Profil menüsü > "Şifre Değiştir" veya `/auth/change-password` (zorunlu hallerde otomatik)

**Adım Adım:**
1. Sağ üstte adınıza tıklayın, "Şifre Değiştir" seçin.
2. "Mevcut Şifre" alanına şu anki şifrenizi yazın.
3. "Yeni Şifre" alanına yeni şifrenizi yazın.
4. "Yeni Şifre (Tekrar)" alanına aynısını yazın.
5. "Kaydet" tıklayın.

**Beklenen Sonuç:** "Şifreniz başarıyla değiştirildi" mesajı; yeni şifre bir sonraki girişte istenir.

**Doğrulama Kuralları:**
- Yeni şifre en az 8 karakter
- En az 1 büyük harf, 1 küçük harf, 1 rakam
- Son 5 şifreyle aynı olamaz [VARSAYIM]

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Mevcut şifre gir | `Eski123!` | OK |
| 2 | Kısa yeni şifre | `abc` | "Şifre 8 karakterden kısa olamaz" |
| 3 | İki alan farklı | `Yeni123!` / `Yeni456!` | "Şifreler eşleşmiyor" |
| 4 | Geçerli yeni şifre | `Yeni123!` / `Yeni123!` | Başarı mesajı |

#### Özellik: Çıkış Yap

**Nerede:** Profil menüsü > "Çıkış"

**Adım Adım:** Profile tıkla → "Çıkış" → Login sayfasına dönülür.

**Beklenen Sonuç:** Tüm cache temizlenir (`queryClient.clear()`), cookie silinir, JTI blocklist'e eklenir, login sayfası açılır.

#### Özellik: Aktif Oturumlarım (Active Sessions)

**Nerede:** Profil menüsü > "Aktif Oturumlar" veya `/auth/sessions`

**Amaç:** Hesabınızla şu anda açık olan tüm tarayıcı / cihaz oturumlarını görmek ve istemediğiniz oturumları sonlandırmak.

**Görünen Sütunlar:** Cihaz / Tarayıcı | IP Adresi | Lokasyon (yaklaşık) | Son Aktivite | Bu Oturum mu?

**Adım Adım:**
1. Profil ikonuna tıkla, "Aktif Oturumlar" seç.
2. Listeden tanımadığınız bir oturumu seçin.
3. "Bu Oturumu Sonlandır" tıklayın → o oturumun token'ı revoke edilir, ilgili cihazda 401 alınır.
4. "Tüm Diğer Oturumları Sonlandır" toplu eylem ile kendi oturumunuz hariç hepsi kapatılır.

**Beklenen Sonuç:** Sonlandırılan oturumlardaki kullanıcı bir sonraki istekte login'e atılır. Audit log'a `session.revoked` olayı düşer.

**Doğrulama Kuralları:**
- En az 1 aktif oturum kalmalı (mevcut oturumu kendiniz sonlandıramazsınız → onun yerine "Çıkış" kullanın).
- Operations rolü, `/admin/users/:id/sessions` üzerinden başka bir kullanıcının oturumlarını da görüntüleyebilir/sonlandırabilir (güvenlik vakası).

---

### 4.2 Cockpit / Ana Panel

#### Özellik: Cockpit Ana Sayfa

**Amaç:** Kullanıcıya gün başında "bugün neye odaklanmalıyım" sorusunun cevabını veren özet panel.

**Nerede:** Giriş sonrası varsayılan; sol menü > "Cockpit"

**Önkoşullar:** Giriş yapılmış olmalı.

**İçerik Kartları (yukarıdan aşağıya):**

| Kart | Ne Gösterir | Tıklama Davranışı |
|---|---|---|
| **"Bugünün Görevleri"** | Tarihi bugün veya geçmiş açık AI Tasks | Görev detayına götürür |
| **"Onay Bekleyenler"** | Sizin onayınızı bekleyen quote/sözleşme | Approvals sayfasına götürür |
| **"Yeni E-postalar"** | Pending review kuyruğundaki spare-part request mailleri | E-posta detayına götürür |
| **"Aylık Forecast"** | İçinde bulunduğunuz ayın toplam taahhüt edilmiş geliri | Forecast sayfasına götürür |
| **"Top 5 Fırsat"** | En yüksek tutarlı açık 5 fırsat | Fırsat detayına götürür |
| **"At-Risk Müşteri"** | Customer Health < 40 olan müşterileriniz | Customer Health sayfasına götürür |

**UAT Test:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Login sonrası bekle | - | Cockpit yüklenir, 6 kart görünür |
| 2 | "Bugünün Görevleri" tıkla | - | Görev listesi açılır |
| 3 | Hiç görevi olmayan kullanıcı için | - | "Bugün için açık görev yok" boş ekran (EmptyState) |
| 4 | "Aylık Forecast" tıkla | - | `/forecast` sayfası açılır |

**Sınır Durumları:**
- Hiç veri yoksa boş ekran (EmptyState) gösterilir.
- API hatası (500) durumunda kart "Yüklenemedi, tekrar dene" gösterir.
- Yetki yetersizliği halinde kart hiç render edilmez (yan menüde de gözükmez).

---

### 4.3 Müşteriler

#### Özellik: Müşteri Listesi

**Amaç:** Sahip olduğunuz / yetkili olduğunuz müşterileri listelemek, filtrelemek, aramak.

**Nerede:** Sol menü > "Müşteriler" → `/customers`

**Önkoşullar:** Login + en az `sales_rep` rolü.

**Adım Adım:**
1. Sol menüden "Müşteriler"e tıklayın.
2. Sayfa açılınca üstte arama kutusu, filtre çipleri, "Yeni Müşteri" butonu görürsünüz.
3. Aşağıda DataTable: Müşteri Adı | Şehir | Sektör | Health Skoru | Toplam Gelir | Sahip.
4. Filtre çipleri: "Sektör", "Şehir", "Health Skoru", "Tier", "Sahip".
5. Arama kutusuna isim/vergi no/e-posta yazın → tablo anlık filtrelenir.
6. Bir satıra tıklayın → Müşteri Detay sayfası açılır.

**Beklenen Sonuç:** Tablo 50 kayıt gösterir; alt kısımda sayfalama; sıralanabilir sütunlar.

**UAT Testi:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Müşteriler sayfasını aç | - | Liste yüklenir |
| 2 | Arama kutusuna "Demir" yaz | `Demir` | "Demirören..." müşterileri filtrelenir |
| 3 | Sektör filtresi seç | "Otomotiv" | Sadece otomotiv müşterileri kalır |
| 4 | "Health Skoru" sütununa tıkla | - | Artan sıralanır; tekrar tıkla → azalan |
| 5 | Sayfa 2'ye geç | - | URL `?page=2` olur, yeni 50 kayıt yüklenir |
| 6 | "Yeni Müşteri" tıkla | - | Modal açılır |

#### Özellik: Yeni Müşteri Oluştur

**Nerede:** `/customers` > "Yeni Müşteri" butonu

**Önkoşullar:** Sales Rep veya üstü.

**Adım Adım:**
1. "Yeni Müşteri" butonuna tıklayın.
2. Açılan formda zorunlu alanları doldurun:
   - **Müşteri Adı** (zorunlu, max 200)
   - **Vergi Numarası** (zorunlu, 10 veya 11 hane; tekil)
   - **Sektör** (dropdown, zorunlu)
   - **Şehir** (dropdown)
   - **Birincil E-posta**, **Birincil Telefon** (zorunlu, geçerli format)
   - **Tier** (Platinum/Gold/Silver/Bronze; varsayılan Bronze)
3. "Kaydet" butonuna basın.

**Beklenen Sonuç:** "Müşteri oluşturuldu" toast, modal kapanır, liste yenilenir, yeni müşteri en üstte görünür.

**UAT Testi:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Formu boş gönder | - | "Müşteri Adı zorunlu", "Vergi No zorunlu" vb. |
| 2 | Geçersiz vergi no gir | `12345` | "Vergi No 10 veya 11 hane olmalı" |
| 3 | Aynı vergi no ikinci kez | `1234567890` | "Bu vergi numarasına sahip müşteri zaten var" |
| 4 | Geçerli form doldur | bkz. yukarı | "Müşteri oluşturuldu" + listede |
| 5 | API 500 dön | (mock) | "Bir hata oluştu, tekrar deneyin" |

**Doğrulama Kuralları:**
- Müşteri adı tenant içinde unique değil; vergi no unique.
- E-posta `EmailStr` (RFC 5322).
- Telefon E.164 önerilir; serbest format kabul edilebilir [VARSAYIM].

**Sınır Durumları:**
- Aynı vergi numarasıyla **başka tenant'ta** var olabilir (tenant izolasyonu).
- Aynı tenant'ta vergi no çakışması → 409 Conflict, hata gösterilir.
- Network hatası → form değerleri korunur, retry imkanı sunulur.

#### Özellik: Müşteri Detayı

**Nerede:** Liste'de satıra tıkla veya `/customers/:id`

**Görünen Sekmeler:**
1. **Genel** — temel bilgiler, sahip, tier, health
2. **İletişim** — adres, kişiler, stakeholder'lar
3. **Fırsatlar** — bu müşterinin açık + kapalı fırsatları
4. **Teklifler** — verilen teklifler
5. **Sözleşmeler** — aktif sözleşmeler
6. **Faturalar** — faturalama geçmişi
7. **E-postalar** — bu müşteriden gelen RFQ ve cevaplar
8. **Aktivite** — tüm tarih sıralı etkinlikler (timeline)
9. **Notlar**

**UAT Test:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Müşteri kartına gir | ID=42 | Detay sayfası |
| 2 | "Fırsatlar" sekmesini tıkla | - | Açık + kapalı fırsatlar tablosu |
| 3 | Müşteri başka tenant'a aitse URL'e gir | ID=9999 | 404 sayfası |
| 4 | "Düzenle" butonu | - | Form pre-filled açılır |

#### Özellik: High-Intent Müşteriler

**Nerede:** `/customers/high-intent`

**Amaç:** AI tarafından "yakın zamanda alım yapma olasılığı yüksek" olarak işaretlenmiş müşterileri öne çıkarmak. Skor hesaplaması için bkz. [Bölüm 6.4](#64-high-intent-skoru).

---

### 4.4 Leadler

#### Özellik: Lead Listesi

**Nerede:** Sol menü > "Leadler" → `/leads`

**Amaç:** Henüz müşteri olmamış, ilgi göstermiş kişi/firmalar.

**Adım Adım:**
1. "Leadler" menüsüne tıkla.
2. Tabloyu görün: İsim | Firma | Skor | Kaynak | Atanmış Kişi | Durum.
3. "Yeni Lead" butonu → manuel ekle.
4. Bir satıra tıkla → detay.

**Lead Durumları:**
- `new` (Yeni) — henüz dokunulmamış
- `working` (Çalışılıyor) — temas kuruldu
- `qualified` (Kalifiye) — fırsata dönüştürülebilir
- `unqualified` (Kalifiye Değil)
- `converted` (Müşteriye Dönüştürüldü) — kilitli, edit yok

#### Özellik: Lead Detayı ve Müşteriye Dönüştürme

**Nerede:** Lead listesi > satır tıkla → `/leads/:id`

**Adım Adım (Convert):**
1. Lead detay sayfasında sağ üstteki "Müşteriye Dönüştür" butonuna tıkla.
2. Açılan formda: Müşteri Adı, Vergi No, Sektör otomatik doldurulur (lead'den).
3. Eksikleri tamamlayın.
4. "Dönüştür" butonuna basın.

**Beklenen Sonuç:** Yeni müşteri oluşur, lead durumu `converted` olur, bağlantı korunur. Müşteri detayında "Lead'den dönüştürüldü" bilgisi görünür.

**UAT Testi:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | "new" durumdaki lead'i aç | - | Tüm alanlar düzenlenebilir |
| 2 | "Müşteriye Dönüştür" tıkla | - | Form modalı açılır |
| 3 | Vergi no zaten varsa | mevcut no | "Bu vergi no ile bir müşteri zaten var, ona bağlamak ister misiniz?" |
| 4 | "Bağla" seç | mevcut müşteri | Lead converted, müşteri güncellenir |
| 5 | Lead düzenleme dene (converted sonrası) | - | Tüm alanlar disabled |

**Sınır Durumları:**
- Aynı lead'i 2 kişi aynı anda dönüştürmeye çalışırsa, ikincisi 409 alır.
- Vergi no boşsa "Vergi No zorunlu" hata.

#### Özellik: Lead Toplu İçe Aktarım (D-031 — CSV Bulk Import)

**Nerede:** Leads sayfasının sağ üstündeki "Toplu İçe Aktar" butonu → modal.

**Amaç:** Bir CSV dosyasından yüzlerce/binlerce lead'i tek seferde sisteme eklemek.

**Yetki:** Sales Manager + Operations.

**Zorunlu Sütunlar:** `first_name`, `last_name`, `email`.
**Opsiyonel Sütunlar:** `phone`, `company`, `source`, `notes`, `assigned_to_email`.

**Adım Adım:**
1. "Toplu İçe Aktar" tıkla.
2. Şablon CSV'yi indir (boş başlık satırı + örnek).
3. Excel'de doldur, CSV olarak kaydet (UTF-8 önerilir; Latin-9 / Windows-1254 de destekli — chardet sniff).
4. "Dosya Yükle" tıkla, dosyayı seç.
5. Sistem dosyayı önizler: kaç satır geçerli, kaç satır hatalı?
6. "Onayla ve İçe Aktar" tıkla → `POST /bulk-import/leads`.

**Per-Row SAVEPOINT Davranışı:**
Bir satırın hatası diğerlerini bozmaz. Her satır kendi SAVEPOINT'inde işlenir:
- Geçerli satır → INSERT, commit.
- Hatalı satır → ROLLBACK savepoint, hata satıra ait error listesine eklenir, bir sonraki satıra geçilir.
- Sonuçta dönen JSON: `{"imported": 487, "failed": 13, "errors": [{"row": 14, "reason": "invalid email"}, ...]}`

**UAT:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Sales rep import çağırır | - | 403 |
| 2 | Boş dosya | 0 satır | "Dosya boş veya başlık yok" |
| 3 | Zorunlu sütun yok | `email` yok | 400 + "missing required field: email" |
| 4 | 500 satırın 12'si invalid email | - | `imported=488, failed=12` + error detayları |
| 5 | 1. satır geçerli, 2. satır invalid, 3. satır geçerli | - | 1 ve 3 INSERT, 2 reddedilir; transaction abort olmaz |
| 6 | Aynı email 2 satırda | - | İlki INSERT, ikincisi `duplicate_email` |
| 7 | Tenant izolasyonu | - | Yeni leadler `current_user.tenant_id` ile yazılır |

**Sınır Durumları:**
- **Maks dosya boyutu:** 10 MB (yaklaşık 50.000 satır). Daha büyük dosyaları bölün.
- **Encoding:** chardet ile otomatik tespit edilir; başarısızsa "Encoding tespit edilemedi, UTF-8 olarak kaydedin" hatası.
- **Roll-up zorunlu değil:** "Müşteriye dönüştür" otomatik yapılmaz; tüm yeni satırlar `new` durumundaki lead olarak yaratılır.

#### Özellik: Fırsat Toplu İçe Aktarım (D-031 — Opportunity CSV Bulk Import)

**Nerede:** Fırsatlar sayfasının sağ üstündeki "Toplu İçe Aktar" → `POST /bulk-import/opportunities`.

**Amaç:** Bir CSV'den çok sayıda fırsatı (forecast pipeline) tek seferde eklemek. Lead içe aktarımıyla aynı per-row SAVEPOINT desenini kullanır.

**Yetki:** Sales Manager + Operations.

**Zorunlu Sütunlar:** `title`, `customer_vergi_no`.
**Opsiyonel Sütunlar:** `amount` (TR `1.234,56` veya US `1234.56` formatı), `currency` (varsayılan TRY), `stage`, `close_date` (ISO `2026-08-15` / `15/08/2026` / `15.08.2026`), `probability` (0-100; boşsa aşamadan türetilir), `source`.

**Davranış:**
- Her satırda `customer_vergi_no` → `customers.tax_id` ile tenant-içi eşleştirilir; müşteri bulunamazsa satır atlanır (önce müşterileri içe aktarın).
- Aşama `OpportunityStage` enum'una göre doğrulanır; boş olasılık aşamadan otomatik (prospecting=10, qualified=25, proposal=50, negotiation=75, closed_won=100, closed_lost=0).
- **Doğal anahtar (tenant, title, customer_id):** aynı forecast CSV'sini yeniden yüklemek mükerrer fırsat yaratmaz, mevcut satırı günceller.

**UAT:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Sales rep import çağırır | - | 403 |
| 2 | Zorunlu sütun eksik | `customer_vergi_no` yok | `csv_missing_required_columns` |
| 3 | Bilinmeyen müşteri vergi no | `9999999999` | satır atlanır, `customer_not_found` |
| 4 | Geçersiz aşama | `not-a-stage` | satır atlanır, `invalid_stage` |
| 5 | Olasılık > 100 | `150` | satır atlanır, `out_of_range` |
| 6 | Aynı CSV ikinci yükleme | - | `updated` (mükerrer değil) |

---

### 4.5 Fırsatlar ve Deal Room

#### Özellik: Fırsat Listesi

**Nerede:** Sol menü > "Fırsatlar" → `/opportunities`

**Görünüm:** DataTable + Kanban Toggle (sağ üstte view switcher).

**Sütunlar:** Fırsat Adı | Müşteri | Tutar | Aşama | Sahip | Yakınlık Tarihi | Olasılık (%).

**Aşamalar:** `prospecting → qualified → proposal → negotiation → closed_won / closed_lost` (OpportunityStage enum'una göre).

#### Özellik: Yeni Fırsat

**Adım Adım:**
1. "Yeni Fırsat" butonu.
2. Form alanları:
   - **Fırsat Adı** (zorunlu, max 200)
   - **Müşteri** (zorunlu, type-ahead müşteri arama)
   - **Tahmini Tutar** (zorunlu, > 0)
   - **Aşama** (varsayılan `prospecting`)
   - **Beklenen Kapanış Tarihi** (zorunlu, gelecekte olmalı)
   - **Olasılık** (yüzde, 0-100; aşamaya göre otomatik öneri)
3. "Kaydet"e bas.

**Olasılık Otomatik Önerisi (varsayılan):**
- prospecting → 10%
- qualified → 25%
- proposal → 50%
- negotiation → 75%
- closed_won → 100%
- closed_lost → 0%

**UAT Testi:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | "Yeni Fırsat" tıkla | - | Modal açılır |
| 2 | Aşama "qualified" seç | - | Olasılık otomatik 25 yazılır |
| 3 | Tutar negatif gir | -100 | "Tutar 0'dan büyük olmalı" |
| 4 | Geçmiş kapanış tarihi | 2020-01-01 | "Tarih gelecekte olmalı" |
| 5 | Geçerli kayıt | - | Fırsat oluşur + listede |

#### Özellik: Fırsat Detayı / Deal Room

**Nerede:** Liste'den tıkla → `/opportunities/:id` veya `/deal-rooms/:id`

**Görünen Sekmeler:**
1. **Özet** — temel bilgiler, sahibi, stakeholder'lar, aşama timeline
2. **Etkinlik Akışı** — e-posta, çağrı, toplantı, transkript
3. **Stakeholder'lar** — karar verici, etkileyici, blokörler
4. **Teklifler** — bu fırsata bağlı teklifler
5. **Riskler & Sinyaller** — AI tarafından tespit edilen kırmızı/sarı bayrak sinyaller (`OpportunitySignalType`)
6. **Coaching** — bu fırsatta önerilen sonraki aksiyon

**Sinyal Tipleri (`OpportunitySignalType`):**
- `pricing_concern` — fiyat hassasiyeti
- (diğer enum değerleri kodda; tam liste için Admin sayfası)

#### Özellik: Aşama Değiştirme + Onay

**Adım Adım:**
1. Fırsat detayında "Aşama" dropdown'una bas.
2. "Closed Won" seç.
3. Eğer tutar onay eşiğini aşıyorsa (örn. 100.000 TL üstü), onay modali açılır.
4. Onayı isteyeceğiniz müdürü seçin → "Onay İste" tıklayın.
5. Onay verilince fırsat closed_won olur, sözleşme akışı tetiklenir.

**UAT Testi:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Tutar < eşik fırsatı won'a al | 50.000 TL | Direkt closed_won olur |
| 2 | Tutar > eşik fırsatı won'a al | 250.000 TL | Onay modali açılır |
| 3 | Onay isteğini gönder | - | Müdürün approvals kuyruğunda görünür |
| 4 | Onay verilmeden 7 gün geçer | - | Otomatik hatırlatma maili gider [VARSAYIM] |
| 5 | Müdür reddederse | - | Fırsat aşaması geri döner, not zorunlu |

---

### 4.6 Teklifler

#### Özellik: Teklif Listesi

**Nerede:** Sol menü > "Teklifler" → `/quotes`

**Sütunlar:** Teklif No | Müşteri | Tutar | Durum | Geçerlilik | Sahip.

**Durumlar:** `draft (Taslak) → sent (Gönderildi) → accepted (Kabul) / declined (Red) → expired (Süresi Doldu)`.

#### Özellik: Yeni Teklif (Manuel)

**Nerede:** `/quotes` > "Yeni Teklif" → `/quotes/new`

**Adım Adım:**
1. "Yeni Teklif" butonu.
2. **Müşteri seç** (type-ahead).
3. **Fırsata bağla** (opsiyonel).
4. **Satır ekle**:
   - Parça Kodu (catalog'dan ara veya manuel gir)
   - Açıklama (otomatik dolar)
   - Adet
   - Birim Fiyat (price list'ten otomatik gelir)
   - İndirim (%)
5. Satır toplamı + KDV + Genel toplam otomatik hesaplanır.
6. **Geçerlilik Tarihi** seç (varsayılan: bugünden +30 gün).
7. **Notlar** ekle (opsiyonel).
8. "Taslak Kaydet" veya "Müşteriye Gönder" seç.

**Beklenen Sonuç:**
- Taslak → durum `draft`, liste'de gri.
- Gönder → durum `sent`, müşteriye PDF mail (eğer e-posta entegrasyonu açık).

**UAT Testi:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Müşteri seçmeden satır ekle | - | "Önce müşteri seçin" uyarı |
| 2 | Geçersiz parça kodu gir | `XXXX` | "Parça katalogda bulunamadı" + manuel girme seçeneği |
| 3 | İndirim %50 gir (eşik üstü) | 50 | "Bu indirim onay gerektirir" uyarısı, gönderim engelli |
| 4 | "Onay İste" tıkla | - | Yöneticiye approval gider |
| 5 | Tarih geçmişte | 2020-01-01 | "Geçerlilik tarihi bugünden sonra olmalı" |
| 6 | Teklifi gönder | - | PDF üretilir, müşteriye mail (varsa SMTP) |

**Doğrulama:**
- En az 1 satır zorunlu.
- Birim fiyat > 0, adet > 0.
- İndirim 0-100% aralığında.

#### Özellik: Teklif Detayı / Müşteriye PDF Gönderme

**Nerede:** Liste'den tıkla → `/quotes/:id`

**Aksiyonlar:**
- **PDF İndir** — anında PDF üretir.
- **Müşteriye Yeniden Gönder** — son e-postanın aynısını tekrarlar.
- **Düzenle (Versiyon 2)** — kabul edilmemiş tekliflerde, yeni versiyon açar. Eski teklif **superseded** olarak işaretlenir ve `superseded_by_id` ile yenisini gösterir (F-026).
- **Sözleşmeye Dönüştür** — accepted teklifleri sözleşmeye çevirir.

#### Özellik: Teklif Versiyon Zinciri (Supersede Chain — F-026)

**Amaç:** Bir teklifin kaç kez revize edildiğini ve hangi versiyonun "kanonik" olduğunu kayıt altına almak.

**Davranış:**
- "Yeni Versiyon" tıklandığında orijinal teklif `superseded_at = now()` ile mühürlenir; yeni teklif aynı zincire bağlanır.
- Süresi dolmuş veya superseded teklifler PDF olarak yeniden indirilebilir ama "Müşteriye Gönder" butonu disable olur — yanlışlıkla eski versiyonun gönderilmesi engellenir.
- Detay sayfasının üstünde "Bu teklifin 3 önceki versiyonu var — v1 (Mart), v2 (Nisan), v3 (Mayıs, current)" şeklinde zincir gösterilir.

#### Özellik: Fiyat Kaynağı Takibi (Price Source — F-027)

Her satır kalemi için fiyatın nereden geldiği `price_source` alanında saklanır:
- `catalog_list` — varsayılan parça liste fiyatı
- `customer_special` — müşteri özel anlaşma fiyatı
- `manual_override` — operatör elle yazdı (warning gösterir)
- `bundle_discount` — bundle kural uyguladı
- `competitor_match` — rakip teklifi eşleştirme

`price_source_ref` alanı kaynağın id'sini tutar (`price_lists.id`, `customer_special_prices.id`, ...). Margin raporları artık "Manuel override yüzdesi: %12" gibi metrik üretebilir.

---

### 4.7 Sözleşmeler ve e-İmza

#### Özellik: Sözleşme Listesi

**Nerede:** Sol menü > "Sözleşmeler" → `/contracts`

**Sütunlar:** Sözleşme No | Müşteri | Tutar | Durum | İmza Durumu | Başlangıç | Bitiş.

**Durumlar:** `draft → pending_signature → active → expired / terminated`.

#### Özellik: Sözleşmeyi e-İmzaya Gönderme (F-006 5-aşamalı OTP akışı)

E-İmza akışı **token + 6 haneli OTP** ile iki faktörlü çalışır. Müşteriye gönderilen URL tek başına imza atmak için yetmez; aynı kişinin **kendi e-postasına** gelen OTP kodunu da girmesi gerekir. Token TTL: 7 gün. OTP kilitleme: 5 yanlış denemeden sonra token kalıcı olarak yanmış sayılır.

**Operatör Tarafı — Adım Adım:**
1. Sözleşme detayında sağ üst "e-İmzaya Gönder" tıkla.
2. İmzalayacak kişiyi seç (müşteri kişileri arasından).
3. "Gönder" tıkla.
4. Sistem `/sign/<token>` linki içeren e-posta gönderir (D-014 SMTP wire — artık gerçek SMTP üzerinden, debug stub değil).
5. Sözleşme durumu `pending_signature` olur.

**Müşteri Tarafı — 5 Aşama:**

| Aşama | Endpoint | Davranış |
|---|---|---|
| 1. Açılış | `GET /sign/{token}` | Maskelenmiş alıcı e-postası + son geçerlilik tarihi + OTP durumu gösterilir |
| 2. OTP iste | `POST /sign/{token}/send-otp` | 6 haneli OTP yalnızca token'ın bağlı olduğu e-postaya gönderilir (link yönlendirmesi işe yaramaz) |
| 3. OTP doğrula | `POST /sign/{token}/verify-otp` | Yanlış kod → kalan deneme sayacı, 5'te kilit; doğru kod → 4. aşama açılır |
| 4. Sözleşmeyi gör | `GET /sign/{token}/contract` | OTP doğrulanmadan 403 (`otp_unverified`); doğrulandıktan sonra contract_id + verified bayrağı |
| 5. İmzala | `POST /sign/{token}/sign` | Imza payload + IP + User-Agent kayda alınır, token consumed, sözleşme `active` olur |

**HTTP Hata Kodları:**
- 404 `not_found` — geçersiz / sahte token
- 410 `expired` — token süresi doldu (7 gün) veya `consumed` — zaten imzalandı
- 423 `otp_locked` — 5 yanlış OTP sonrası kilit
- 429 `otp_rate` — kısa sürede çok fazla OTP isteme
- 400 `otp_wrong` / `otp_expired`
- 403 `otp_unverified` — OTP doğrulanmadan contract'a erişim

**UAT Testi:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Draft sözleşme aç | - | "e-İmzaya Gönder" görünür |
| 2 | İmzalayıcı seçmeden gönder | - | "Lütfen imzalayıcı seçin" |
| 3 | Geçerli kişiyle gönder | `ahmet@firma.com` | "İmza linki gönderildi" toast, gerçek SMTP send |
| 4 | Müşteri tarafında link aç | (geçerli token) | Aşama 1 — masked email + "OTP Gönder" butonu |
| 5 | OTP iste | - | Müşterinin posta kutusuna 6 haneli kod düşer (60 sn) |
| 6 | Yanlış OTP gir 4 kez | `000000` | "Geçersiz kod, kalan 1 deneme" |
| 7 | 5. yanlış deneme | - | 423 Locked, token kalıcı yanmış, yeni link gerekir |
| 8 | Doğru OTP gir | (gerçek) | Aşama 4 — sözleşme PDF + "İmzala" butonu |
| 9 | Forwarded URL'i 2. kişi açar | - | Aşama 2'de OTP başka kişiye gitmediği için ilerleyemez |
| 10 | Geçerli OTP + imza | - | `active` durumu, audit log'a `IP + UA` ile düşer, dashboard sayacı +1 |
| 11 | Aynı linke 2. kez "İmzala" | - | 410 `consumed` |
| 12 | 7 gün geçmiş token | - | 410 `expired` |

**Sınır Durumları:**
- **Token forwarding:** Müşteri linki üçüncü kişiye iletse bile OTP yalnızca kayıtlı e-postaya gider → 2FA garantisi.
- **Brute-force OTP:** 5-attempt sayacı per-token kalıcıdır (server restart hile yapmaz).
- **Audit:** Tüm aşama geçişleri `audit_log` + `sign_otp_tokens` tablosunda kalıcıdır. İmza sonrası IP + User-Agent + zaman damgası hukuki kanıt için saklanır.
- **TSA (Time Stamping Authority):** `tsa_token` kolonu rezerve (Phase 5 + harici TSA entegrasyonu beklemede).

---

### 4.8 Abonelikler

#### Özellik: Abonelik Listesi

**Nerede:** Sol menü > "Abonelikler" → `/subscriptions`

**Amaç:** Periyodik (aylık/yıllık) faturalandırılan hizmet abonelikleri.

**Durumlar:** `active → paused → cancelled → expired`.

**Adım Adım (Yeni):**
1. "Yeni Abonelik".
2. Müşteri seç.
3. Plan seç (Standard/Premium/Enterprise [VARSAYIM]).
4. Başlangıç tarihi, dönem (aylık/yıllık), miktar.
5. "Kaydet" — abonelik aktif olur, ilk fatura otomatik tetiklenir.

**UAT Testi:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Yeni aylık abonelik | Plan: Premium, 1.000 TL | İlk fatura oluşur |
| 2 | "Pause" tıkla | - | Durum pause; bir sonraki fatura döngüsü atlanır |
| 3 | "Cancel" tıkla | - | Onay diyalog; onay sonrası iptal |

---

### 4.9 Faturalar ve Gelir Tahakkuku

#### Özellik: Fatura Listesi

**Nerede:** Sol menü > "Faturalar" → `/invoices`

**Sütunlar:** Fatura No | Müşteri | Tutar | Durum | Vade Tarihi | Tahsil Durumu.

**Durumlar:** `draft → sent → paid → overdue → cancelled`.

#### Özellik: Yeni Fatura

**Adım Adım:**
1. "Yeni Fatura".
2. Müşteri seç, sözleşmeden veya tekliften al.
3. Kalemleri kontrol et / değiştir.
4. KDV ve toplam otomatik.
5. Vade tarihini ayarla.
6. "Müşteriye Gönder" (e-fatura entegrasyonu varsa otomatik).

**UAT Testi:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Sözleşmeden fatura | Sözleşme A | Kalemler pre-fill |
| 2 | Manuel fatura | - | Boş kalem grid'i |
| 3 | Vade tarihi geçmiş | 2020 | "Vade gelecekte olmalı" |
| 4 | "Ödendi olarak işaretle" | - | Tahsil durumu `paid`, gelir tahakkuk kaydı oluşur |

#### Özellik: Gelir Tahakkuku (Revenue Recognition)

**Nerede:** Sol menü > "Gelir Tahakkuku" → `/revenue-recognition`

**Amaç:** Çok dönemli sözleşmelerde (örn. 12 aylık abonelik) gelirin hangi ayda ne kadar tanınacağını gösterir.

**Hesaplama:** [Bölüm 6.6](#66-gelir-tahakkuku-rev-rec)'ya bakın.

---

### 4.10 E-posta Hattı

> **Bu modül Round-17 + Round-18'de derinden güçlendirildi. Coverage ~%90.**

#### Özellik: Manuel E-posta Çekme ("Email Kontrol" butonu — hızlı poll + arka plan ayrıştırma)

**Nerede:** E-postalar sayfasının sağ üstündeki **"Email Kontrol"** butonu → `POST /emails/poll`

**Amaç:** Zamanlanmış cron'u beklemeden gelen kutusunu hemen kontrol etmek.

**2026-06-03 hız iyileştirmesi — neden artık hızlı dönüyor:**
Önceden buton, her maili **alıp anında Claude ile ayrıştırdığı** için 20-30 mail × birkaç saniyelik LLM çağrısı = uzun bekleme demekti. Artık akış ikiye bölündü:
1. **Ön planda (senkron):** Mailler IMAP'tan alınır, çöp filtresinden geçirilir, `EmailRequest` satırı olarak kuyruğa yazılır → buton **birkaç saniyede** döner ve "N yeni mail alındı, ayrıştırılıyor…" mesajı gösterir.
2. **Arka planda (asenkron, `BackgroundTasks`):** Claude ayrıştırması alınan her mail için tek tek, kendi DB oturumunda, mail başına commit ile ve `EMAIL_BATCH_DELAY_SECONDS` temposuyla koşar. Parça listeleri hazır oldukça satırlar dolar.

**Beklenen Sonuç:** Buton anında yanıt verir; liste yeni maillerle hemen dolar (kategori/parça sütunları "ayrıştırılıyor" durumunda başlar, saniyeler içinde dolar). Sayfayı yenilemeye gerek yok — kuyruk periyodik güncellenir.

**UAT Testi:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | 20 yeni mail varken "Email Kontrol" tıkla | - | Buton ≤ birkaç sn döner; "20 yeni mail" mesajı |
| 2 | Hemen ardından kuyruğa bak | - | 20 satır görünür (parça sütunu "…" → dolmaya başlar) |
| 3 | Birkaç saniye bekle | - | Parça listeleri arka planda dolar |
| 4 | Hiç yeni mail yoksa | - | "Yeni mail yok" mesajı, anında döner |

**Sınır Durumları:**
- **Arka plan ayrıştırması bir mailde hata verirse** diğerlerini etkilemez (mail başına izole oturum + commit). Hatalı mail DLQ'ya düşer (D-028).
- **Aynı anda iki kez tıklama:** İkinci poll yeni mail bulamaz (idempotent `message_id`), boşuna iş yapmaz.

#### Özellik: Çöp / Toplu Posta Ön-Filtresi (Junk Filter — sıfır LLM maliyeti)

**Amaç:** Gelen kutusundaki çöpleri (Apple/banka makbuzları, CNN/Fanatik haber bültenleri, "%30 indirim" promosyonları, no-reply gönderenler) **Claude'a hiç göndermeden, alım anında** elemek. Böylece hem inceleme kuyruğu temiz kalır hem de gereksiz LLM maliyeti **sıfırlanır**.

**Nasıl çalışır (3 sinyal):** Bir mail aşağıdakilerden **herhangi birine** uyuyorsa çöp sayılır ve kaydedilmez (yalnızca log'a "skipped junk" düşer):

| Sinyal | Tespit | Yakaladığı tipik çöp |
|---|---|---|
| **Toplu posta başlıkları (RFC 3834)** | `List-Unsubscribe`, `List-Id`, `Precedence: bulk/list/junk`, `Auto-Submitted` ≠ no/none | Bültenler, haber maileri, promosyonlar |
| **No-reply gönderen** | Gönderen localpart'ında `no-reply`, `do-not-reply`, `mailer-daemon`, `mdaemon`, `postmaster` (örn. `testflight_no_reply@…` dahil) | Makbuzlar, sistem bildirimleri, otomatik yanıtlar |
| **Operatör listesi** | `EMAIL_JUNK_SENDER_PATTERNS` ile eklenen alan adı/desen alt-dizgileri (örn. `fanatik.com,cnnturk`) | Operatörün manuel kara listeye aldığı kaynaklar |

**Neden gerçek RFQ'ları etkilemez:** Bir insanın yazdığı gerçek parça talebi asla `no-reply` adresinden gelmez ve `List-Unsubscribe` gibi toplu-posta başlığı taşımaz. Tasarım bilinçli olarak **muhafazakârdır** — şüpheli bir şey eleyeceğine geçirir.

**Konfigürasyon (Operations):**
- `EMAIL_JUNK_FILTER_ENABLED` (varsayılan `true`) — filtreyi tamamen kapatmak için `false`.
- `EMAIL_JUNK_SENDER_PATTERNS` — virgülle ayrılmış ek desenler (örn. `newsletter@,bulten,no-reply@partner.com`).

**Kapsam:** Filtre ortak alım yolundadır (`email_ingestion_service.ingest_fetched_email`), bu yüzden **hem manuel "Email Kontrol" hem de saatlik cron** poll'ünde aynı şekilde uygulanır.

**UAT Testi:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | No-reply mail gelir | `no_reply@email.apple.com` | Kuyruğa **düşmez**, log: `noreply_sender`, Claude çağrısı yok |
| 2 | Bülten geldi (List-Unsubscribe başlıklı) | CNN haber maili | Kuyruğa düşmez, log: `bulk_mail` |
| 3 | Promosyon (Precedence: bulk) | "%30 indirim" | Kuyruğa düşmez, log: `bulk_mail` |
| 4 | Gerçek RFQ | `birkanege.durukan@tanap.com` "5x C7061A1012" | Normal şekilde kuyruğa düşer + ayrıştırılır |
| 5 | `EMAIL_JUNK_FILTER_ENABLED=false` | no-reply mail | Filtre devre dışı, mail kuyruğa düşer |
| 6 | Operatör `fanatik.com` ekler | `bulten@fanatik.com` | Kuyruğa düşmez, log: `junk_sender` |

**Sınır Durumları:**
- **Yanlışlıkla elenen meşru mail:** Bir müşteri bülten altyapısı üzerinden yazarsa (nadir) elenebilir; bu durumda gönderenini `EMAIL_JUNK_SENDER_PATTERNS` dışında tutmak yeterli değildir (başlık sinyali baskındır) — gerekirse filtreyi geçici kapatın. Pratikte gerçek RFQ'lar bu başlıkları taşımaz.
- **Denetlenebilirlik:** Her eleme `INFO` seviyesinde gönderen + sebep + konu(80 karakter) ile log'lanır; "neden bu mail gelmedi?" sorusu loglardan yanıtlanabilir.

#### Özellik: LLM Hız-Sınırı (Rate-Limit) Savunması — 3 katman

Claude API'sinin dakikalık token/istek limitine takılıp ayrıştırmanın kesilmesini önlemek için üç bağımsız katman vardır:

1. **429 `Retry-After` geri-çekilme:** Tek bir Claude çağrısı `429 Too Many Requests` alırsa, sunucunun bildirdiği `Retry-After` süresince beklenip yeniden denenir (4 deneme, üst sınır 60 sn). Devre kesici (circuit breaker, eşik 3 ardışık hata, 30 sn iyileşme) art arda hatalarda hattı kısa devre yapar.
2. **Toplu işlem throttle:** Bekleyen mailler `EMAIL_BATCH_SIZE` (varsayılan 50) gruplar hâlinde, gruplar arası `EMAIL_BATCH_DELAY_SECONDS` (varsayılan 2.0 sn) bekleyerek işlenir — ani patlama limitleri zorlamaz.
3. **Çağrı başına girdi tavanı:** Tek bir maile/eke ait LLM girdisi `AI_MAX_INPUT_CHARS` (24.000) ve ek başına `AI_MAX_ATTACHMENT_CHARS` (8.000) ile kırpılır. Aşırı uzun mail/ek tek başına dakikalık token bütçesini tüketemez. Kırpma olduğunda mail `attachment_pages_truncated` ile işaretlenir ve **otomatik teklif gate'i bunu geçmez** (manuel inceleme).

**Operatör konfigürasyonu:** Yukarıdaki dört değer `Settings` üzerinden ayarlanabilir; pilot (20-30 kullanıcı) için varsayılanlar uygundur.

#### Özellik: E-posta İnceleme Kuyruğu

**Nerede:** Sol menü > "E-postalar" → `/emails`

**Amaç:** IMAP üzerinden çekilen müşteri parça talebi maillerinin AI tarafından ayrıştırılmış halini görüp onaylamak.

**Önkoşullar:**
- Operations rolü tarafından IMAP kimlik bilgileri girilmiş (`/integrations`).
- Worker job çalışıyor (`poll_emails` periyodik).

**Görünen Kolonlar:** Tarih | Gönderen | Konu | Kategori (RFQ / Sipariş / Bilgi / Diğer) | Parça Sayısı | Auth (SPF/DKIM/DMARC) | Durum.

**Auth Etiketleri:**
- 🟢 `pass` — SPF + DKIM + DMARC üçü de geçti
- 🟡 `partial` — biri eksik
- 🔴 `fail` — sahtecilik şüphesi
- ⚪ `none` — kontrol edilmedi

**Durumlar:**
- `pending_review` — incelenmeyi bekliyor
- `approved` — onaylandı, taslak teklif oluşturuldu
- `rejected` — yok sayıldı

**Adım Adım (Bir maili incelemek):**
1. Listede "Onay Bekliyor" filtresi seç.
2. Yeni bir maile tıkla → detay.
3. Detay sayfasında:
   - **Sol panel:** Orijinal mail (HTML temizlenmiş + Bleach ile XSS engellenmiş).
   - **Ekler:** Excel/CSV/PDF/görsel ekleri; "Önizle" ile içeriği gör.
   - **Sağ panel:** AI'nın çıkardığı parçalar listesi.
4. Parça satırlarını gözden geçir:
   - 🟢 `exact` — katalogda tam eşleşme (otomatik fiyatlanır + onaylanabilir)
   - 🟡 `normalized` — katalogla normalize edilerek eşleşti (tire/boşluk farkı) (otomatik fiyatlanır + onaylanabilir)
   - 🟠 `fuzzy` — fuzzy eşleşme (Levenshtein/prefix); **öneri olarak gösterilir, asla otomatik onaylanmaz** — operatör doğrulamalı
   - 🔴 `unknown` — katalogda yok **veya** geçerli bir koda 1 hane uzaklıkta farklı bir gerçek parçaya denk geldi (örn. …1011 ↔ …1012); sistem bilerek tahmin etmez, manuel seçmeniz gerekir
5. Eksik/hatalı satırı düzenle. **⚠ Adet uyuşmazlığı (`quantity_conflict`)** rozeti varsa: aynı parça hem mail metninde hem ekte farklı adetle geçmiş — her iki değer de gösterilir, doğru olanı siz seçin (sistem sessizce birini atmaz).
6. **"Onayla ve Teklif Oluştur"** tıkla.
7. Sistem yeni bir teklif taslağı açar, müşteri pre-fill edilir.

**UAT Testi:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | E-postalar sayfasını aç | - | Pending kuyruğu görünür |
| 2 | Yeni RFQ maili aç | - | Parça listesi + Auth etiketi |
| 3 | Auth `fail` mail | - | Üstte kırmızı uyarı "Bu mail SPF/DKIM doğrulamasını geçemedi — manuel doğrulayın" |
| 4 | XSS denemesi içeren mail | `<script>alert()</script>` | Script çalışmaz, sanitize edilmiş HTML render |
| 5 | Image ekli mail (PNG RFQ) | - | OCR çalışır, parçalar pop up |
| 6 | Scanned PDF (text yok) | - | Vision OCR fallback, 5 sayfaya kadar |
| 7 | "Onayla" tıkla | - | Quote taslağı oluşur, kuyruktan kalkar |
| 8 | "Reddet" tıkla | - | Mail rejected, log'a düşer |

**Doğrulama — Otomatik teklif gate'i (`_auto_quote_eligible`):**
Otomatik taslak teklif oluşması için **tüm** aşağıdaki koşullar sağlanmalı; biri bile başarısızsa mail incelemeye düşer ve teklif manuel oluşturulur:
1. **Auth durumu `pass`** (SPF + DKIM + DMARC) — sahtecilik şüphesi yok.
2. **Tüm parçalar `exact` veya `normalized`** — bulanık/`unknown` eşleşme yok.
3. **Ek/sayfa kırpılmamış** (`attachment_pages_truncated=false`) — eksik veriyle teklif verilmez.
4. **İlk-kez gönderen değil** (`first_time_sender=false`) — daha önce yazışılmış güvenilir adres.
5. **Adet belirsizliği yok** (`quantity_suspect`/`quantity_conflict` yok) — şüpheli adet otomatik geçmez.
6. **Değer tavanı altında** — yüksek tutarlı talepler her zaman insana gider.
7. **AV temiz** (`parse_skipped_reason ≠ av_infected`) — infected ek varsa asla otomatik teklif yok.

Ayrıca onay anında (§ "Parça çıkarımı & fiyatlandırma garantileri" T3) tüm satırların **`is_confirmed` + fiyatlı** olması zorunludur.

**Parça çıkarımı & fiyatlandırma garantileri (2026-06-01/02 sıfır-tolerans sertleştirmesi):**
- **Asla maliyetten fiyatlanmaz.** Satış fiyatı önceliği: müşteri fiyat listesi (`PriceEntry.net_price`) → yalnızca liste yoksa maliyet × (1 + `min_margin_pct`). Marj 0 ise satır **fiyatsız** bırakılır (otomatik onaylanmaz), sıfır-marjlı maliyetle teklif **verilmez**. Tüm para hesapları `Decimal` ile yapılır (float yuvarlama hatası yok — R5); katalog satış fiyatları teklif para birimine (TRY) çevrilir (R2/T5).
- **Fiyatlar yüklenen yedek parça kataloğundan gelir, mailden değil.** Müşterinin mailde yazdığı fiyat asla teklife geçmez; fiyat daima sizin yüklediğiniz katalog/fiyat listesinden okunur.
- **Süresi geçmiş fiyat kullanılmaz (T4).** Yalnızca geçerli tarih penceresindeki `PriceEntry` seçilir; pencere dışı (eskimiş) fiyata düşülmez — satır fiyatsız kalır ve incelemeye gider.
- **Teklif satırındaki SKU = gate'in değerlendirdiği SKU.** Satır kalemi, otomatik-teklif gate'inin kullandığı katalog çözücünün verdiği parçayı kullanır; iki ayrı eşleştirme motorunun farklı parça seçmesi sorunu giderildi.
- **Yalnızca aktif parçalar eşlenir (T1).** Mailden gelen kodlar katalog çözücüde `is_active=true` parçalarla eşleştirilir; pasif/arşiv parçalar otomatik yola sızmaz.
- **Gerçek Honeywell kodlarını katalogdan tanır (F-A — katalog-duyarlı tarayıcı).** Çıkarım, mail metnindeki token'ları (ve bitişik token çiftlerini, normalize ederek) **gerçek katalog kodlarıyla** karşılaştırır; böylece `764744`, `581239`, `HDZWM2` gibi kodlar yanlış-pozitif üretmeden geri kazanılır.
- **Aynı parça tek satıra toplanır (T2 — dedup).** Mail + ek + gövdede aynı kanonik koda denk gelen kalemler tek satırda birleşir (adetler toplanır, gerekirse `quantity_suspect` + `duplicate_merged` bayrağı). Tire/boşluk varyasyonu çift saymaz.
- **Düşük skorlu eşleşme SKU/fiyat yazmaz.** Eşik (`80`) altındaki bulanık eşleşmeler yalnızca *öneri* olarak kaydedilir; satır SKU'su ve fiyatı boş kalır → zorunlu inceleme. (Örn. kodsuz "valf" tanımının %50 isim eşleşmesiyle gerçek bir SKU+fiyat alması engellendi.)
- **Ek (Excel/CSV/PDF) adetleri başlık-duyarlı okunur.** Qty / Adet / Miktar / Quantity sütunu tespit edilir; baştaki satır-numarası (`#`) sütunu adet sanılmaz. 10.000 üstü toplu siparişler artık `1`'e indirgenmez.
- **Şüpheli adet sessizce `1` olmaz.** Eksik/aralık-dışı adet `quantity_suspect` ile işaretlenir ve satır otomatik onaylanmaz.
- **Teklif onayında satır doğrulama zorunlu (T3).** Bir teklif onaylanırken (`approve_quote`) tüm satırlar **`is_confirmed` + fiyatlı** olmak zorundadır; aksi halde `400` döner. Operatör bilinçli geçmek isterse `?force=true` ile denetlenebilir (audit'e düşen) override kullanılır. Operatörün elle eklediği satırlar tanımı gereği onaylı sayılır.

**Sınır Durumları:**
- **Aynı thread'den ikinci mail:** RFQ Aggregator otomatik bağlar (`rfq_thread_key`). Detayda "Bu mail [konu] thread'ine ait, 2 mail var" bilgisi.
- **AV taraması:** Ekler alım sırasında taranır (varsayılan `_NoopScanner` → `unscanned`; `AV_SCAN_BACKEND=clamav` ile gerçek tarama). `infected` ek: içeriği LLM'e verilmez, ek nötralize edilir ve e-posta incelemeye düşer.
- **Şifrelenmiş ZIP eki:** "İçerik okunamadı" notu; manuel inceleme gerekir.
- **OCR başarısız:** "Görsel okunamadı, manuel inceleyin" + ek olarak indirilebilir.
- **Aynı parça farklı yerlerde (mail + ek):** Normalize edilmiş koda göre tek satıra birleşir (tire/boşluk varyasyonu çift saymaz). Adetler farklıysa `quantity_conflict` rozetiyle her iki değer gösterilir; sistem birini sessizce seçmez.

#### Özellik: RFQ Aggregation (Çoklu Mail Birleştirme)

**Otomatik:** İki veya daha fazla mail aynı `thread_id` (Gmail/Outlook conversation) veya (sender_domain + normalized_subject) ile gelmişse, sistem aynı `rfq_thread_key`'i atar ve birleştirir.

**Görünüm:** E-posta detayında "Bu RFQ thread'i" kutusu açılır; tüm ilgili mailler kronolojik listelenir.

**UAT:**
| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Mail 1: "5x C7061A1012" gönder | - | Pending'e düşer |
| 2 | Mail 2: "Aynısından 2 daha lütfen" (reply) | - | Aynı thread'e atanır, parça `quantity: 7` toplanır |
| 3 | Mail 3: farklı thread'den C7061 talebi | - | Yeni RFQ açılır, birleşmez |

---

### 4.11 Yedek Parçalar ve Parts Intel

#### Özellik: Parça Listesi

**Nerede:** Sol menü > "Parçalar" → `/parts`

**Sütunlar:** Parça Kodu | Açıklama | Kategori | Mevcut Stok | Liste Fiyatı | Aktif.

**Yetki:** Operations + Sales Manager düzenleyebilir; Sales Rep yalnızca görür.

**Adım Adım (Yeni Parça):**
1. "Yeni Parça" tıkla.
2. **Parça Kodu** (zorunlu, unique, max 50)
3. **Açıklama**
4. **Kategori** (dropdown)
5. **Liste Fiyatı**, **Para Birimi**
6. **Min Stok**, **Max Stok**
7. "Kaydet".

**UAT:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Aynı parça kodunu 2. defa | C7061A1012 | "Bu kod zaten kullanılıyor" |
| 2 | Para birimi seçmeden | - | "Para birimi zorunlu" |
| 3 | Geçerli kayıt | - | Parça listesinde görünür |

#### Özellik: Parts Intel

**Nerede:** `/parts-intel`

**Amaç:** AI/analitik tabanlı ürün öngörüleri (en çok talep edilenler, stok riskleri, çapraz satış önerileri).

---

### 4.12 Onay Akışları

#### Özellik: Onay Kuyruğum

**Nerede:** Sol menü > "Onaylar" → `/approvals`

**Görünen:** Tarafıma onay için gelen istekler (teklif indirim, fırsat closed_won, sözleşme şartları).

**Adım Adım:**
1. Kuyruktan bir isteği seç.
2. Detay sağda açılır: kim istedi, ne istiyor, gerekçe.
3. **Onayla** veya **Reddet** tıkla. Reddederken not zorunlu.

**UAT:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Onay isteği geldi (bildirim) | - | Sağ üstte 🔔 sayacı +1 |
| 2 | Kuyruğu aç | - | Listede beliriyor |
| 3 | Onayla | - | İstek closed, isteyene mail/bildirim |
| 4 | Reddet, not yok | - | "Red gerekçesi zorunlu" |
| 5 | Reddet, gerekçeli | "Karlılık düşük" | İstek closed, fırsat geri aşamaya döner |

#### Özellik: Onay Kuralları (Approval Rules)

**Nerede:** Sol menü > "Onaylar" > "Kurallar" → `/approvals/rules`

**Yetki:** Sales Manager + Operations.

**Adım Adım (Yeni Kural):**
1. "Yeni Kural" tıkla.
2. **Kural Adı**
3. **Tetikleyici Olay:** quote_discount > X, opportunity_amount > Y, contract_term > Z
4. **Eşik Değer**
5. **Onaylayıcı:** Rol (sales_manager) veya belirli kullanıcı
6. **Quorum Politikası (F-018):** `single` (tek onay) veya `quorum_n` (N onayın hepsi gerekli).
   - Örnek: 3 manager'lık quorum, indirim %50 üstü için → 2/3 onay verene kadar bekler.
7. **SLA (F-028):** "Onay verilmesi gereken süre (saat)". Default 24h. Süre dolarsa otomatik escalation.
   - Level 1: Manager'ın yöneticisine ek bildirim
   - Level 2: Operations'a "stuck approval" raporu
8. **Aktif** toggle'ı
9. "Kaydet".

**UAT:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Yeni kural: indirim >% 30 | - | Kural listesinde |
| 2 | Bir teklif %35 indirimle gönder | - | Otomatik onay isteği oluşur |
| 3 | Kuralı pasif et | - | %35 indirimli teklif onaysız gider |
| 4 | İki kural aynı koşulda | - | Tüm onaylayıcılar paralel istek alır |
| 5 | Quorum_n=2 kuralı, 1 manager onaylar | - | İstek hala `pending` |
| 6 | 2. manager onaylar | - | İstek `approved` |
| 7 | SLA = 24h, 25 saat bekle | - | `escalation_level=1`, üst yöneticiye bildirim |
| 8 | 48 saat bekle | - | `escalation_level=2`, Operations dashboard'a "stuck" listesi |

#### Özellik: Onay Forensik Audit (D-012)

**Nerede:** Onay detay sayfasında "Karar Geçmişi" sekmesi + `/audit?event_type=approval.*`

**Amaç:** "Kim onayladı/reddetti, ne zaman, hangi IP'den, hangi yorum ile" sorularını **inkar edilemez** kayıt altına almak.

**Saklanan Alanlar (`approval_decisions` tablosu):**
- `decider_id`, `decided_at`, `decision` (approve/reject)
- `reason` (red gerekçesi)
- `ip_address`, `user_agent`
- `delegation_chain` (varsa: A→B→C onay zinciri)

**Önemli:** Aynı kişi aynı isteğe 2. kez karar veremez — `UNIQUE(request_id, decider_id)` constraint ile DB seviyesinde de garanti edilir.

#### Özellik: Onay Delegasyonu

**Nerede:** Profil > "Onaylarımı Delege Et"

**Amaç:** Tatildeyken onaylarınızı geçici olarak başkasına yönlendirmek.

**Adım Adım:**
1. "Yeni Delegasyon" tıkla.
2. Hedef kullanıcı seç (aynı rol veya üstü).
3. Başlangıç + bitiş tarihi.
4. Öncelik (P0/P1/P2): hangi seviye onaylar delege edilsin.
5. "Aktif".
6. R19 `r19_delegation_expiry` cron'u bitiş tarihinde otomatik kapatır.

**Audit:** Delege edilmiş onaylar `delegation_chain` alanında zincir olarak gözükür ("A delege etti B'ye, B onayladı").

---

### 4.13 Pano (Kanban)

**Nerede:** Sol menü > "Pano" → `/board`

**Amaç:** Fırsatları aşama bazlı kanban gibi sürükle-bırak yönetmek.

**Adım Adım:**
1. "Pano" menüsüne tıkla.
2. Kolonlar = OpportunityStage (prospecting, qualified, proposal, negotiation).
3. Bir fırsat kartını sürükleyip başka kolona bırak.
4. Eğer hedef "closed_won" ve tutar onay gerektiriyorsa, modal açılır.

**Filtreler:** Sahip, Müşteri, Tutar aralığı.

**UAT:**
| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Pano'yu aç | - | 4 kolon |
| 2 | Kart sürükle proposal→negotiation | - | Aşama güncellenir, olasılık 75% |
| 3 | closed_won'a sürükle (eşik üstü) | - | Onay modal açılır |

---

### 4.14 Planning Studio

**Nerede:** `/planning-studio`

**Amaç:** Yıllık/çeyreklik satış hedef planlama; ekibe quota dağıtımı; territory bazlı tahsisat.

**Adım Adım:**
1. Studio'ya gir.
2. Periyot seç (Q1/Q2/2026 vb.).
3. Top-down dağıtım (Sales Manager): toplam hedefi gir → ekibe oransal dağıtır.
4. Bottom-up: temsilcilere hedeflerini kendin tıklat.
5. "Onayla ve Uygula".

> **[VARSAYIM]** Planning Studio'nun tam form alanları sahada doğrulanmalıdır.

---

### 4.15 Raporlar

#### Özellik: Raporlar Anasayfa

**Nerede:** `/reports`

**Görünen:** Standart raporlar (Aylık Satış Özeti, Müşteri Bazlı Gelir, Parça Hareketleri).

#### Özellik: Rapor Builder

**Nerede:** `/reports/builder`

**Yetki:** Sales Manager + Operations.

**Adım Adım:**
1. "Yeni Rapor"a tıkla.
2. Veri kaynağı seç (Quotes/Customers/Opportunities/Invoices).
3. Sütunları seç (drag-drop).
4. Filtre ekle (tarih aralığı, sahibi, durum).
5. Gruplama (örn. "Ayba göre", "Müşteriye göre").
6. Çıktı tipi: Tablo / Bar Chart / Line Chart / Pie.
7. "Kaydet" + "Çalıştır".
8. "Saved Reports" sekmesine düşer (`/reports/saved`).

**Beklenen Sonuç:** Tablo + grafik üretilir. CSV/Excel olarak dışa aktarılabilir.

**UAT:**
| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Data: Quotes | - | Sütunlar yüklenir |
| 2 | Filtre: son 30 gün | - | Önizleme yenilenir |
| 3 | Gruplama: Müşteri | - | Müşteri bazlı toplam |
| 4 | Kaydet, ad: "Aylık Quote" | - | Saved'de görünür |
| 5 | Export CSV | - | Dosya indirilir |

**D-035 — CSV Streaming (büyük raporlar):** CSV dışa aktarımı artık veritabanı imlecinden **akış (streaming)** ile üretilir; tüm satırları belleğe yüklemez. 50.000 satırlık bir rapor bile sabit bellekle indirilir. Gruplanmış (aggregate) raporlar küçük olduğundan tamponlu yola düşer. Her hücre F-008 formül-enjeksiyonu sanitizasyonundan geçer (örn. `=cmd|...` ile başlayan müşteri adı pasif metne çevrilir). Güvenlik tavanı: tek dışa aktarımda max 200.000 satır (aşılırsa log'a "truncated" yazılır).

---

### 4.16 Forecast

**Nerede:** `/forecast`

**Amaç:** Açık fırsatlardan beklenen geliri ay/çeyrek bazında tahmin etmek.

**Hesaplama:** Bkz. [Bölüm 6.2](#62-forecast-hesaplaması).

**Görünüm:** Sol = aylar, Sağ = beklenen / commit / closed won / quota; renkli bar chart.

**Adım Adım:**
1. Forecast'ı aç.
2. Üstten dönem seç (Q1/2026 vb.).
3. Tabloya bak: "Bu ay X TL commit, Y TL pipeline, Z TL kapanmış."
4. Bir hücreye tıkla → o aydaki fırsatlar listesi açılır.

---

### 4.17 Dashboards

**Nerede:** `/dashboards`

**Amaç:** Kullanıcı kendi widget'larıyla özelleştirilebilir pano oluşturabilir.

**Adım Adım:**
1. "Yeni Dashboard" tıkla.
2. Ad ver.
3. Widget ekle: KPI (sayı), Grafik, Tablo, Liste.
4. Düzenle modunda (`/dashboards/:id/edit`) widget'ları sürükleyip boyutlandır.
5. "Kaydet".

**UAT:**
| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Yeni dashboard | - | Boş canvas |
| 2 | KPI ekle: "Bu ay açık fırsatlar" | - | Sayı widget yerleşir |
| 3 | Grafik ekle: aylık quote count | - | Bar chart |
| 4 | Paylaş (ekibimle) | - | Diğer kullanıcılar görür |

---

### 4.18 Playbooks

**Nerede:** `/playbooks`

**Amaç:** Belirli bir senaryoda izlenecek adımları (örn. "Soğuk lead'i nasıl ısıtırım") rep'lere şablon olarak sunmak.

**Sekmeler:** Listem | Şablonlar (`/playbooks/templates`) | Analytics (`/playbooks/analytics`).

**Adım Adım (Yeni):**
1. "Yeni Playbook".
2. İsim, açıklama, kategori.
3. Adımları ekle (sıralı kart liste): "Müşteri site ziyareti yap" → "Demo planla" → ...
4. Her adıma "trigger" (örn. "ilk 24 saatte tamamla") ekle.
5. "Yayınla" → ekibe açılır.

---

### 4.19 Coaching

**Nerede:** `/coaching`

**Amaç:** Görüşme transkriptlerinden AI çıkarımlı koçluk önerileri (`coaching_hooks`).

**Sales Rep görünümü:** Kendisine gelen önerileri ve yöneticinin notlarını görür.

**Sales Manager görünümü:** `/coaching/rep/:id` ile ekibindeki rep'in performansını ve önerileri görür.

**Coaching Hook Çeşitleri (örnek):**
- "Bu görüşmede fiyat itirazı kötü ele alındı; şu cümleyi deneyin: '...'"
- "Müşteri bütçeden bahsetti, BANT formuna geç"
- "Decision-maker yokmuş; bir sonraki toplantıya CFO'yu çağırın"

**UAT:**
| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Sales rep coaching aç | - | Açık 3-5 öneri kartı |
| 2 | Öneriyi "Uyguladım" işaretle | - | Kart arşivlenir |
| 3 | Manager olarak rep aç | rep id=42 | Rep performansı + önerileri |
| 4 | Manager not ekle | "Demo tekrar planla" | Rep coaching panelinde görünür |

---

### 4.20 Engagement

#### Özellik: Transcripts (Görüşme Transkriptleri)

**Nerede:** `/engagement/transcripts`

**Amaç:** Yüklenen ses/video transkriptlerini analiz etmek, anahtar kelime çıkarmak, sentiment göstermek.

**Adım Adım:**
1. Sayfayı aç.
2. "Yeni Transkript Yükle" → audio/video drop.
3. AI işler (1-5 dakika), durum `processing → ready` olur.
4. Hazır olunca tıkla: tam metin + zaman damgalı oynatıcı + sentiment + anahtar kelimeler.
5. "Coaching'e gönder" → AI öneri üretir.

#### Özellik: Keywords

**Nerede:** `/engagement/keywords`

Belirli kelimeler için arama: "rakip", "bütçe", "iptal" gibi anahtar kelimeleri transkriptlerde bulup öne çıkarır.

#### Özellik: Sequences (Otomatik Mail Dizileri)

**Nerede:** `/engagement/sequences`

**Amaç:** Lead nurturing için zaman ayarlı mail otomasyonu.

**Adım Adım (Yeni):**
1. `/engagement/sequences/builder` aç.
2. Sequence adı.
3. Adımları ekle: Day 0 → mail A, Day 3 → mail B (yanıtsızsa), Day 7 → mail C.
4. Her adıma şablon seç.
5. Hedef segment seç.
6. "Aktif" toggle.

**UAT:**
| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | 3 adımlı sequence kur | - | Builder'da görünür |
| 2 | Test mail gönder | bana@firma.com | Mail kutuma düşer |
| 3 | Aktif et + segmenti at | - | Worker job sequence'i koşturur |
| 4 | Bir alıcı yanıt verirse | - | Sequence o alıcı için durur |

#### Özellik: Segments

**Nerede:** `/engagement/segments`

**Amaç:** Dinamik müşteri/lead grupları (örn. "Son 30 günde teklif görmüş, satın almamış").

#### Özellik: Scorecards

**Nerede:** `/engagement/scorecards`

**Amaç:** Bir rep'in görüşme kalitesi puanlama formu (Acentede X kullanılır mı? Müşteri ihtiyacı netleşti mi?).

---

### 4.21 Insights / AI Tasks

#### Özellik: AI Tasks

**Nerede:** `/ai/tasks`

**Amaç:** AI tarafından otomatik üretilmiş eylem önerileri ("Müşteri X'e 7 gündür dönüş yapılmamış, ara").

**Durumlar:** `open → in_progress → completed → dismissed`.

**Adım Adım:**
1. Listede açık görevleri gör.
2. Bir göreve tıkla → bağlam (hangi müşteri/fırsat) + öneri metni.
3. "Başla" tıkla → in_progress.
4. Aksiyon sonrası "Tamamla" veya "Reddet".

#### Özellik: AI Insights

**Nerede:** `/ai/insights` veya `/insights`

**Amaç:** Aggregat veri tabanlı sezgi panelleri ("Bu çeyrekte parça X tüm sektörde +%20 talep gördü").

---

### 4.22 Network Intelligence

**Nerede:** `/network-intelligence`

**Amaç:** Müşteri ağındaki gizli bağlantıları, ortak yatırımcıları, ortak müşteri-tedarikçi ilişkilerini grafiğe döker.

> **[VARSAYIM]** İçerik kod tabanında stub aşamasında olabilir; doğrulayın.

---

### 4.23 Sales Analytics

**Nerede:** `/sales-analytics`

**Amaç:** Win rate, sales cycle length, deal size dağılımı, kazanma/kaybetme sebepleri.

**Bölümler:**
- Win/Loss Analysis
- Cycle Time
- Conversion Funnel (lead → opp → quote → won)
- Deal Velocity

**UAT:**
| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Sales Analytics aç | - | 4 ana grafik yüklenir |
| 2 | Tarih aralığı: 2026 | - | Yıl bazında metrikler |
| 3 | Filtre: Sahip = ben | - | Sadece kendi performansım |

---

### 4.24 Customer Health / At-Risk

#### Özellik: Customer Health Skoru

**Nerede:** Müşteri detay sayfasında üst kart + `/at-risk`

**Skor Aralığı:** 0-100.

**Bantlar:**
- 🟢 70-100 = Sağlıklı
- 🟡 40-69 = İzlemede
- 🔴 0-39 = Riskli (at-risk)

**Hesaplama:** [Bölüm 6.3](#63-customer-health-skoru)'ya bakın.

#### Özellik: At-Risk Listesi

**Nerede:** `/at-risk`

Tüm müşterileri health skoruna göre düşük→yüksek sıralar; her satırda "neden riskli" gerekçesi.

---

### 4.25 Leaderboard

**Nerede:** `/leaderboard`

**Amaç:** Ekip içi rekabet için satış performans sıralaması.

**Gösterilen Metrikler:** Toplam Kapanan Gelir, Açılan Yeni Fırsat, Won Rate, Ortalama Deal Size.

**Periyotlar:** Bu Hafta / Bu Ay / Bu Çeyrek / Yıl.

---

### 4.26 Campaigns

**Nerede:** `/campaigns`

**Amaç:** Pazarlama kampanyalarını kaydetmek, ROI hesaplamak (kampanyaya atfedilen müşteri/gelir).

**Adım Adım (Yeni):**
1. "Yeni Kampanya" tıkla.
2. Ad, başlangıç-bitiş, bütçe, kanal (e-mail/etkinlik/digital ads).
3. Hedef segment.
4. "Aktif" tetikle.

Detayda (`/campaigns/:id`): bağlı leadler, dönüşüm sayıları, ROI.

---

### 4.27 Compliance

#### Özellik: Compliance Anasayfası

**Nerede:** `/compliance`

**Amaç:** KVKK/GDPR uyum işlemlerini yönetmek.

#### Özellik: Retention Policy

**Nerede:** `/compliance/retention`

**Amaç:** Veri saklama sürelerini tanımlamak (örn. "Kapalı leadler 24 ay sonra otomatik silinir").

#### Özellik: Breaches

**Nerede:** `/compliance/breaches`

**Amaç:** Veri sızıntısı / ihlal kayıtlarını yönetim altına almak.

**Adım Adım (Yeni):**
1. "Yeni İhlal" tıkla.
2. Tarih, etkilenen kayıt sayısı, ihlal tipi, gerekçe.
3. Aksiyon planı, sorumlu kişi, deadline.
4. "Kaydet".

KVKK kapsamında 72 saat içinde Kurul'a bildirim takibi yapar.

---

### 4.28 Integrations

**Nerede:** Sol menü > "Entegrasyonlar" → `/integrations`

**Yetki:** Operations.

**Tipler:**
- **E-posta (IMAP):** Host, Port, Kullanıcı, Şifre (Fernet ile şifrelenir).
- **E-posta (SMTP):** Giden mail server.
- **e-Fatura:** GİB entegrasyonu.
- **Twilio / WhatsApp:** SMS/WA mesajları için.
- **Anthropic Claude:** API key (Claude AI servisleri için).

**Adım Adım (IMAP):**
1. "E-posta (IMAP)" kartını aç.
2. Host: `imap.firma.com`, Port: `993`, SSL: ON.
3. Kullanıcı + Şifre.
4. "Test Et" → "Bağlantı başarılı" mesajını bekle.
5. "Kaydet" → şifre Fernet ile şifrelenip DB'ye yazılır.

**UAT:**
| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Yanlış şifre | - | "IMAP login başarısız" |
| 2 | Yanlış host | `xx.invalid` | "Sunucuya bağlanılamadı" |
| 3 | Geçerli | - | "Bağlantı başarılı", kaydedildi |
| 4 | Test mail at | - | 60 saniye içinde `/emails` kuyruğuna düşer |

**Güvenlik:** Şifre değiştirme (rotation): Operations Settings sayfasında "Encryption Key Rotation" işlemi `rotate_encryption_key.py` ile arka planda yapılır.

---

### 4.29 KVKK Export (F-023 + D-015/D-016)

**Nerede:** `/kvkk-export`

**Amaç:** KVKK'nın "veri sahibi talep hakkı" kapsamında, bir kişinin tüm verilerini ZIP arşivi olarak çıkarmak. **İki kişi kuralı** (two-person rule) zorunludur — tek operatör tek başına export çalıştıramaz.

**Yetki:** Operations + Sales Manager (sales_rep reddedilir).

**State Machine:**

```
draft → pending_approval → approved → executing → done
                       ↘ rejected
```

**Adım Adım — Operator A (Talep Eden):**
1. "Yeni Export Talebi" tıkla.
2. **Subject lookup:** kişinin e-postası, vergi no veya müşteri id'si.
3. **Subject kind:** `customer`, `lead`, `contact`, `user`.
4. "Talep Oluştur" → durum `pending_approval`. Listede tüm Operations+Manager kullanıcılara bildirim düşer.

**Adım Adım — Operator B (Onaylayan):**
1. Bekleyen talepler listesine git (`/kvkk-export/requests?status=pending_approval`).
2. Talebi aç, kim talep etti / hangi kişi için olduğunu kontrol et.
3. **"Onayla"** veya **"Reddet"** (reddet için min 10 karakter gerekçe).
4. Onay sonrası durum `approved`.

**Önemli — İki Kişi Kuralı (Two-Person Rule):**
- Talep eden kişi kendi talebini onaylayamaz (`TwoPersonViolation` → 403).
- Kural 3 katmanda enforce edilir:
  1. API handler katmanı (`approver_id != requested_by`)
  2. Service katmanı (`kvkk_two_person.approve_request`)
  3. DB CHECK constraint (`kvkk_export_requests.approved_by != requested_by`)
- Gelecekte birinin bypass etmeye çalışması durumunda DB constraint son savunma hattıdır.

**Adım Adım — Execute:**
1. `approved` talebin sağ üstündeki "Çalıştır" butonu.
2. Durum `executing` olur, transaction commit edilir.
3. Arka planda `kvkk_export_worker.run_export` koşar:
   - Customer + opportunities + quotes + invoices + contracts + email_requests + audit_log tablolarından subject verisi çekilir
   - **Coaching notları HARIÇ tutulur** (TC-KVKK-005 — koçluk gözlemleri kişisel veri tabanında talep edilemez).
   - ZIP arşivi oluşturulur ve `KVKK_ARTIFACT_DIR` altına yazılır (env var, default `/var/lib/kvkk-exports`).
   - `artifact_url` alanına path/URL yazılır.
   - Durum `done` olur.
4. **D-015 Konu Bildirimi:** Subject'e (eğer e-postası varsa) "KVKK talebiniz tamamlandı, ekteki dosya verinizdir" maili gerçek SMTP ile gönderilir.

**Hata Halinde:**
- Worker exception fırlatırsa durum `failed` olur, hata mesajı detayda görünür.
- Aynı zamanda **DLQ'ya yazılır** (D-019) — Operations DLQ panelinden re-run trigger edebilir.

**UAT Senaryoları:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Sales rep KVKK talebi açmaya çalışır | - | 403 `kvkk_export_requires_ops_or_manager` |
| 2 | Manager A talep oluşturur | subject=`ali@firma.com`, kind=customer | `pending_approval` |
| 3 | Manager A kendi talebini onaylar | - | 403 `TwoPersonViolation` |
| 4 | Manager B onaylar | - | `approved` |
| 5 | Manager B "Çalıştır" | - | `executing` → `done`, ZIP üretilir |
| 6 | Subject kullanıcıya bildirim | - | "KVKK talebiniz tamamlandı" e-postası |
| 7 | ZIP içeriği denetle | - | customer/opps/quotes/.../*; coaching_notes/ klasörü YOK |
| 8 | Foreign-tenant subject id'si | - | 404 (varlığı sızdırmaz) |
| 9 | Worker DB connection patlatır | - | `failed`, DLQ'ya kaydedilir |

**Audit Trail:**
- `kvkk_export_requests` tablosu kalıcı: kim talep etti, kim onayladı/reddetti, ne zaman çalıştı, artifact nerede.
- `audit_log`'a `kvkk.request_created / kvkk.approved / kvkk.rejected / kvkk.executed / kvkk.delivered` olayları düşer.

---

### 4.30 Settings

**Nerede:** `/settings`

**Sekmeler:**
- **Profil** — ad, e-posta, telefon
- **Bildirim Tercihleri** — hangi kanaldan, hangi olaylarda bildirim
- **Şifre Değiştir** — bkz. 4.1
- **Pipelines** (`/settings/pipelines`) — fırsat aşamalarını özelleştir

---

### 4.31 Admin

> Aşağıdaki sayfalar yalnızca Operations rolünde (veya bazıları Sales Manager) görünür.

#### Özellik: Kullanıcı Yönetimi

**Nerede:** `/users`

**Adım Adım (Yeni Kullanıcı):**
1. "Yeni Kullanıcı" tıkla.
2. Ad, Soyad, E-posta (zorunlu, unique).
3. Rol seç.
4. Bölge (Territory) ata.
5. Geçici şifre üret veya manuel gir.
6. "Davet Gönder" → kullanıcıya welcome mail.

**UAT:**
| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Yeni rep ekle | `ayse@firma.com` | Listede |
| 2 | Aynı e-posta tekrar | - | "Bu e-posta zaten var" |
| 3 | Pasif et | - | Kullanıcı login olamaz |
| 4 | Rol değiştir | sales_rep → manager | Anında etkili |

#### Özellik: Audit Log

**Nerede:** `/audit` veya `/admin/event-audit`

**Amaç:** Sistemdeki tüm önemli olayları (kim ne zaman ne yaptı) izlemek.

**Filtreler:** Aktör (kullanıcı), Olay Tipi, Tarih, Hedef Kayıt.

**Örnek Olaylar:** `user.login`, `customer.create`, `quote.send`, `approval.grant`, `field_permission.update`.

#### Özellik: System Health (Admin)

**Nerede:** `/admin/system-health`

API yanıt süreleri, IMAP poll worker durumu, Claude API rate-limit kullanımı, DB connection pool, son hatalar.

#### Özellik: AI Attributes

**Nerede:** `/admin/ai-attributes`

AI modülünün veri özelliklerini ve kullandığı özniteliklerini görüntüleme/ayarlama.

#### Özellik: Data Quality

**Nerede:** `/admin/data-quality`

Eksik alan oranları, duplicate kayıtlar, format uyumsuzlukları raporu.

#### Özellik: Custom Fields

**Nerede:** `/admin/custom-fields`

Her entity (customer, lead, opp) için ek özel alan tanımlama.

**Adım Adım:**
1. Entity seç (Customer).
2. "Yeni Özel Alan".
3. Ad, Tip (text/number/date/dropdown), Zorunlu?, Default.
4. Kaydet → tüm yeni formlarda görünür.

#### Özellik: Field Permissions

**Nerede:** `/admin/field-permissions`

Hangi alanı hangi rolün görüp düzenleyebileceğini ayarlar (CLAUDE.md "Field-level permission masking" bölümü).

#### Özellik: Product Rules

**Nerede:** `/admin/product-rules`

Hangi parçanın hangi parça ile birlikte satılması gerektiği (bundle rules), zıt parça uyarıları.

#### Özellik: Workflow Rules

**Nerede:** `/admin/workflow-rules` (+ flow editor `/admin/workflow-rules/flow/new`)

If-then-else otomasyon kuralları:
- "Müşteri tier'i Platinum olduğunda → Manager bildirim al"
- "Lead 30 gündür çalışılmıyorsa → Auto-archive"

**D-013 — Workflow Döngü ve Derinlik Algılama:**
Bir kuralın action'ı başka bir kuralı tetikleyebilir ("opportunity.stage=closed_won" → contract oluştur → "contract.created" event → notification gönder). Sonsuz döngüye düşmeyi engellemek için sistem her event chain'i `RuleExecutionContext` ile sarmalar:
- **Cycle:** A → B → A şeklinde geri dönüş tespit edilirse `WorkflowCycleDetected` raised, blok atılır.
- **Depth:** Max chain derinliği 10 (`WorkflowDepthExceeded`).
- Bloklanan akış `workflow_execution_log`'a kayıt edilir ve admin için "Bloklanan Akışlar" raporunda görünür.

**UAT:**
| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Yeni workflow başlat | - | Flow canvas açılır |
| 2 | Trigger: "lead_inactive_30d" | - | Node yerleşir |
| 3 | Action: "set_status='archived'" | - | İkinci node + ok |
| 4 | Aktif et + 30 gün simüle | - | Job çalışır, lead'ler arşivlenir |
| 5 | A → B → A döngüsel kural tanımla | - | İlk tetikleme cycle algılar, blok'a düşer |
| 6 | 11 derinlikli zincir | - | 10. seviyede `WorkflowDepthExceeded`, log'a düşer |

#### Özellik: Merge (Birleştirme)

**Nerede:** `/admin/merge/:entityType/:winnerId/:loserId`

Aynı müşteriyi/lead'i iki kayıt olarak görmek istendiğinde manuel birleştirme.

#### Özellik: Territories (Bölgeler)

**Nerede:** `/admin/territories`

Coğrafi/sektörel müşteri dağıtım kuralları. Yeni gelen lead'in hangi rep'e atanacağını belirler.

#### Özellik: Pricing (Fiyat Yönetimi)

**Nerede:** `/admin/pricing`

Parça fiyat listesi, müşteri özel fiyatları, currency override.

#### Özellik: Admin Chat

**Nerede:** `/admin/chat`

Admin'in tüm sistem genelinde chat/destek mesajları yönetimi (varsa).

#### Özellik: Çöp Kutusu / Trash (F-007 — Soft-Delete + Restore)

**Nerede:** `/admin/trash` (sol menü > "Çöp Kutusu")

**Amaç:** Yanlışlıkla silinen kayıtları geri yüklemek. Sistemdeki tüm önemli entity'ler artık **soft-delete** ile çalışır — fiziksel silme yerine `deleted_at` zaman damgası işaretlenir.

**Desteklenen Entity'ler (7):** `customers`, `leads`, `opportunities`, `quotes`, `contracts`, `invoices`, `email_requests`.

**Yetki:** Operations + Sales Manager (sales_rep göremez).

**Adım Adım:**
1. "Çöp Kutusu" menüsüne tıkla.
2. Üstte entity dropdown'u seç (örn. "Müşteriler").
3. `GET /trash/customers?limit=100` çağrılır → soft-deleted satırlar listelenir.
4. Sütunlar: ID | Silinme Tarihi | Silen Kullanıcı | Silme Sebebi.
5. Bir satırda **"Geri Yükle"** tıkla → `POST /trash/customers/:id/restore`.
6. `deleted_at = NULL` yapılır, kayıt aktif duruma döner, audit log düşer.

**UAT:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Sales rep `/admin/trash`'ı açar | - | 403 `trash_requires_ops_or_manager` |
| 2 | Manager, customers tab'ı açar | - | Soft-deleted müşteriler listelenir |
| 3 | Bilinmeyen entity tipi yaz | `widgets` | 400 `unknown_entity` (allowed list döner) |
| 4 | "Geri Yükle" tıkla | id=42 | "1 müşteri geri yüklendi" toast |
| 5 | Aynı id'yi 2. kez restore et | - | 404 `customers_not_found_or_not_deleted` |
| 6 | Foreign-tenant id'si restore et | - | 404 (tenant izolasyonu, 403 değil) |

**Sınır Durumları:**
- Tenant scoping: yabancı tenant'ın silinmiş kaydı görünmez ve restore edilemez (404).
- Silme nedeni (`delete_reason`) DELETE çağrısında kaydedildiyse görünür; aksi halde "—".
- Saklama süresi: KVKK retention politikasında tanımlanan süre dolduğunda **fiziksel** silinir (hard delete cron); restore artık mümkün değildir.

#### Özellik: DLQ — Arka Plan İş Başarısızlık Kuyruğu (D-019)

**Nerede:** `/admin/dlq` (sol menü > "DLQ")

**Amaç:** Cron, worker veya scheduler işlerinden hata fırlatıp **çözülmemiş** olan başarısızlıkları operatöre göstermek; tekrar denetip resolve etmek.

**Yetki:** Operations rolündeki kullanıcılar (DLQ entry payload'ları hassas içerik barındırabilir: KVKK export request id, sign-OTP token hash, vb.).

**Görünen Sütunlar:** ID | Job Adı | Hata | Başarısızlık Zamanı | Retry Sayısı | Payload (JSON).

**Adım Adım (Çözme):**
1. Listede unresolved entry'leri gör.
2. Satıra tıkla → payload + stack-trace görünür.
3. Operatör asıl sebebi düzeltir (örn. SMTP credential, disk space).
4. "Retry" tıkla → `POST /admin/dlq/:id/retry`, retry sayacı +1 (asıl re-execution operatör'ün asıl endpoint'i tekrar tetiklemesiyle yapılır).
5. Sorun çözüldüyse "Resolve" tıkla → `POST /admin/dlq/:id/resolve` (opsiyonel `note`).
6. Resolved entries kuyruktan kalkar ama tabloda audit amacıyla saklanır.

**Yaygın Job'lar ve DLQ'ya Düşme Sebepleri:**

| Job | Yaygın Hata | Çözüm |
|---|---|---|
| `kvkk_export_worker` | DB disconnect / disk dolu | Connection pool / disk temizliği, sonra retry |
| `sequence_email_sender` | SMTP credential expired | Integrations → SMTP yenile → retry |
| `imap_poll_emails` | IMAP login fail | Integrations → IMAP test → retry |
| `revenue_recognition_cron` | Decimal divide-by-zero | Sözleşmede term=0; düzelt + retry |

**UAT:**

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Sales manager DLQ açmaya çalışır | - | 403 `dlq_requires_ops` |
| 2 | Ops kullanıcı listeyi açar | - | Unresolved entry'ler listelenir |
| 3 | Resolve note ile | "SMTP fix" | Entry resolved olarak işaretlenir |
| 4 | Retry tıkla | - | `retry_count` +1 |

---

## 5. Uçtan Uca Senaryolar

### Senaryo 1: Müşteriden gelen e-postadan teklife kadar tam akış

**Amaç:** IMAP'tan gelen RFQ maili → kuyrukta inceleme → onay → otomatik teklif taslağı → müşteriye gönderim.

**Önkoşullar:**
- Operations IMAP entegrasyonu çalışır halde
- Catalog'da gerekli parçalar mevcut
- Kullanıcı en az sales_rep rolünde

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Login | sales rep | Cockpit açılır |
| 2 | Cockpit "Yeni E-postalar" sayacını kontrol et | - | 1 yeni mail |
| 3 | E-postalar menüsüne git | - | Pending kuyruğunda 1 satır |
| 4 | Maili aç | RFQ "5x C7061A1012" | Auth=pass, parça parsing OK, status=exact |
| 5 | "Onayla ve Teklif Oluştur" | - | Yeni teklif draft otomatik açılır, müşteri pre-fill |
| 6 | Birim fiyat kontrol et | Liste fiyatı geldi | Onay |
| 7 | "Müşteriye Gönder" | - | PDF üretilir, müşteriye mail |
| 8 | Müşteri yanıtı bekleyen olarak işaretlenir | - | Teklif status=sent |
| 9 | 3 gün sonra hatırlatma | - | Otomatik follow-up mail gider [VARSAYIM] |
| 10 | Müşteri "kabul" cevabı | "Kabul ediyoruz" | AI mail parse → teklif status=accepted, bildirim |

### Senaryo 2: Lead'den müşteriye dönüşüm ve ilk fırsat

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Yeni lead kaydı | Ad: Mehmet, Firma: ABC AŞ | Lead listede |
| 2 | Lead detay > "Müşteriye Dönüştür" | - | Form |
| 3 | Vergi no, sektör doldur | 1234567890, "Otomotiv" | Müşteri oluşur |
| 4 | Müşteri detayında "Yeni Fırsat" | 100.000 TL, prospecting | Fırsat açılır |
| 5 | Fırsatı negotiation'a al | Kanban'da sürükle | Aşama güncellendi |
| 6 | Teklif oluştur fırsattan | - | Teklif fırsata bağlı |
| 7 | Teklif kabul, fırsat closed_won | - | Sözleşme akışı tetiklenir |
| 8 | Sözleşme e-imzaya git | - | Müşteriye link |
| 9 | Müşteri imzalar | - | Sözleşme `active` |
| 10 | İlk fatura otomatik | - | Faturalar listesinde |

### Senaryo 3: Yüksek indirim onay akışı

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Sales rep teklif oluştur | 200.000 TL, indirim %35 | "Onay gerekiyor" uyarısı |
| 2 | "Onay İste" tıkla | - | İstek sales manager kuyruğuna düşer |
| 3 | Manager login + approvals | - | Kuyrukta görünür |
| 4 | Manager detay aç | - | Gerekçe + teklif görünür |
| 5 | "Onayla" | - | Rep'e bildirim |
| 6 | Rep teklifi "Gönder" | - | Müşteriye PDF mail |
| 7 | Audit log'da iki olay | rep+manager | Olaylar listede |

### Senaryo 4: At-Risk müşteri kurtarma

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Cockpit "At-Risk" kartı | - | 3 müşteri görünür |
| 2 | Birine tıkla | Health=32 | Riskli sebepleri liste |
| 3 | Coaching paneline geç | - | "Müşteriyi ziyaret et" önerisi |
| 4 | Yeni AI task oluştur | - | `open` durumda |
| 5 | Task'ı "Başla" | - | in_progress |
| 6 | Müşteri ziyaret sonrası "Tamamla" | - | completed; health skoru yeniden hesaplanır |

### Senaryo 5: Çoklu mail RFQ aggregation

| Adım | Eylem | Test Verisi | Beklenen Sonuç |
|---|---|---|---|
| 1 | Müşteri mail 1: "5x C7061A1012" | thread_id=xyz | Pending'e düşer |
| 2 | Müşteri mail 2 (reply): "2 daha ekleyin" | thread_id=xyz | Aynı RFQ thread_key'e bağlanır |
| 3 | E-posta detayını aç | mail 2 | "Bu thread'te 2 mail" başlığı + birleşik parts |
| 4 | Toplam quantity | C7061A1012 | 7 |
| 5 | "Onayla ve Teklif" | - | Tek teklifte 7 adet |

---

## 6. Algoritmalar ve Hesaplama Mantığı

### 6.1 E-posta Parsing Pipeline

**Girdi:** IMAP'tan çekilen tek bir RFC 822 e-posta.

**Adımlar:**

0. **Junk / Bulk Ön-Filtresi (LLM öncesi, alımda)** — Ortak `email_ingestion_service` içinde, herhangi bir Claude çağrısından önce:
   - Toplu posta başlıkları (RFC 3834): `List-Unsubscribe` / `List-Id` / `Precedence: bulk|list|junk` / `Auto-Submitted ≠ no|none` → `bulk_mail`.
   - No-reply gönderen localpart'ı (`no-reply`, `do-not-reply`, `mailer-daemon`, `mdaemon`, `postmaster`) → `noreply_sender`.
   - Operatör desenleri (`EMAIL_JUNK_SENDER_PATTERNS`) → `junk_sender`.
   - Eşleşen mail **kaydedilmez** (yalnızca log) — sıfır LLM maliyeti. `EMAIL_JUNK_FILTER_ENABLED=false` ile kapatılır. İç-domain + duplicate skip kontrolleri de bu aşamadadır.

1. **Sender Auth Verifier** — Authentication-Results header'ından SPF/DKIM/DMARC sonuçları parse edilir.
   - Üçü de `pass` → `pass`
   - Bir veya iki `pass`, diğerleri yok → `partial`
   - En az biri `fail` → `fail`
   - Hiçbiri yok → `none`

   > **Not (2026-06-03 — manuel poll):** `POST /emails/poll` artık yalnızca 0-1 numaralı adımları (alım + çöp/auth/duplicate eleme) senkron yapar; 4-10 numaralı ağır ayrıştırma adımları arka plana (`BackgroundTasks`, mail başına oturum + commit, `EMAIL_BATCH_DELAY_SECONDS` tempolu) ertelenir. Zamanlanmış cron tüm adımları kendi içinde koşturmaya devam eder.

2. **HTML Cleaner (Bleach):**
   - Allowed tags: `p, b, i, em, strong, table, tr, td, th, ul, ol, li, br, hr`
   - Disallowed: `script, iframe, object, embed, form, style` — strip edilir.
   - LXML ile tablolar Markdown'a çevrilir (kolon hizalı).

3. **Attachment Parser:**
   - Whitelist: `.xlsx, .xlsm, .xltx, .xls, .csv, .tsv, .pdf, .png, .jpg, .jpeg, .gif, .tiff, .webp, .bmp`
   - Per-file 10 MiB, max 10 file, total 25 MiB
   - Excel: `openpyxl` (`keep_vba=False`, `data_only=True`) — macro stripping
   - CSV: chardet ile encoding sniff (windows-1254 destekli)
   - PDF: `pdfplumber.extract_tables()` → text yoksa Claude Vision OCR
   - Image: doğrudan Claude Vision OCR

4. **Thread Context Injection** — son 14 gün, max 5 önceki mail başlık + parsed_parts olarak prompt'a eklenir.

5. **Claude Parser (LLM):**
   - System: "Honeywell spare-parts sales agent for Turkey..."
   - Tool: `extract_parts_from_email` (parts[]: code/description/quantity, category, sentiment)
   - Tool-use forced.

6. **Regex Fallback** — Claude breaker açıksa veya boş döndüyse, regex tabanlı parser çalışır.

6b. **Katalog-Duyarlı Kod Tarayıcı (F-A):** Mail metnindeki token'lar (ve bitişik token çiftleri, normalize edilerek) **gerçek katalog kodlarıyla** karşılaştırılır; LLM/regex'in kaçırdığı gerçek Honeywell kodları (`764744`, `581239`, `HDZWM2` …) yanlış-pozitif üretmeden geri kazanılır. Heuristic parçalar mevcut parçalarla birleştirilir (Q3/Q4).

7. **Catalog Resolver** — her part_code için, **yalnızca `is_active=true` parçalar** üzerinde (T1):
   - **Exact match:** kod birebir aynı → `status=exact`
   - **Normalized:** tire/boşluk/alt çizgi temizlenip aynı → `status=normalized`
   - **Fuzzy (Damerau-Levenshtein, OSA):** mesafe ≤ 2 ve uzunluk ≥ 6 → `status=fuzzy` (**asla otomatik onaylanmaz**); geçerli bir koda 1 hane uzaklıktaki farklı gerçek parça → `unknown` (bilerek tahmin etmez)
   - Diğer → `status=unknown`
   - Çözücünün verdiği parça, teklif satır kalemi için **tek SKU kaynağıdır** (skor-korumalı `parts_matcher` yalnızca eşik-80 fallback).

7b. **Dedup (T2):** Aynı kanonik koda denk gelen kalemler tek satıra toplanır (adetler toplanır; `quantity_suspect` + `duplicate_merged` bayrakları korunur). Tire/boşluk varyasyonu çift saymaz.

7c. **Fiyatlandırma (R1–R5, T4):** Satış fiyatı önceliği `PriceEntry.net_price` (geçerli tarih penceresi) → yoksa maliyet × (1 + `min_margin_pct`); marj 0 → fiyatsız. Süresi geçmiş fiyat girişine düşülmez (T4). Tüm hesap `Decimal`; katalog satış fiyatı teklif para birimine (TRY) çevrilir (R2/T5). Fiyat **daima yüklenen katalogdan** okunur, mailden değil.

8. **RFQ Aggregator:** SHA-256(tenant + thread_id || tenant + sender_domain + normalized_subject)[:16] → `rfq_thread_key`.

9. **AV Scan Hook:** Her iki alım yolunda da (manuel `/poll` + zamanlanmış cron) ortak `email_ingestion_service` içinde çalışır. `AV_SCAN_BACKEND=clamav` ise ClamAV INSTREAM ile taranır; varsayılan `_NoopScanner` her eki `unscanned` işaretler. `infected` çıkan ekin metni + heuristic parçaları temizlenir (LLM'e gitmez), e-posta `pending_review`'a düşer ve otomatik teklif `av_infected` gerekçesiyle engellenir.

10. **Eligibility Gate (auto-quote — `_auto_quote_eligible`):** Hepsi sağlanmalı:
    - Auth = `pass`
    - Tüm parts `exact` veya `normalized`
    - Ek/sayfa kırpılmamış (`attachment_pages_truncated=false`)
    - İlk-kez gönderen değil (`first_time_sender=false`)
    - Adet belirsizliği yok (`quantity_suspect`/`quantity_conflict` yok)
    - Değer tavanı altında
    - AV temiz (`parse_skipped_reason ≠ av_infected`)
    - Biri bile başarısızsa e-posta `pending_review`'a düşer. Onay anında (`approve_quote`, T3) tüm satırlar `is_confirmed` + fiyatlı olmalı; değilse `400` (`?force=true` ile audit'li override).

11. **LLM Rate-Limit Savunması:** 429 `Retry-After` geri-çekilme + devre kesici (`claude_breaker`, eşik 3 / 30 sn) + toplu işlem throttle (`EMAIL_BATCH_SIZE`/`EMAIL_BATCH_DELAY_SECONDS`) + çağrı başına girdi tavanı (`AI_MAX_INPUT_CHARS`=24k, `AI_MAX_ATTACHMENT_CHARS`=8k).

**Çıktı:** `EmailRequest` row + parsed parts JSON + RFQ link.

### 6.2 Forecast Hesaplaması

**Girdi:** Tüm açık fırsatlar (closed_won + open).

**Formula (aylık):**
```
forecast_revenue[month] = Σ (opportunity.amount × opportunity.probability)
  WHERE
    expected_close_date BETWEEN month_start AND month_end
    AND stage NOT IN ('closed_lost', 'closed_won')

commit_revenue[month] = Σ opportunity.amount
  WHERE
    expected_close_date BETWEEN month_start AND month_end
    AND probability ≥ 0.75   (committed band)

closed_revenue[month] = Σ opportunity.amount
  WHERE
    actual_close_date BETWEEN month_start AND month_end
    AND stage = 'closed_won'
```

**Yuvarlama:** İki ondalığa banker's rounding (round-half-to-even).

**Güncelleme:** Anlık (CRUD trigger) + her gece pipeline snapshot.

**D-034 — Tenant-yerel snapshot zamanı:** Pipeline forecast snapshot'ı artık tek bir UTC anında değil, **her tenant'ın kendi saat diliminde** alınır. Ayarlar: `tenant_settings.forecast_cron_hour` (varsayılan 4) + `forecast_cron_tz` (varsayılan `UTC`). Dispatcher her 15 dakikada bir çalışır; bir tenant'ın yerel saati yapılandırılan saate ulaştığında o tenant'a özel (tenant-scoped) snapshot alınır — böylece forecast tabanı tutarlı bir yerel iş-günü sınırında oluşur. Geçersiz timezone UTC'ye düşer + uyarı log'lanır. Aynı gün içinde mükerrer çalışma per-(tenant, yerel-tarih) guard ile engellenir.

**Sınır durumları:**
- `expected_close_date` boşsa fırsat hiçbir aya konmaz; raporda "Unscheduled" başlığı altına düşer.
- `probability` boşsa stage'in default'u kullanılır.

### 6.3 Customer Health Skoru

**Girdi:** Müşterinin son 90 günlük etkinlikleri.

**Bileşenler (toplam = 100):**

| Bileşen | Ağırlık | Hesap |
|---|---|---|
| Faturalandırma düzenliliği | 25 | (zamanında ödenen fatura sayısı / toplam fatura) × 25 |
| Son etkileşim tazeliği | 20 | son 30 gün: 20, 30-60: 15, 60-90: 5, >90: 0 |
| Açık şikayet / breach | 15 | 0 şikayet: 15, 1-2: 10, 3+: 0 |
| Sözleşme yenileme | 15 | aktif sözleşme + yenileme tarihi yakınsa: 15 |
| AI sentiment (transcript) | 15 | son 5 transkript ortalama sentiment * 15 |
| Genel etkinlik hacmi | 10 | son 90 gün mail/çağrı/toplantı sayısı normalize (max 50 = 10) |

**Toplam skor = Σ bileşenler**, [0, 100] aralığında.

**Bantlar:**
- 70-100 = healthy
- 40-69 = watchlist
- 0-39 = at-risk

**Güncelleme:** Gece 02:00 cron + her büyük olayda (fatura ödendi, breach açıldı vb.) anlık trigger.

**D-033 — Düşük Veri Bias Düzeltmesi:**
Yeni müşteriler veya yeterli sinyal toplanmamış müşteriler "0 fatura, 0 transkript" girdileri ile yapay bir 0 skor alıyorlardı. Şimdi `health_bias_correction.correct_for_data_sparsity(raw_score, signal_count)` katmanı devreye girdi:
- `signal_count` < 3 → confidence < 0.3 → skor `50` (neutral) olarak override edilir, UI'da `⚠️ Yeterli veri yok` rozeti gösterilir.
- `signal_count` 3-10 → raw skor 50'ye doğru yumuşatılır (Bayesian shrinkage).
- `signal_count` > 10 → raw skor olduğu gibi kullanılır.

Bu düzeltme yeni müşterilerin yanlışlıkla "at-risk" listesinde toplanmasını engeller.

**Pseudocode:**
```python
def compute_health_score(customer, today):
    score = 0
    # Billing
    invs = get_invoices(customer.id, last_days=90)
    if invs:
        on_time = sum(1 for i in invs if i.paid_on_time)
        score += (on_time / len(invs)) * 25
    # Recency
    last_act = get_last_activity_date(customer.id)
    delta = (today - last_act).days
    score += 20 if delta <= 30 else 15 if delta <= 60 else 5 if delta <= 90 else 0
    # Breaches
    open_breaches = count_open_breaches(customer.id)
    score += 15 if open_breaches == 0 else 10 if open_breaches <= 2 else 0
    # Renewal
    if has_active_contract(customer.id) and days_to_renewal(customer.id) <= 60:
        score += 15
    # Sentiment
    sent = avg_sentiment_last_n(customer.id, n=5)  # -1..+1
    score += max(0, sent + 1) / 2 * 15
    # Activity volume
    vol = count_activities(customer.id, last_days=90)
    score += min(vol, 50) / 50 * 10
    return round(score, 0)
```

### 6.4 High-Intent Skoru

**Girdi:** Customer aktivite + web/email engagement + sektör trendi.

**Formula:** [VARSAYIM] Gerçek implementasyon `app/services/` altında `customer_intelligence_service` veya benzeri bir modülde aranmalı. Genel mantık:

```
intent_score = w1 × recent_email_open_rate
             + w2 × demo_request_in_last_30d
             + w3 × pricing_page_visits
             + w4 × competitor_mention_in_transcripts
             + w5 × sector_growth_rate
```

`intent_score >= 0.75` ise high-intent.

### 6.5 Approval Rule Eşik Tetikleyici

**Girdi:** Yeni quote/opportunity/contract olayı.

**Adımlar:**
1. Aktif kuralları yükle (`approval_rules WHERE active=true AND tenant_id=…`).
2. Her kural için event tipini eşle.
3. Eşik karşılaştır:
   ```
   if rule.operator == '>' AND event.value > rule.threshold:
       create_approval_request(rule.approver, event)
   ```
4. Birden fazla kural eşleşirse hepsi paralel açılır.

**Karar:** Onay verilirse event devam eder; reddedilirse rollback.

### 6.6 Gelir Tahakkuku (Rev Rec)

**Girdi:** Aktif sözleşme + dönemi (örn. 12 ay).

**Formula:**
```
monthly_recognition = contract.total / contract.term_months   (straight-line)
```

**Tablo:**
```
Month 1 → recognized = monthly_recognition
Month 2 → recognized = monthly_recognition
...
Month N (last) → recognized = total - (N-1) × monthly_recognition  (yuvarlama düzeltmesi)
```

**Yuvarlama:** Her ay 2 ondalığa banker's rounding; son ay artığı taşır.

### 6.7 Lead Scoring

> **[VARSAYIM]** Gerçek implementasyon `app/services/lead_score_service.py` benzeri bir dosyada olabilir.

Olası girdiler: e-posta domain (corporate vs free), sektör fit, web etkileşim, form doldurma sayısı.

```
lead_score = base_score + sector_fit + engagement + recency_bonus
```

---

## 7. En İyi Uygulamalar

### Genel
1. **Müşteri kaydı oluşturmadan önce mutlaka vergi no'yu doğrulayın** — duplicate oluşumunu önler.
2. **Her fırsata "expected close date" girin** — forecast doğruluğu için kritik.
3. **Teklif gönderirken müşterinin doğru e-posta adresinden emin olun** — e-imza maillerinin yanlış gitmesini engeller.
4. **Onay isteğinde her zaman gerekçe yazın** — manager hızla karar verebilsin.
5. **E-posta inceleme kuyruğunu günde 2 kere boşaltın** (sabah + öğleden sonra).

### Sales Rep
- Cockpit'i günde ilk açılan sayfa yapın.
- AI Tasks'ı bitmeyen iş listesi olarak kullanmayın; ya yapın ya reddedin.
- Coaching önerilerini uyguladığınızı işaretleyin → manager raporları doğru olur.

### Sales Manager
- Onay kuyruğunu gün içinde 2 kere kontrol edin (SLA: 4 saat).
- Forecast'ı haftalık ekip toplantısında gözden geçirin.
- At-Risk müşterilere bizzat dokunun.
- Quarter sonu Planning Studio'da hedefleri update edin.

### Operations
- IMAP şifresini her 90 günde bir döndürün (`rotate_encryption_key.py` script'i).
- AV taraması açıksa daemon health'ini izleyin.
- Data Quality dashboard'ını ayda 1 kere açıp duplicate/eksik alan oranlarını sıfıra yakın tutun.

### Yaygın Hatalar
- ❌ Lead'i konvert etmeden teklif vermek → arşivde kaybolur, atfedilemez.
- ❌ Manuel teklifte fiyat listesi yerine düz rakam yazmak → margin raporu yanlış çıkar.
- ❌ Mail kuyruğunda fuzzy match'i göz kontrolü yapmadan onaylamak → yanlış parça satışı riski.
- ❌ Custom field eklemek için Operations rolünü beklemek yerine "Notlar"a yazmak → veri kaybı.

---

## 8. Sorun Giderme ve SSS

### Login & Erişim

**Sorun:** "Giriş yapamıyorum, şifreyi unuttum."
- **Neden:** Self-service şifre sıfırlama mevcut.
- **Çözüm:** Login sayfasında "Şifremi Unuttum"a tıklayın; mail kutunuza link gelir.
- **Beklenen Sonuç:** Yeni şifre belirledikten sonra giriş yapabilirsiniz.

**Sorun:** "Hesabım kilitlendi."
- **Neden:** 15 dakika içinde 5 yanlış şifre denemesi sonrası hesap 15 dakika kilitlenir (D-006 — `login_lockouts` tablosunda kalıcı kayıt).
- **Çözüm:** 15 dk bekleyin veya Operations rolündeki bir kullanıcıdan `/admin/login-lockouts` üzerinden manuel unlock isteyin.
- **Beklenen Sonuç:** Lockout süresi sonunda veya manuel unlock sonrası login yeniden mümkün.

**Sorun:** "Yanlış kişi adıma onay kuyruğuma erişiyor gibi (forensik şüphe)."
- **Neden:** Token ele geçirilmiş veya delege akışı yanlış kurulmuş olabilir.
- **Çözüm:** Profil > "Aktif Oturumlar" → tanımadığınız oturumu sonlandırın; ardından Onay Forensik Audit'ten (`/audit?event_type=approval.*`) son kararları IP+UA ile inceleyin.

### Cockpit & Veri

**Sorun:** "Cockpit kartlarımda hiç veri yok."
- **Neden:** Henüz size atanmış müşteri/fırsat yok veya tenant boş.
- **Çözüm:** Müdürünüze atama yapmasını söyleyin.

**Sorun:** "Bir müşteriyi göremiyorum ama olduğunu biliyorum."
- **Neden:** Sahip ataması başka kişide; tenant doğru ama yetki yok.
- **Çözüm:** Müdüre sahip değişikliği isteyin veya Field Permission kontrol edilmeli.

### E-postalar

**Sorun:** "Yeni mailler kuyrukta gözükmüyor."
- **Neden:** IMAP entegrasyonu bozulmuş.
- **Çözüm:** Operations → Integrations → "Test" çalıştırın.
- **Beklenen Sonuç:** Başarılı bağlantı + 1 dk içinde mailler gelir.

**Sorun:** "Mail SPF/DKIM fail görünüyor."
- **Neden:** Müşterinin domain'i auth setup'ı eksik; veya sahtecilik denemesi.
- **Çözüm:** Manuel doğrulama yapın, müşteriyle telefonda teyit edin; gerekirse "Reddet".

**Sorun:** "Excel ekteki parçalar parse olmadı."
- **Neden:** Excel dosyası macro içeriyor veya parola korumalı.
- **Çözüm:** Müşteriden CSV ile yeniden gönderim isteyin; veya manuel girin.

**Sorun:** "OCR yapılmış mail çok uzun sürdü."
- **Neden:** PDF 5 sayfayı geçti, OCR truncate edildi.
- **Çözüm:** Mail detayında "Truncated to N pages" notu görünür; sayfa 6+ için müşteriden ayrı PDF isteyin.

**Sorun:** "'Email Kontrol' bastım, '20 yeni mail' dedi ama parça sütunları boş/'ayrıştırılıyor' görünüyor."
- **Neden:** Bu beklenen davranış (2026-06-03). Buton mailleri hızlıca alır; ağır Claude ayrıştırması arka planda koşar.
- **Çözüm:** Birkaç saniye bekleyin; satırlar arka planda dolar. Yenilemeye gerek yok.

**Sorun:** "Gelen kutuma düşen bir mail uygulamada hiç görünmedi."
- **Neden:** Çöp/toplu posta ön-filtresi onu elemiş olabilir (no-reply gönderen, bülten/promosyon başlığı). Bu mailler maliyet ve gürültüyü önlemek için Claude'a hiç gönderilmeden atlanır.
- **Çözüm:** Operations sunucu loglarında gönderen + sebep (`noreply_sender` / `bulk_mail` / `junk_sender`) ile kaydı bulabilir. Meşru bir mail yanlışlıkla elendiyse, `EMAIL_JUNK_SENDER_PATTERNS`'ten ilgili deseni çıkarın veya geçici olarak `EMAIL_JUNK_FILTER_ENABLED=false` yapın. Gerçek RFQ'lar bu sinyalleri taşımadığı için pratikte etkilenmez.

**Sorun:** "Ayrıştırma sırasında 'rate limit' / 429 hatası görüyoruz."
- **Neden:** Aynı anda çok mail Claude API'sinin dakikalık limitini zorluyor.
- **Çözüm:** Sistem otomatik geri-çekilir (`Retry-After`) ve toplu işleri throttle eder; ek müdahale gerekmez. Kalıcıysa Operations `EMAIL_BATCH_SIZE`'ı düşürüp `EMAIL_BATCH_DELAY_SECONDS`'ı artırabilir.

### Teklifler & Sözleşmeler

**Sorun:** "Teklif gönder butonuna basıyorum, hata alıyorum."
- **Neden:** Onay bekliyor olabilir (indirim eşik üstü) veya müşteri e-postası eksik.
- **Çözüm:** Üstteki uyarı mesajını okuyun, ona göre düzeltin.

**Sorun:** "Müşteri imza linkine tıklayamıyor (404)."
- **Neden:** Token süresi dolmuş (30 gün) veya zaten imzalanmış.
- **Çözüm:** Sözleşmeyi yeniden gönderin.

### Performans

**Sorun:** "Liste sayfaları çok yavaş yükleniyor."
- **Neden:** 10.000+ kayıt + filtre yok.
- **Çözüm:** Filtre uygulayın (tarih aralığı, sahip), sayfa başına 50 ile sınırlı kalın.

### Yetki

**Sorun:** "Bu butonu göremiyorum."
- **Neden:** Rolünüz yetersiz veya feature flag kapalı.
- **Çözüm:** Müdürünüze rolünüzü kontrol ettirin; flag için Operations'a yazın.

### Bildirimler

**Sorun:** "E-mail bildirimleri gelmiyor."
- **Neden:** Bildirim tercihinde kapalı veya SMTP entegrasyonu çalışmıyor.
- **Çözüm:** Settings → Bildirim Tercihleri kontrol; ardından Operations'a SMTP test ettirin.

### Veri Bütünlüğü

**Sorun:** "İki tane aynı müşteri var (duplicate)."
- **Neden:** Aynı firma farklı kişiler tarafından kaydedilmiş.
- **Çözüm:** Operations'tan `/admin/merge/customer/{winner}/{loser}` ile birleştirme isteyin.

---

## Ek A — Klavye Kısayolları

| Kısayol | İşlev |
|---|---|
| `/` | Global arama kutusu odakla |
| `g + c` | Customers sayfasına git |
| `g + l` | Leads sayfasına git |
| `g + o` | Opportunities sayfasına git |
| `g + q` | Quotes sayfasına git |
| `g + e` | Emails sayfasına git |
| `Esc` | Modal kapat |
| `Ctrl/Cmd + Enter` | Form gönder |
| `?` | Klavye kısayolları yardımı |

> **[VARSAYIM]** Kısayolların tamamı sahada doğrulanmalı; bazıları henüz wireup edilmemiş olabilir.

## Ek B — Bilinen Sınırlamalar (Round-19+ Hardening)

1. **AV taraması**: Tarama kancası alım hattına bağlandı (2026-06-02, her iki poll yolunda) → ancak ClamAV daemon henüz Render üzerinde provisioned değil, dolayısıyla varsayılan `_NoopScanner` ile tüm ekler `unscanned` geçer. `AV_SCAN_BACKEND=clamav` + daemon sağlandığında otomatik devreye girer.
2. **OCR 5 sayfa cap'i**: Çok sayfalı scanned PDF'lerde 6+ sayfa görüntülenmez (review kuyruğunda not ile işaretlenir).
3. **Eval harness**: 10 fixture; tam coverage henüz ulaşılmadı. `06_typo_fuzzy` ve `10_thread_continuation` regex fallback ile %0 (full pipeline %100).
4. **AI Coaching**: `coaching_hooks` döngüsü beta; manager'a sunulan öneriler her zaman doğru olmayabilir, daima manuel değerlendirin.
5. **TSA (Time Stamping Authority)**: e-İmza akışında `sign_otp_tokens.tsa_token` kolonu rezerve ama harici TSA entegrasyonu beklemede. Şu anda IP + UA + zaman damgası iç audit için yeterli; hukuki noter onayı için TSA entegrasyonu gerekli.
6. **KMS / DEK rotation**: Per-tenant DEK envelope encryption aktif (tenant_dek + Fernet KEK) ama AWS KMS entegrasyonu (D-002) ve key rotation otomasyonu (D-017) pilot scale (20-30 kullanıcı) sonrasına ertelendi.
7. **RLS (Row-Level Security)**: PostgreSQL RLS politikaları henüz uygulanmadı; tenant izolasyonu uygulama katmanında (`assert_same_tenant`) sağlanıyor (D-001 beklemede).
8. **KVKK Export artifact storage**: Şu anda local disk (`/var/lib/kvkk-exports`); S3/object storage entegrasyonu beklemede. Pilot scale için yeterli.
9. **OCC endpoint/UI wiring**: D-009 row_version artık 11 entity'de mevcut + `guarded_update` helper'ı hazır, ancak PUT/PATCH endpoint'lerinin `row_version` zorunlu kılması + frontend 409 üç-yön merge modali (P3, sözleşme-kıran) pilot sonrasına ertelendi.
10. **Mobile responsive**: D-003 mobile-first pass beklemede; tablet/mobile breakpoint'lerde DataTable scroll bazı durumlarda kesik gösterilebilir.

---

## Ek C — Round-19+ Geliştirmeleri Özeti (Mayıs 2026)

| Bulgu | Açıklama | Etkilenen Bölüm |
|---|---|---|
| D-006 | Kalıcı per-account login lockout (5 deneme / 15 dk) | 4.1 Auth, 8. SSS |
| D-007 | JWT rotation on login (token-fixation koruması) | 4.1 Auth |
| D-009 | OCC (`row_version`) tüm 11 mutable entity'de | (backend) |
| D-010 | Cross-tenant probe tespiti + audit | 2.2 Tenant, 4.31 Admin |
| D-012 | Onay forensik audit (`approval_decisions`) | 4.12 Onay Akışları |
| D-013 | Workflow cycle + depth detection (max 10) | 4.31 Workflow Rules |
| D-014 | Gerçek SMTP gönderimi (debug stub kaldırıldı) | 4.7, 4.29, sequences |
| D-015 | KVKK subject notification email | 4.29 KVKK Export |
| D-016 | KVKK export worker (ZIP, coaching exclude) | 4.29 KVKK Export |
| D-018 | Field permission decorator (apply_request_perms_to_response) | 2.3 Field Permissions |
| D-019 | Background-job DLQ + admin endpoints | 4.31 Admin → DLQ |
| D-024 | Unsubscribe token HTML-comment leak engelleme | 4.20 Engagement |
| D-028 | Email pipeline başarısızlığı → DLQ yönlendirme | 4.31 Admin → DLQ |
| D-031 | Lead **+ Fırsat** toplu içe aktarım (CSV + per-row SAVEPOINT) | 4.4 Leadler, 4.5 Fırsatlar |
| D-033 | Health score sparse-data bias correction | 6.3 Health Algoritması |
| D-034 | Tenant-yerel forecast snapshot cron (timezone başına) | 4.16 Forecast, 6.2 |
| D-035 | Reports Builder CSV streaming (büyük dışa aktarım) | 4.15 Raporlar |
| F-006 | e-Sign OTP 5-aşamalı doğrulama akışı | 4.7 Sözleşmeler |
| F-007 | Soft-delete + Trash/Restore (7 entity) | 4.31 Admin → Trash |
| F-018 | Quorum onay politikası (N-of-M) | 4.12 Onay Kuralları |
| F-026 | Quote supersede chain (versiyon zinciri) | 4.6 Teklifler |
| F-027 | Quote item price source tracking | 4.6 Teklifler |
| F-028 | Approval SLA + escalation (24h/48h) | 4.12 Onay Kuralları |
| — | Active sessions yönetimi (kendi + admin) | 4.1 Auth |
| — | Approval delegation (chain_mode, expiry cron) | 4.12 Onay Akışları |
| — | R19 5 yeni cron job (token blocklist, nonce cleanup, SLA escalation, health batch, delegation expiry) | 6. Algoritmalar |
| SP-14 | Yedek parça çıkarımı sıfır-tolerans (maliyet-altı engelleme, tek-SKU kaynağı, başlık-duyarlı adet, tire-dedup, ±1 hane koruması) | 4.10 E-posta |
| R1–R5 | Çıkarım yeniden denetimi: Decimal para, currency dönüşümü, katalog satış fiyatı annotasyonu | 4.10 E-posta |
| T1–T5 | Aktif-parça eşleşme, kanonik dedup, onayda `is_confirmed`+fiyatlı zorunluluğu, fiyat-penceresi, TRY çevirimi | 4.10 E-posta |
| F-A | Katalog-duyarlı kod tarayıcı (gerçek Honeywell kodlarını metinden geri kazanır) | 4.10 E-posta |
| — | Manuel poll hızlandırma (ingest senkron + Claude ayrıştırma arka planda) | 4.10 E-posta |
| — | Çöp/toplu posta ön-filtresi (RFC 3834 — sıfır LLM maliyeti) | 4.10 E-posta, 8. SSS |
| — | LLM rate-limit savunması (429 Retry-After + batch throttle + girdi tavanı) | 4.10 E-posta |

---

**Sürüm geçmişi:**
- 2026-05-25 — İlk yayın (Round-18'e karşılık gelir).
- 2026-05-26 — Round-19+ Hardening update: login lockout, KVKK worker + iki-kişi onayı, DLQ, Trash/Restore, e-Sign OTP, onay forensik/quorum/SLA, lead bulk import, workflow cycle detection, health bias correction, active sessions, cross-tenant audit. (17/40 D-NNN findings shipped — 43%.)
- 2026-06-01 — Phase 12: D-007 JWT rotation, D-009 OCC (11 entity), D-028 email→DLQ, D-031 opportunity bulk import, D-034 tenant-yerel forecast cron, D-035 reports CSV streaming. Ayrıca kapsamlı CI sertleştirme (security-scan 4/4 yeşil: TruffleHog/ZAP/SAST/dependency-audit; restore-drill + load-test secret-yoksa-atla). (25/40 D-NNN findings shipped — 63%.)
- 2026-06-02 — Yedek parça sıfır-tolerans sertleştirmesi + iki yeniden denetim (R1–R5, T1–T5): maliyet-altı fiyat engelleme, tek-SKU kaynağı, aktif-parça eşleşme, kanonik dedup, onayda `is_confirmed`+fiyatlı zorunluluğu, fiyat-penceresi koruması, Decimal/currency. Katalog-duyarlı kod tarayıcı (F-A) + gerçek müşteri RFQ uçtan-uca test harness'i. E-posta hattı hardening (ortak alım yolu, AV kancası, tenant filtre).
- 2026-06-03 — E-posta hız + maliyet optimizasyonu: "Email Kontrol" hızlı poll (ağır ayrıştırma arka planda), çöp/toplu posta ön-filtresi (sıfır LLM maliyeti), 3-katmanlı LLM rate-limit savunması.

**Geri bildirim:** Yanlış veya eksik gördüğünüz yerleri `docs/USER_MANUAL.md` üzerinde PR açarak iyileştirin.
