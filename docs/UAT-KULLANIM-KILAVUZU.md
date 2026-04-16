# Honeywell Sales Suite — UAT Kullanim Kilavuzu

## Giris

Honeywell Sales Suite, Honeywell yedek parca ve endustriyel ekipman satis sureclerini uctan uca yoneten bir CRM ve CPQ platformudur. Bu kilavuz, UAT (Kullanici Kabul Testi) sureci icin tum ozelliklerin nasil test edilecegini adim adim aciklar.

### Giris Bilgileri

| Rol | E-posta | Sifre | Yetkiler |
|-----|---------|-------|----------|
| Satis Muduru (Admin) | admin@honeywell.com | Admin123! | Tam yetki, yonetim paneli, raporlar |
| Satis Temsilcisi (Rep) | rep@honeywell.com | Rep12345 | Firsat, teklif, musteri yonetimi |
| Operasyon (Ops) | ops@honeywell.com | Ops12345 | Stok, fatura, operasyonel islemler |

### URL'ler

| Ortam | URL |
|-------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Dokumantasyonu | http://localhost:8000/docs |

---

## 1. Dashboard

**Navigasyon:** Sol menu &rarr; Dashboard (Ana Sayfa)

**Beklenen Gorunum:**
- Ust kisimda KPI kartlari: toplam firsat tutari, acik firsatlar, kazanma orani, bu ayin geliri
- Pipeline dagitim grafigi (bar/donut chart)
- Son aktiviteler listesi
- Yaklasan kapanislar

**Test Adimlari:**
1. Admin hesabiyla giris yapin
2. Dashboard sayfasinin yuklendigini dogrulayin
3. KPI kartlarindaki rakamlarin mantikli oldugunu kontrol edin (5 firsat, toplam ~802.000 TRY)
4. Pipeline grafiklerinin gosterildigini dogrulayin
5. Son aktiviteler bolumunde demo aktivitelerin listelenigini kontrol edin
6. Farkli kullanici rolleriyle giris yaparak dashboard'un role gore filtrelendigini test edin

**Mock Veri:**
- 5 firsat (prospecting'den closed_won'a kadar cesitli asamalarda)
- 20 aktivite kaydi
- 5 bildirim

---

## 2. Pipeline / Board (Kanban)

**Navigasyon:** Sol menu &rarr; Pipeline

**Beklenen Gorunum:**
- Ust kisimda pipeline secici dropdown (3 pipeline: Standart Satis, Hizli Satis, Proje Satisi)
- Kanban board: her asama bir kolon olarak gosterilir
- Her firsat bir kart olarak gorunur (baslik, tutar, musteri, kapanma tarihi)
- Sales Path cubugu (ilerleme gostergesi)

**Test Adimlari:**
1. Varsayilan "Standart Satis" pipeline'inin secili geldigini dogrulayin
2. 6 asama gorulmeli: Arastirma, Nitelendirme, Teklif, Muzakere, Kazanildi, Kaybedildi
3. Firsat kartlarinin dogru asamalarda oldugunu kontrol edin
4. Bir karti suruklayerek farkli asamaya tasima islemini test edin
5. Pipeline seciciyi degistirerek "Hizli Satis" (4 asama) ve "Proje Satisi" (7 asama) pipeline'larini test edin
6. Bir firsat kartina tiklayarak detay sayfasini acin
7. Sales Path cubugunun mevcut asamayi dogru gosterdigini dogrulayin

**Mock Veri:**
- 3 pipeline (Standart Satis varsayilan, Hizli Satis, Proje Satisi)
- 5 firsat Standart Satis pipeline'ina atanmis
- Asamalar JSON formatinda `stages_json` alaninda saklanir

---

## 3. Musteri Yonetimi

**Navigasyon:** Sol menu &rarr; Musteriler

**Beklenen Gorunum:**
- Musteri listesi tablosu (ad, sirket, e-posta, telefon, bolge)
- Filtreleme ve arama
- Detay sayfasinda: iletisim bilgileri, teklifler, firsatlar, sozlesmeler

**Test Adimlari:**
1. 10 musterinin listede goruntulendigini dogrulayin
2. Arama kutusuna "Anadolu" yazarak filtreleme yapin
3. "Anadolu Endustri A.S." detay sayfasini acin
4. Hesap hiyerarsisi bolumunu kontrol edin:
   - Anadolu Endustri altinda 2 alt sirket gorunmeli: Trakya Endustriyel, GAP Muhendislik
   - Marmara HVAC altinda 1 alt sirket: Bolu Termal Sistemler
5. Rollup metriklerinin hesaplandigini kontrol edin (alt sirketlerin toplam firsat tutarlari)
6. Musteri saglik skorunun (varsa) gosterildigini dogrulayin
7. KVKK onayi alanlarinin goruntulendigini kontrol edin

**Hesap Hiyerarsisi Mock Verisi:**
```
Anadolu Endustri A.S.
  ├── Trakya Endustriyel
  └── GAP Muhendislik

Marmara HVAC Systems
  └── Bolu Termal Sistemler
```

---

## 4. Lead Yonetimi

**Navigasyon:** Sol menu &rarr; Leads

**Beklenen Gorunum:**
- Lead listesi: ad, soyad, sirket, skor, durum
- Skor cubugu (0-100)
- Durum etiketleri renkli badge olarak

**Test Adimlari:**
1. 5 lead'in listede gorundugunu dogrulayin
2. Lead skorlarini kontrol edin (20-85 arasi cesitli skorlar)
3. "Zeynep Celik" lead'ine tiklayin (skor: 85, qualified)
4. Lead donusturme akisini test edin:
   - "Donustur" butonuna tiklayin
   - Musteri ve firsat olusturma formunun acildigini dogrulayin
5. Lead filtreleme: sadece "qualified" lead'leri goruntuleyin

**Mock Veri:**

| Ad | Sirket | Durum | Skor |
|----|--------|-------|------|
| Burak Ozturk | Potansiyel A.S. | new | 45 |
| Selin Arslan | Yeni Proje Ltd. | contacted | 62 |
| Can Tekin | Sanayici Grup | qualified | 78 |
| Zeynep Celik | HVAC Pro | qualified | 85 |
| Emre Sahin | - | unqualified | 20 |

---

## 5. Teklif Yonetimi (CPQ)

**Navigasyon:** Sol menu &rarr; Teklifler

**Beklenen Gorunum:**
- Teklif listesi: numara, musteri, durum, toplam tutar, tarih
- Durum akisi: Taslak &rarr; Onay Bekliyor &rarr; Onaylandi &rarr; Gonderildi &rarr; Kabul Edildi

**Test Adimlari:**
1. 15 teklifin listede gorundugunu dogrulayin
2. "Yeni Teklif" butonuyla teklif olusturma formunu acin
3. Musteri secin, urun ekleyin (parca kodunu veya adini aratarak)
4. Fiyat kademeleri kontrolu:
   - HW-FILT-001 icin 50+ adet sectiginde birim fiyatin 85 USD'ye dustugunu dogrulayin
   - HW-SENS-001 icin 10+ adet sectiginde %9.4 indirim uygulandigini kontrol edin
5. Musteri ozel fiyatlama:
   - Anadolu Endustri musterisi secildiginde HW-FILT-001 fiyatinin 70 USD geldigini dogrulayin
6. Onay akisini test edin:
   - Taslak teklifi onaya gonderin
   - Admin olarak onaylayin
   - Musteriye gonderme islemini test edin
7. PDF indirme butonunu test edin
8. E-imza isteme butonunu test edin (Bolum 6'ya bakiniz)

**Rehberli Satis Sihirbazi:**
1. "Rehberli Satis" butonuna tiklayin
2. Adim adim musteri ihtiyac analizi sorularini cevaplayin
3. Onerilen urunlerin dogru geldigini dogrulayin

**Mock Veri:**
- 15 teklif (QT-2026-001000 - QT-2026-001014)
- Durumlari: draft, pending_approval, approved, sent, accepted, rejected
- Her teklifte 1-4 kalem urun

---

## 6. Fatura Yonetimi

**Navigasyon:** Sol menu &rarr; Faturalar

**Beklenen Gorunum:**
- Fatura listesi: numara, musteri, durum, tutar, vade tarihi
- Durum renkleri: taslak (gri), gonderildi (mavi), odendi (yesil), gecikti (kirmizi), iptal (sari)

**Test Adimlari:**
1. 5 faturanin listede gorundugunu dogrulayin
2. Her durumdaki faturalari kontrol edin:
   - INV-2026-0001: Odendi (paid)
   - INV-2026-0002: Gonderildi (sent)
   - INV-2026-0003: Taslak (draft)
   - INV-2026-0004: Gecikti (overdue)
   - INV-2026-0005: Iptal (voided)
3. Fatura detay sayfasini acin, teklif baglantisini dogrulayin
4. Durum gecisleri:
   - Taslak faturaya "Gonder" butonuyla gonderildi durumuna getirin
   - Gonderilen faturaya "Odeme Alindi" ile odendi durumuna getirin
5. E-imza butonunun calistigini dogrulayin

**Mock Veri:**

| Fatura No | Durum | Kaynak Teklif |
|-----------|-------|---------------|
| INV-2026-0001 | Odendi | Kabul edilmis teklif |
| INV-2026-0002 | Gonderildi | Kabul edilmis teklif |
| INV-2026-0003 | Taslak | Onaylanmis teklif |
| INV-2026-0004 | Gecikti | Gonderilmis teklif |
| INV-2026-0005 | Iptal | Kabul edilmis teklif |

---

## 7. Kampanya Yonetimi

**Navigasyon:** Sol menu &rarr; Kampanyalar

**Beklenen Gorunum:**
- Kampanya listesi: ad, tur, durum, butce, gerceklesen gelir
- ROI gostergesi
- Uye sayisi

**Test Adimlari:**
1. 3 kampanyanin listede gorundugunu dogrulayin
2. "Q1 2026 Sensor Kampanyasi" detayini acin:
   - Tur: email, Durum: active
   - Butce: 15.000, Harcama: 5.000
   - Beklenen Gelir: 45.000, Gerceklesen: 32.000
   - ROI hesabini kontrol edin
3. Kampanya uyelerini goruntuleyin (lead ve musteri karisik, 15+ uye)
4. Uye durumlarini kontrol edin: sent, opened, clicked, responded, converted, unsubscribed
5. Yeni kampanya olusturma formunu test edin
6. Uye ekleme islemini test edin (lead veya musteri ekle)
7. "HVAC Yenileme Webinari" kampanyasinin "completed" durumunda oldugunu dogrulayin

**Mock Veri:**

| Kampanya | Tur | Durum | Butce | Gelir |
|----------|-----|-------|-------|-------|
| Q1 2026 Sensor Kampanyasi | email | active | 15.000 | 32.000 |
| HVAC Yenileme Webinari | webinar | completed | 8.000 | 98.000 |
| Yeni Musteri Sosyal Medya | social | draft | 20.000 | 0 |

---

## 8. Sozlesme Yonetimi

**Navigasyon:** Sol menu &rarr; Sozlesmeler

**Beklenen Gorunum:**
- Sozlesme listesi: baslik, musteri, durum, deger, baslangic/bitis tarihi
- Durum etiketleri: taslak, aktif, tamamlandi

**Test Adimlari:**
1. 4 sozlesmenin listede gorundugunu dogrulayin
2. "Anadolu HVAC Bakim Sozlesmesi" detayini acin:
   - Durum: active, Deger: 250.000 TRY
   - Sure: 12 ay
   - Imzalayan bilgisi gorunmeli
3. "Karadeniz Yillik Servis" sozlesmesinin taslak durumunda oldugunu dogrulayin
4. "GAP Proses Otomasyon" sozlesmesinin tamamlandi durumunda oldugunu dogrulayin
5. Sozlesme-fatura iliskisini kontrol edin

**Mock Veri:**

| Sozlesme | Durum | Deger | Sure |
|----------|-------|-------|------|
| Anadolu HVAC Bakim Sozlesmesi | active | 250.000 | 12 ay |
| Ege Sensor Tedarikat | active | 180.000 | 6 ay |
| Karadeniz Yillik Servis | draft | 95.000 | 12 ay |
| GAP Proses Otomasyon | completed | 350.000 | 24 ay |

---

## 9. Gelir Tanima

**Navigasyon:** Sol menu &rarr; Gelir Tanima

**Beklenen Gorunum:**
- Gelir tanima takvimleri listesi
- Aylik gelir dagitimi tablosu
- Tanima durumu: pending (bekleniyor), recognized (taninmis)

**Test Adimlari:**
1. 2 gelir tanima takviminin gorundugunu dogrulayin
2. "Anadolu HVAC Bakim" takvimini acin:
   - Tip: straight_line (dogusal)
   - Toplam: 250.000 TRY, 12 ay
   - Aylik tutar: ~20.833 TRY
   - Gecmis aylar "recognized" durumunda olmali
   - Gelecek aylar "pending" durumunda olmali
3. "Ege Sensor Tedarikat" takvimini acin:
   - Toplam: 180.000 TRY, 6 ay
   - Aylik tutar: 30.000 TRY
4. Manuel tanima islemini test edin:
   - Bekleyen bir girisi secin
   - "Tanima Yap" butonuna tiklayin
   - Durumun "recognized" olarak degistigini dogrulayin

**Mock Veri:**
- Takvim 1: 250.000 TRY / 12 ay, kismen taninmis
- Takvim 2: 180.000 TRY / 6 ay, kismen taninmis

---

## 10. E-posta

**Navigasyon:** Sol menu &rarr; E-posta

**Beklenen Gorunum:**
- Gelen kutusu: musteri e-postalari listesi
- Durum etiketleri: new, parsed, quoted
- AI yanit onerisi paneli

**Test Adimlari:**
1. 8 e-posta istegin listede gorundugunu dogrulayin
2. Bir e-postaya tiklayin, icerigini goruntuleyin
3. AI yanit onerisi butonunu test edin (Claude API baglantisi gereklidir)
4. E-posta sablonlari sekmesine girin (3 sablon olmali):
   - "Teklif Gonderim" sablonu: {{customer_name}}, {{quote_number}} degiskenleri
   - "Takip Maili" sablonu: {{customer_name}}, {{days_ago}} degiskenleri
   - "Hosgeldiniz" sablonu: {{customer_name}}, {{rep_name}}, {{rep_email}} degiskenleri
5. Sablon onizleme ozelligini test edin
6. Sablondaki degiskenlerin otomatik doldurulmasini dogrulayin

**Mock Veri:**
- 8 e-posta istegi (cesitli durumlarda)
- 3 e-posta sablonu (Teklif Gonderim, Takip Maili, Hosgeldiniz)

---

## 11. AI Ozellikleri

**Navigasyon:** Sol menu &rarr; AI Asistani

> **Not:** AI ozellikleri Claude API key gerektirir. API key yoksa bu ozellikler sinirli calisir.

**Beklenen Gorunum:**
- AI gorev paneli
- Icerik onerisi alani
- Deal risk analizi

**Test Adimlari:**
1. AI gorev olusturma formunu acin
2. "Bu firsat icin en uygun sonraki adim ne olmali?" sorusunu girin
3. AI icerik analizi:
   - Bir firsata gidin, "AI Analiz" butonuna tiklayin
   - Risk faktoru ve onerilerinin goruntulenmesini bekleyin
4. Email AI draft:
   - E-posta modulu icerisinde "AI ile Yazdir" butonuna tiklayin
   - Otomatik taslak olusmali
5. Deal risk analizi:
   - Pipeline sayfasinda yuksek degerli bir firsata tiklayin
   - Risk sinyallerinin goruntulenmesini kontrol edin (pricing_concern, no_touch, positive)

**Mock Veri:**
- 3 opportunity signal (farkli tip ve siddetlerde)
- 3 AI gorevi (firsatlara baglanmis)

---

## 12. Pipeline Ayarlari

**Navigasyon:** Sol menu &rarr; Ayarlar &rarr; Pipeline Yonetimi

**Beklenen Gorunum:**
- Pipeline listesi (3 pipeline)
- Her pipeline icin asama listesi duzenlenebilir
- Varsayilan pipeline secimi

**Test Adimlari:**
1. 3 pipeline'in listede gorundugunu dogrulayin
2. "Standart Satis" pipeline'inin varsayilan (default) oldugunu kontrol edin
3. Yeni pipeline olusturma formunu test edin:
   - Ad girin, asamalari ekleyin (key, label, probability, order)
   - Kaydetme islemini dogrulayin
4. Mevcut pipeline'a asama ekleme/cikarma islemini test edin
5. Asama sirasini (order) degistirme islemini test edin
6. Varsayilan pipeline degistirme islemini test edin

**Mock Veri:**

| Pipeline | Varsayilan | Asama Sayisi |
|----------|-----------|-------------|
| Standart Satis | Evet | 6 |
| Hizli Satis | Hayir | 4 |
| Proje Satisi | Hayir | 7 |

---

## 13. Bolge Yonetimi

**Navigasyon:** Sol menu &rarr; Ayarlar &rarr; Bolgeler

**Beklenen Gorunum:**
- Bolge agaci gorunumu (hiyerarsik)
- Her bolge icin atanan kullanicilar
- Bolge-musteri iliskileri

**Test Adimlari:**
1. 5 bolgenin gorundugunu dogrulayin
2. Hiyerarsiyi kontrol edin:
   ```
   Marmara Bolgesi
     ├── Istanbul Saha
     └── Bursa-Kocaeli
   Anadolu Bolgesi
   Ege-Akdeniz Bolgesi
   ```
3. "Istanbul Saha" bolgesine tiklayin:
   - Sahip: rep@honeywell.com (Elif Kaya)
   - Atanmis musteriler: Anadolu Endustri, Marmara HVAC
4. "Marmara Bolgesi" bolgesine tiklayin:
   - Sahip: admin@honeywell.com (Ahmet Yilmaz)
5. Yeni bolge olusturma ve ust bolge secimi
6. Kullanici atama islemini test edin (owner/member/viewer rolleri)
7. Bolgeye musteri atama islemini kontrol edin

**Mock Veri:**

| Bolge | Ust Bolge | Sahip | Musteri Sayisi |
|-------|-----------|-------|---------------|
| Marmara Bolgesi | - | Admin | - |
| Istanbul Saha | Marmara | Rep | 2 |
| Bursa-Kocaeli | Marmara | - | 1 |
| Anadolu Bolgesi | - | - | 1 |
| Ege-Akdeniz Bolgesi | - | - | 1 |

---

## 14. Fiyatlama Yonetimi

**Navigasyon:** Sol menu &rarr; Ayarlar &rarr; Fiyatlama

**Beklenen Gorunum:**
- Fiyat kademeleri tablosu (parca bazinda)
- Musteri ozel fiyatlar listesi
- Marj hesaplama

**Test Adimlari:**
1. Fiyat kademeleri sekmesini acin
2. HW-FILT-001 (Hava Filtresi) kademelerini kontrol edin:

   | Min Adet | Max Adet | Birim Fiyat | Indirim % |
   |----------|----------|-------------|-----------|
   | 1 | 49 | 95 USD | 0% |
   | 50 | 199 | 85 USD | 10.5% |
   | 200+ | - | 72 USD | 24.2% |

3. HW-SENS-001 (Sicaklik Sensoru) kademelerini kontrol edin:

   | Min Adet | Max Adet | Birim Fiyat | Indirim % |
   |----------|----------|-------------|-----------|
   | 1 | 9 | 320 USD | 0% |
   | 10 | 49 | 290 USD | 9.4% |
   | 50+ | - | 260 USD | 18.7% |

4. Musteri ozel fiyatlar sekmesini acin:
   - Anadolu Endustri &rarr; HW-FILT-001: 70 USD (%26.3 indirim)
   - Marmara HVAC &rarr; HW-SENS-001: 275 USD (%14.1 indirim)
5. Yeni kademe ekleme/duzenleme islemini test edin
6. Musteri ozel fiyat olusturma islemini test edin

---

## 15. Raporlar & Dashboard Builder

**Navigasyon:** Sol menu &rarr; Raporlar

**Beklenen Gorunum:**
- Rapor olusturucu: entity secimi, filtreleme, gruplama
- Kayitli raporlar listesi
- Dashboard duzenleyici (widget ekleme/cikarma)

**Test Adimlari:**
1. Rapor olusturucu formunu acin
2. Entity olarak "Opportunity" secin
3. Filtre ekleyin: stage = "proposal"
4. Gruplama: owner_id bazinda
5. Raporu calistirin ve sonuclari dogrulayin
6. Raporu "Teklif Asamasindaki Firsatlar" adiyla kaydedin
7. Kayitli raporlar listesinden tekrar acin
8. Dashboard duzenleyiciye gidin:
   - Yeni widget ekleyin (KPI karti, grafik)
   - Widget'lari surukle-birak ile yeniden konumlandirin

---

## 16. Playbook & Kocluk

**Navigasyon:** Sol menu &rarr; Playbook

**Beklenen Gorunum:**
- Playbook listesi
- Playbook detay: adimlar, kontrol listeleri, en iyi uygulamalar
- Kocluk genel bakis: temsilci performans ozeti

**Test Adimlari:**
1. Playbook listesinin yuklendigini dogrulayin
2. Varsa bir playbook detayini acin
3. Kocluk sekmesine girin
4. Temsilci bazinda performans metriklerini goruntuleyin
5. Kocluk notu ekleme islemini test edin

---

## 17. Engagement

**Navigasyon:** Sol menu &rarr; Engagement

**Beklenen Gorunum:**
- Transkriptler listesi
- Sekanslar (otomatik e-posta dizileri)
- Segmentler (musteri gruplamalari)

**Test Adimlari:**
1. Transkriptler sekmesini acin
2. Sekanslar sekmesinde mevcut dizileri goruntuleyin
3. Yeni sekans olusturma formunu test edin
4. Segment olusturma: filtre kriterleri belirleyin, kaydedin

---

## 18. Canli Sohbet

**Navigasyon:** Sag alt kosede chat widget'i + Sol menu &rarr; Canli Sohbet

**Beklenen Gorunum:**
- Chat widget: sag alt kosede yuvarlak ikon
- Agent chat sayfasi: aktif/kapali oturumlar listesi
- Otomatik yanitlar ayar sayfasi

**Test Adimlari:**
1. Sag alt kosedeki chat ikonuna tiklayin
2. Widget'in acildigini ve mesaj gonderme alaninin gorundugunu dogrulayin
3. "fiyat" yazarak otomatik yanit mekanizmasini test edin:
   - Beklenen otomatik yanit: "Fiyat bilgisi icin satis temsilciniz sizinle iletisime gececektir."
4. "stok" yazarak ikinci otomatik yaniti test edin:
   - Beklenen: "Stok durumu sorgunuz alinmistir. En kisa surede donecegiz."
5. Agent chat sayfasina gidin (admin/rep hesabi):
   - 2 oturum gorunmeli: visitor-001 (open), visitor-002 (closed)
   - visitor-001 oturumunda 3 mesaj olmali
6. Agent olarak yanitlama islemini test edin
7. Otomatik yanitlar ayar sayfasinda 3 kural goruntulenmeli

**Mock Veri:**

| Oturum | Durum | Mesaj Sayisi |
|--------|-------|-------------|
| visitor-001 | open | 3 (visitor, bot, agent) |
| visitor-002 | closed | 2 (visitor, bot) |

**Otomatik Yanit Kurallari:**

| Anahtar Kelime | Yanit |
|----------------|-------|
| fiyat | Fiyat bilgisi icin satis temsilciniz sizinle iletisime gececektir. |
| stok | Stok durumu sorgunuz alinmistir. En kisa surede donecegiz. |
| destek | Teknik destek talebiniz olusturuldu. Referans no: #AUTO |

---

## 19. Yonetim

**Navigasyon:** Sol menu &rarr; Ayarlar / Yonetim

### 19.1 Kullanici Yonetimi

**Test Adimlari:**
1. 3 kullanicinin listede gorundugunu dogrulayin
2. Rol ve yetki bilgilerini kontrol edin
3. Yeni kullanici olusturma formunu test edin
4. Manager hiyerarsisini dogrulayin (rep ve ops, admin'e baglidir)

### 19.2 Denetim Gunlugu (Audit Log)

**Test Adimlari:**
1. Aktivite loglarinin listelenmesini dogrulayin (20 kayit)
2. Filtreleme: entity_type, activity_type bazinda
3. Detay goruntuleme

### 19.3 Is Kurallari (Workflow Rules)

**Test Adimlari:**
1. 2 is kuralinin gorundugunu dogrulayin:
   - "Yuksek Deger Firsat Bildirimi": firsat tutari > 100K ise yoneticiye bildir
   - "Lead Skoru Yuksek Atama": lead skoru > 80 ise kidemli temsilciye ata
2. Kural detayini acin, kosullari ve aksiyonlari inceleyin
3. Gorsel akis olustarucu (flow builder) ile akisi goruntuleyin
4. Yeni kural olusturma formunu test edin

### 19.4 Ozel Alanlar (Custom Fields)

**Test Adimlari:**
1. Ozel alan yonetimi sayfasini acin
2. Yeni alan ekleme formunu test edin
3. Alan turlerini kontrol edin (text, number, date, dropdown, vb.)

### 19.5 Alan Izinleri (Field Permissions)

**Test Adimlari:**
1. Role gore alan gorunurluk ayarlarini kontrol edin
2. Okuma/yazma izinlerini test edin

### 19.6 Urun Kurallari (Product Rules)

**Test Adimlari:**
1. Urun kurallarinin listelenmesini dogrulayin
2. Yeni kural olusturma (uyumluluk, bagimlilik, dislanma)

### 19.7 Veri Kalitesi

**Test Adimlari:**
1. Veri kalitesi panelini acin
2. Eksik alan analizini kontrol edin
3. Duplicate tespitini test edin

### 19.8 Liderlik Tablosu

**Test Adimlari:**
1. Liderlik tablosunun gorundugunu dogrulayin
2. 3 basarinin listelenmesini kontrol edin:
   - Elif Kaya: "Ayin Satiscisi" + "100K Kulubu"
   - Ahmet Yilmaz: "Hiz Sampiyonu"
3. Siralama ve puanlama mantgini dogrulayin

---

## 20. Uyumluluk (KVKK)

**Navigasyon:** Sol menu &rarr; Uyumluluk

**Beklenen Gorunum:**
- KVKK uyumluluk paneli
- Veri saklama politikalari listesi
- Ihlal yonetimi formu

**Test Adimlari:**
1. Uyumluluk panelini acin
2. Musteri verileri uzerindeki KVKK onayi durumlarini kontrol edin
3. Veri saklama politikalarini goruntuleyin
4. Ihlal bildirimi olusturma formunu test edin
5. Veri silme talepleri bolumunu kontrol edin
6. Veri siniflandirma etiketlerini dogrulayin (public, internal, confidential, restricted)

---

## 21. Entegrasyonlar

**Navigasyon:** Sol menu &rarr; Entegrasyonlar

**Beklenen Gorunum:**
- Entegrasyon listesi (e-posta, takvim, ERP, vb.)
- Baglanti durumu gostergesi
- API key yonetimi

**Test Adimlari:**
1. Entegrasyon sayfasini acin
2. Mevcut entegrasyonlarin listesini goruntuleyin
3. Baglanti durumlarini kontrol edin
4. Yeni entegrasyon ekleme formunu test edin

---

## Kullanici Rolleri ve Yetkileri

| Ozellik | Admin (Satis Muduru) | Rep (Satis Temsilcisi) | Ops (Operasyon) |
|---------|-----|-----|-----|
| Dashboard | Tam | Kendi verileri | Operasyonel |
| Pipeline Yonetimi | Tam | Olusturma/Duzenleme | Salt okunur |
| Musteri Yonetimi | Tam | Olusturma/Duzenleme | Salt okunur |
| Teklif Olusturma | Tam | Kendi teklifleri | Salt okunur |
| Teklif Onaylama | Evet | Hayir | Hayir |
| Fatura Yonetimi | Tam | Goruntuleme | Olusturma/Duzenleme |
| Kampanya Yonetimi | Tam | Goruntuleme | Hayir |
| Sozlesme Yonetimi | Tam | Goruntuleme | Goruntuleme |
| Bolge Yonetimi | Tam | Kendi bolgesi | Hayir |
| Fiyatlama Ayarlari | Tam | Salt okunur | Hayir |
| Pipeline Ayarlari | Tam | Hayir | Hayir |
| Kullanici Yonetimi | Tam | Hayir | Hayir |
| Rapor Olusturma | Tam | Sinirli | Sinirli |
| AI Ozellikleri | Tam | Tam | Sinirli |
| KVKK Yonetimi | Tam | Goruntuleme | Hayir |
| Is Kurallari | Tam | Hayir | Hayir |

---

## Mock Veri Ozeti

| Varlik | Adet | Aciklama |
|--------|------|----------|
| Kullanicilar | 3 | admin, rep, ops |
| Musteriler | 10 | Turk sanayi sirketleri |
| Leads | 5 | Cesitli skorlar (20-85) |
| Yedek Parcalar | 20 | Vana, sensor, filtre, kontrolor vb. |
| Firsatlar | 5 | Farkli asamalarda |
| Teklifler | 15 | Cesitli durumlarda, 1-4 kalem |
| Faturalar | 5 | 5 farkli durumda |
| Kampanyalar | 3 | email, webinar, social |
| Kampanya Uyeleri | 15+ | Lead ve musteri karisik |
| Pipeline'lar | 3 | 4-7 asamali |
| Bolgeler | 5 | 2 seviyeli hiyerarsi |
| Sozlesmeler | 4 | draft, active, completed |
| E-Imzalar | 3 | signed, pending, expired |
| Fiyat Kademeleri | 9 | 3 urun icin 3'er kademe |
| Musteri Ozel Fiyat | 2 | 2 musteri icin ozel fiyat |
| Gelir Takvimleri | 2 | 6 ve 12 aylik |
| Chat Oturumlari | 2 | open ve closed |
| Chat Mesajlari | 5 | visitor, bot, agent |
| Otomatik Yanitlar | 3 | fiyat, stok, destek |
| E-posta Sablonlari | 3 | Teklif, takip, hosgeldiniz |
| Is Kurallari | 2 | Firsat ve lead kurallari |
| Yorumlar | 5 | Firsat ve musteri uzerinde |
| Basarilar | 3 | Ayin satiscisi, 100K kulubu, hiz sampiyonu |
| Asama Konfigurasyonlari | 6 | Prospecting'den closed'a |
| Aktivite Loglari | 20 | Cesitli islem tipleri |
| E-posta Istekleri | 8 | Yedek parca talepleri |
| Bildirimler | 5 | Cesitli tipler |

---

## Bilinen Sinirlamalar

1. **Backend API baglantisi gereklidir** — Frontend, backend API sunucusuna baglanamaz ise tum veriler bos goruntulenir. `docker-compose up` ile tum servisleri baslattiginizdan emin olun.

2. **AI ozellikleri Claude API key gerektirir** — AI icerik analizi, deal risk analizi ve AI e-posta taslagi ozellikleri icin gecerli bir `ANTHROPIC_API_KEY` ortam degiskeni tanimlanmalidir.

3. **Qdrant baglantisi RAG icin gereklidir** — Semantik arama ve AI bellek ozellikleri icin Qdrant vektor veritabani calisir durumda olmalidir.

4. **E-posta entegrasyonu mock modda** — Gercek e-posta gonderimi yapilmaz, tum e-posta islemleri veritabaninda kaydedilir.

5. **E-imza harici servise baglanmaz** — E-imza islemi simule edilir, gercek bir e-imza saglayicisina baglanmaz.

6. **PDF olusturma** — PDF indirme islemi backend'de wkhtmltopdf veya WeasyPrint gerektirebilir. Kurulu degilse PDF butonu calismayabilir.

7. **Chat widget** — WebSocket baglantisi gerektirir. WebSocket baglantisi kurulamazsa canli sohbet calismaz.

8. **Seed data sirasi** — Oncelikle `seed_demo_data.py`, ardindan `seed_uat_data.py` calistirilmalidir:
   ```bash
   cd backend
   source venv/bin/activate
   python -m scripts.seed_demo_data
   python -m scripts.seed_uat_data
   ```

9. **Tarayici uyumlulugu** — Chrome, Firefox ve Safari'nin guncel surumleri desteklenir. IE desteklenmez.

10. **Dil** — Arayuz dili Turkce, API yanitlari Ingilizce terimleri icerebilir.
