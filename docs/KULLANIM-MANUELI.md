# Honeywell Sales Suite — Sıfırdan Kullanım Kılavuzu (TR)

Bu doküman, uygulamadaki **tüm ana özellikleri “hiç bilmeyen biri”** için adım adım anlatır. Her bölümün sonunda o ekranda görülen metriklerin **hangi formüllerle hesaplandığı** net şekilde listelenir (backend kaynaklı gerçek hesaplamalar).

> Not: Bu ürün bir “CRM + CPQ + Operasyon + Analitik” paketidir. Menüde gördüğünüz her sayfa bir iş akışına karşılık gelir.

## Hızlı Başlangıç

### Roller (Kim ne yapabilir?)

Genel yaklaşım:

- **Satış Müdürü (Admin/Manager)**: yönetim, onay, analitik ve ayarların çoğu.
- **Satış Temsilcisi (Rep)**: fırsat/teklif/müşteri üzerinde günlük operasyon.
- **Operasyon (Ops)**: katalog, fiyat, fatura vb. operasyonel süreçler.

UAT ortamı için örnek giriş bilgileri `docs/UAT-KULLANIM-KILAVUZU.md` içinde mevcut.

### Uygulama Mantığı (1 cümleyle)

- **E-mail/Lead → Müşteri → Teklif → (Onay/PDF/E-İmza) → Kontrat → Fatura → Gelir Tanıma → Analitik**

### Navigasyon (Sol Menü)

Sol menüdeki başlıklar, birimlerin iş akışlarına göre grupludur. Günlük iş için en çok kullanılanlar:

- **Dashboard**
- **Pipeline (Board)**
- **Müşteriler / Leads**
- **Teklifler (CPQ)**
- **Faturalar**
- **Kontratlar**
- **Kampanyalar**
- **Gelir Tanıma**

---

## 1) Dashboard (Kontrol Paneli)

### Ne işe yarar?

Sistemin “tek bakışta” özetidir: KPI kartları, pipeline dağılımı, trendler ve aksiyon gerektiren alanlar.

### Nasıl kullanılır? (0’dan)

- Sol menüden **Dashboard**’a girin.
- KPI kartlarına bakarak “bugün sistemde ne oluyor?”u görün:
  - Aktivite/teklif/fırsat hacmi
  - Gelir trendi
  - Riskli müşteri/fırsat
- Grafiklerdeki değişimleri takip edip Board/Customers/Quotes bölümlerine detay için geçin.

### Hesaplamalar (Özet)

Dashboard kartlarının bir kısmı backend “analytics” sorgularından gelir. Net formüller ilgili servislerde yer alır:

- Aylık trend gibi metrikler: `backend/app/api/v1/analytics.py`
- Pipeline tahmin metrikleri: `backend/app/services/forecast_service.py`
- Risk/Leak metrikleri: `backend/app/services/leak_detection_service.py`

---

## 2) Pipeline / Board (Kanban)

### Ne işe yarar?

Fırsatları (deal/opportunity) satış aşamalarında **sürükle-bırak** yönetirsiniz. Amaç, satış sürecini görünür kılmak ve tahmin/aksiyon üretmektir.

### Temel kavramlar

- **Pipeline**: Aşamaların (stage) dizisi. Şirketinizde birden fazla pipeline olabilir.
- **Stage (Aşama)**: Örn. araştırma → nitelendirme → teklif → müzakere → kazanıldı/kaybedildi.
- **Kart (Fırsat)**: Tek bir satış fırsatı. Kartın tutarı, müşterisi ve kapanış tarihi gibi bilgiler olur.
- **Weighted (Ağırlıklı) değer**: Her aşamanın kazanma olasılığına göre ağırlıklandırılmış tahmin değeri.

### Nasıl kullanılır? (0’dan)

- Sol menüden **Board / Pipeline** sayfasına girin.
- Üstteki seçimden pipeline’ı seçin.
- Her kolondaki kartlar o aşamadaki fırsatları temsil eder.
- Bir kartı tutup diğer kolona sürükleyerek aşama değiştirin.
- Bir karta tıklayıp detay sayfasına girin:
  - müşteri, tutar, kapanış tarihi, notlar, aktiviteler
  - aşama gereksinimleri (eksik alanlar / ipuçları)

### Hesaplamalar (Formüller)

Bu modülde en kritik hesaplar **forecast (tahmin)** ve **aşama olasılıkları**dır.

#### 2.1 Weighted Forecast (Ağırlıklı Tahmin)

Backend’de snapshot alınırken hesaplanır: `backend/app/services/forecast_service.py`

- **Stage Probability (olasılık)**:
  - Öncelik sırası: DB’de tanımlı olasılıklar → yoksa fallback.
  - Fallback olasılıklar:
    - prospecting: 0.1
    - qualified: 0.3
    - proposal: 0.5
    - negotiation: 0.7
    - closed_won: 1.0
    - closed_lost: 0.0
- **Stage Total Amount**:
  - \text{totalamount(stage)} = \sum \text{opportunity.amount}
- **Stage Weighted Amount**:
  - \text{weightedamount(stage)} = \text{totalamount(stage)} \times \text{probability(stage)}

#### 2.2 Week-over-Week (Haftalık karşılaştırma)

API: `backend/app/api/v1/forecast.py`

- \Delta = \text{currenttotal} - \text{previoustotal} 
- \Delta = (\Delta / \text{previoustotal}) \times 100  (previous_total 0 ise 0)

---

## 3) Müşteriler (Customer Management)

### Ne işe yarar?

Müşteri kartlarını (firma/kişi) yönetir, müşteriyle ilgili teklifleri, fırsatları, kontratları ve sağlık/risk metriklerini görürsünüz.

### Nasıl kullanılır? (0’dan)

- Sol menüden **Müşteriler** sayfasına girin.
- Arama/filtre ile müşteriyi bulun.
- Bir müşteriye tıklayıp detay sayfasına girin:
  - İletişim bilgileri (telefon/e-posta/adres)
  - Teklif geçmişi ve toplam değer
  - Kontratlar ve faturalar
  - (Varsa) alt şirketler / hesap hiyerarşisi
  - Müşteri sağlık skoru ve öneriler

### Hesaplamalar (Formüller)

#### 3.1 Müşteri Sağlık Skoru (0–100)

Servis: `backend/app/services/customer_health_service.py` + `backend/app/services/health_indicators.py`

**Genel skor**:

- Her gösterge için 0–100 arası bir skor üretilir.
- Ağırlıklı ortalama alınır:
  - \text{raw} = \frac{\sum (\text{indicator.score} \times \text{indicator.weight})}{\sum \text{indicator.weight}} 
  - \text{score} = clamp(0, 100, round(\text{raw}))

**Risk seviyesi** (eşikler):

- healthy_threshold = 70
- at_risk_threshold = 40

**Gösterge formülleri** (özet):

- **Teklif Sıklığı** (son 180 gün):
  - aylık ortalama = \text{quotecount} / (180/30)
  - skor = min(100, \text{monthlyavg} \times 50)
  - ağırlık: 0.20
- **Yanıt Süresi** (Email → Teklife geçiş, saat):
  - avg_hours = ortalama(Quote.created_at − EmailRequest.received_at)
  - 4–48 saat aralığına clamp edilir
  - skor = 100 \times (48 - clamped) / (48 - 4)
  - ağırlık: 0.15
- **Değer Trendi** (son 90 gün vs önceki 90 gün):
  - trend_pct = ((recent - older)/older) \times 100
  - skor = clamp(0,100, 50 + trendpct)
  - ağırlık: 0.20
- **Parça Çeşitliliği**:
  - unique_parts = distinct(QuoteItem.honeywell_code) sayısı
  - hedef = 10
  - skor = min(100, (uniqueparts/10) \times 100)
  - ağırlık: 0.10
- **Etkileşim Güncelliği** (son teklif veya son email’e göre):
  - days_since = bugün − max(last_quote_date, last_email_date)
  - 7 gün ve altı: 100
  - 90 gün ve üstü: 0
  - arası: lineer
  - ağırlık: 0.20
- **Dönüşüm Oranı**:
  - total = toplam teklif sayısı (lookback)
  - converted = status ∈ {sent, accepted}
  - rate = (converted/total) \times 100
  - skor = min(100, rate \times 1.25)
  - ağırlık: 0.15

---

## 4) Leads (Lead Yönetimi)

### Ne işe yarar?

Henüz müşteri olmamış potansiyel kişileri/fırsatları yönetirsiniz. Lead’ler puanlanır, filtrelenir ve “müşteriye/fırsata” dönüştürülür.

### Nasıl kullanılır? (0’dan)

- Sol menüden **Leads**’e girin.
- Listeyi durum/puan/owner filtreleriyle daraltın.
- Bir lead’e tıklayıp detayına girin.
- Lead’i:
  - güncelleyin
  - yeniden skorlatın (rescore)
  - uygun olduğunda “dönüştürün” (müşteri + fırsat yaratır)

### Hesaplamalar (Formüller)

#### 4.1 Lead Skoru (Davranışsal skor — 0–100)

Servis: `backend/app/services/scoring_service.py`

Skor, sinyallerin “delta” etkisiyle değişir ve 0–100 aralığına clamp edilir:

- \Delta = POSITIVESIGNALS[signal] + NEGATIVESIGNALS[signal] 
- \text{new} = clamp(0,100, old + \Delta)

Örnek sinyal ağırlıkları:

- email_replied: +15
- meeting_booked: +20
- quote_sent: +10
- quote_approved: +15
- email_bounced: −20
- dnc_flagged: −50
- no_touch_30d: −20

#### 4.2 Lead Funnel / Kaynak dönüşüm oranı

API: `backend/app/api/v1/leads.py`

- Kaynak bazında:
  - conversion_rate_pct = (convertedcount / count) \times 100
  - avg_days_to_convert = totaldays / convertedcount (yoksa null)

---

## 5) Teklifler (CPQ)

### Ne işe yarar?

Parça/ürün ekleyip fiyat/iskonto/vergiyi hesaplayarak müşteriye teklif üretirsiniz. Onay, PDF ve e-imza süreçlerine bağlanır.

### Nasıl kullanılır? (0’dan)

- Sol menüden **Teklifler**’e girin.
- “Yeni Teklif” ile boş teklif açın veya:
  - Email’den teklif üretin
  - PDF’den teklif içeri aktarın
- Kalem ekleyin:
  - parça kodu/isim ile arayın
  - adet ve iskontoyu girin
- Vergi oranını (KDV) belirleyin.
- Teklifi kaydedin.
- Gerekirse:
  - Onaya gönderin / onaylayın
  - PDF indir
  - E-imza iste
  - Para birimi dönüşümü yap

### Hesaplamalar (Formüller)

#### 5.1 Satır (Line) hesapları

Servis: `backend/app/services/quote_service.py`

- discounted_unit_price = unitprice \times (1 - discountpct/100)
- line_total = quantity \times discountedunitprice
- line_total round(2)

#### 5.2 Teklif toplamları

Servis: `backend/app/services/quote_service.py`

- subtotal = \sum linetotal
- discount_total = \sum ((unitprice \times quantity) - linetotal)
- tax_amount = subtotal \times (taxrate/100)
- grand_total = subtotal + taxamount
Hepsi round(2)

#### 5.3 Para birimi dönüştürme (Re-price)

API: `backend/app/api/v1/quotes.py`

- Her kalem için unit_price dönüştürülür ve line_total yeniden hesaplanır:
  - line_total = newunitprice \times quantity \times (1 - discountpct/100)
- subtotal yeniden toplanır
- tax_amount = subtotal \times taxrate/100
- grand_total = subtotal - discounttotal + taxamount

#### 5.4 Fiyat bulma (Customer / Tier / Standard)

API: `backend/app/api/v1/pricing.py` (`/pricing/lookup`)
Çözüm sırası:

1. **Müşteri kontratlı fiyatı** (valid_from/valid_until uygunsa)
2. **Tier (adet kırılımı)** (min_qty ≤ qty ≤ max_qty)
3. **Standart net_price** (son price entry)

#### 5.5 Rehberli Satış (Guided Selling Wizard)

Servis: `backend/app/services/guided_selling_service.py`

- Her kuralın “conditions” alanı, answers sözlüğüyle eşleşirse:
  - suggest_parts ve suggest_bundles birleştirilir
- match_count = suggested_part_ids + suggested_bundle_ids toplamı

---

## 6) Faturalar

### Ne işe yarar?

Teklif/kontrat üzerinden veya manuel olarak fatura üretir; durum geçişleriyle (taslak→gönderildi→ödendi vb.) tahsilat sürecini takip edersiniz.

### Nasıl kullanılır? (0’dan)

- Sol menüden **Faturalar** sayfasına girin.
- Listeden bir faturayı açın veya “Yeni” ile oluşturun.
- Taslak faturada:
  - kalemleri (items_json) ve ara toplamı girin
  - vergi oranını (tax_rate) girin
  - vade tarihini ayarlayın
- Durum geçişleriyle ilerletin:
  - draft → sent
  - sent/overdue → paid
  - (gerekiyorsa) voided

### Hesaplamalar (Formüller)

API: `backend/app/api/v1/invoices.py`

- tax_amount = round(subtotal \times taxrate/100, 2)
- grand_total = round(subtotal + taxamount, 2)

Notlar:

- Fatura numarası: `INV-{year}-{seq}` (yıl içindeki adet + 1)
- Durum geçişleri `VALID_TRANSITIONS` ile kısıtlıdır.

---

## 7) Kontratlar

### Ne işe yarar?

Tekliften doğan veya manuel yaratılan sözleşmeleri yönetir; aktivasyon ve değişiklik (amendment) süreçlerini takip edersiniz.

### Nasıl kullanılır? (0’dan)

- Sol menüden **Kontratlar** sayfasına girin.
- Liste filtresiyle (durum/müşteri/arama) sözleşmeleri bulun.
- Yeni kontrat oluşturun:
  - müşteri seçin
  - başlık/tarih/değer girin
  - (varsa) quote bağlayın
- Taslak kontratı “Aktifleştir” ile aktif edin.
- Değişiklik ekleyin (amend):
  - type: extension/modification/termination
  - effective_date
  - changes_json (değişiklik detayları)

### Hesaplamalar / Kurallar

API: `backend/app/api/v1/contracts.py`

- Kontrat aktivasyonu:
  - sadece status == draft iken
  - status → active
  - signed_at = now
- Amendment:
  - amendment_type ∈ {extension, modification, termination}
  - Eğer kontrat active ise status → amended

---

## 8) Kampanyalar

### Ne işe yarar?

Kampanya oluşturur, lead/müşteri üyeleri eklersiniz ve kampanya ROI / dönüşüm metriklerini takip edersiniz.

### Nasıl kullanılır? (0’dan)

- Sol menüden **Kampanyalar** sayfasına girin.
- “Yeni kampanya” ile kampanya oluşturun (manager).
- Kampanya detayında:
  - bütçe (budget), beklenen gelir (expected_revenue) girin
  - gerçek maliyet (actual_cost) ve gerçek gelir (actual_revenue) güncelleyerek ROI’yi izleyin
- Üyeler sekmesinde lead/müşteri ekleyin.
- Üye durumlarını (sent/responded/converted vb.) güncelleyin.

### Hesaplamalar (Formüller)

ROI endpoint’i: `backend/app/api/v1/campaigns.py` `GET /campaigns/{id}/roi`

- member_count = count(CampaignMember)
- responded_count = count(status == responded)
- converted_count = count(status == converted)
- conversion_rate = (convertedcount / membercount) \times 100 (member_count 0 ise 0)
- roi_pct:
  - Eğer actual_cost > 0:
    - roipct = ((actualrevenue - actualcost) / actualcost) \times 100
  - Değilse: 0

---

## 9) Gelir Tanıma (Revenue Recognition)

### Ne işe yarar?

Kontrat gelirini zaman içine yayarak (ör. straight-line) aylık dönem kayıtları oluşturur; “tanındı” işlemleriyle muhasebe uyumlu bir gelir takibi sağlar.

### Nasıl kullanılır? (0’dan)

- Sol menüden **Gelir Tanıma**’ya girin.
- “Yeni takvim” ile bir schedule oluşturun:
  - kontrat
  - tanıma tipi (immediate/straight_line/milestone/usage)
  - başlangıç/bitiş
  - toplam tutar + para birimi
- Schedule açıp “Kayıtları oluştur” ile aylık entry’leri üretin.
- Aylık bir entry için “Tanı” diyerek tanındı durumuna getirin.

### Hesaplamalar (Formüller)

API: `backend/app/api/v1/revenue_recognition.py`

#### 9.1 Dönem kayıtları oluşturma (generate entries)

- periods = start_month..end_month (YYYY-MM) listesi
- per_month = round(totalamount / len(periods), 2)
- remainder = round(totalamount - permonth \times len(periods), 2)
- son ay amount = per_month + remainder, diğerleri per_month

#### 9.2 Tanıma (recognize entry)

- entry.status = recognized
- entry.recognized_amount = entry.amount
- schedule.recognized_amount = round(schedule.recognizedamount + entry.amount, 2)

#### 9.3 Dashboard oranı

- recognition_rate_pct = round(totalrecognized / totalscheduled \times 100, 2) (0 ise 0)