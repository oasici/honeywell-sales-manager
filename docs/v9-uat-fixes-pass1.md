# V9 UAT Fixes — Pass 1 (2026-04-28)

34 maddelik UAT review için bu turda yapılanlar + sıradakiler.

---

## ✅ Pass 1'de tamamlananlar

### Quick UI removals
- **Item 26** — Yazı boyutu büyüt/küçült feature'ı `SettingsPage` Display Settings bölümünden kaldırıldı. State + i18n key + lucide icon importları temizlendi.
- **Item 4 (kısmi)** — `OpportunityDetailPage`'deki "V4 Günlük Snapshot" başlığı "Günlük Snapshot" olarak güncellendi.
- **Item 24 (kısmi)** — Sequences sayfasındaki "Dizi Analitiği (V2)" → "Dizi Analitiği" (i18n key güncellendi).

### Massive seed extension (`scripts/seed_v9_uat_extension.py`)
Bu pass'te yeni script eklendi; `seed_v8_full_demo.py`'nin üstüne run edilir:

```bash
python -m scripts.seed_v8_full_demo --apply
python -m scripts.seed_v9_uat_extension --apply
```

**Eklenen entity'ler** (UAT madde referanslarıyla):

| Entity | Adet | UAT madde |
|---|---|---|
| `ApprovalRule` | 6 (yüksek indirim, büyük tutar, VIP, marj altı, sözleşme uzatma, kritik fırsat) | #12, #13 |
| `ApprovalRequest` | 20 (mix: pending/approved/rejected) | #12 |
| `Invoice` | 40 (8 overdue + 10 paid + 8 sent + 8 draft + 6 partial) | #9 |
| `KeywordPack` | 8 (fiyat, rakip, pozitif, erteleme, procurement, güvenlik, entegrasyon, yetki) | #23 |
| `Segment` | 8 (VIP, kayıp riski, yeni, üretim, EMEA, mid-market, enterprise, HVAC) | #25 |
| `CustomField` | 10 + 90 değer (lead_source, competitor, decision_timeline, vb.) | #29 |
| `FieldPermission` | 12 (rep/operations/manager × 4 entity) | #30 |
| `ProductRule` | 6 (min_quantity, discount_cap, approval_required, bundle_suggest, lead_time_warning) | #31 |
| `WorkflowRule` (extras) | 6 (Slack bildirim, doğum günü, pipeline sıkışma, lead atama, fatura, sözleşme bitiş) | #32 |
| `Territory` + assignments | 6 + 12 (Marmara, Ege, İç Anadolu, Akdeniz, EMEA, Karadeniz) | #33 |
| `ProductBundle` | 4 (HVAC starter, otomasyon, yangın güvenlik, bakım kit) | #14 |
| `RetentionPolicy` | 6 (customer 5y, opp 3y, activity 2y, email 3y, quote 7y, contract 10y) | #28 |
| `BreachNotification` | 3 (yetkisiz export, 3rd party şifre, phishing) | #28 |
| `CoachingPlan` | 5 + 32 snapshot (1 düşük performans senaryolu rep) | #21 |
| `ForecastAdjustment` | 10 | #6 |
| `PipelineSnapshot` | 48 (8 hafta × 6 stage) | #6 |
| `ForecastSnapshotDetail` | 60 | #6 |
| `Transcript` | 6 (discovery, demo, negotiation, renewal, stakeholder, loss review) | #22 |
| `RevenueSignal` (high_intent) | 8 müşteri için | #3, #16 |
| `Notification` (extras) | 16 unread (4 tip × 4 kullanıcı) | #34 |

**Test**: Fresh SQLite DB üzerinde end-to-end başarılı, tüm `INFO` log'lar yeşil.

---

## ⏸ Pass 2'ye ertelenenler

Bu turda yapılmadı, kapsamlı frontend çalışması gerektiriyor:

### i18n EN→TR (frontend string-by-string)

| UAT madde | Açıklama | Etkilenen dosya/lokasyon |
|---|---|---|
| #2 | Temsilci koçluk skor risk label'ları İngilizce + renk-risk uyumu | `CoachingRepPage` veya `Coaching` panel — risk badge component |
| #3 | "Standard Sales", "Quick Sales" İngilizce | Pipeline stage display — i18n key gerekli |
| #4 (genişletilmiş) | "Negotiation" stage adı, pipeline öneri adımları, fırsat sağlığı göstergeleri, AI risk faktörleri, kapanma olasılığı sonraki adımlar — hepsi İngilizce | `OpportunityDetailPage` çoklu section + `pipelineApi`/`riskApi` response'ları (backend Türkçe label döndürmeli) |
| #13 | Yeni onay kuralı modal text İngilizce | `ApprovalRulesPage` modal |
| #15 | Müşteri sağlık skoru altı, etkileşim skoru, son temas, risk özeti, kayıp risk analizi — hepsi İngilizce | `CustomerDetailPage` + `customer_health_service` response'ları |
| #17 | AI Asistan sayfasındaki sekmeler İngilizce | `AIAssistantPage` tab labels |
| #20 | Playbook kart verileri + label'lar İngilizce | `PlaybookListPage` + `PlaybookDetailPage` |
| #27 | Pipeline ayarları sayfası kart bilgileri İngilizce | `PipelineSettingsPage` |
| #33 | Bölge yönetimi kartları İngilizce | `TerritoriesPage` |

**Yaklaşım**: Her sayfayı tek tek aç, hardcoded English string bul, `lib/i18n.ts`'e TR çevirisi ekle, `t('key')` ile değiştir. Tahmini: ~2-3 saat tek seferde, yoğun ve dikkat gerektiriyor.

### UI behavior fixes

| UAT madde | İhtiyaç | Karmaşıklık |
|---|---|---|
| #27 | Pipeline key kutusunda dropdown (mevcut text input → Select) | Orta — kullanılabilir key listesi backend'den çekilmeli |
| #28 | Uyumluluk → Müşteri ID input'u customer Select'e dönüştür + Saklama Politikaları/İhlal Bildirimleri için tab UI | Orta — `CompliancePage` tab ekle, RetentionPolicy/BreachNotification render |
| #24 | Hazır sekans şablonuna tıklandığında `SequenceBuilderPage`'e template verisi ile yönlen | Orta — query param ile geçiş, builder default state'i template'ten doldur |
| #34 | Bildirim butonu açıldığında "boş" gösterimi inconsistent (seed'de 16 unread var ama UI'da görünmüyor olabilir) | Düşük — fetch endpoint'i yanlış filter çekiyor olabilir |

### Item 2 risk label colors (özel inceleme)

UAT'ta belirtildi: "risk labelları İngilizce ve label renkleri risk sıralamasına uygun gözükmüyor".

İki ayrı sorun:
1. Label dili (i18n): yukarıdaki #2 i18n batch'inde
2. Renk semantiği: low=green, med=amber, high=red, critical=dark-red sıralaması frontend'te yanlış olabilir → `Badge` component'inin variant mapping'i kontrol edilmeli

---

## Pass 2 önerilen sıra

1. i18n critical batch (#2 dahil 9 madde) — en yüksek görünür etki
2. Risk label colors (#2) — Badge component fix
3. UI behavior: #34 (notification fetch), #28 (customer select + tabs), #27 (key dropdown), #24 (template flow)
4. Re-run seed + validation
5. Commit + push + v1.4.0 release

---

## Kullanım talimatı (UAT için seed yenileme)

Sandbox / staging DB'yi sıfırlayıp seed'i tazelemek için:

```bash
# Backend dizininde
cd backend && source venv/bin/activate
export DATABASE_URL="postgresql+asyncpg://..."  # production DB

# Önce migration'lar
alembic upgrade head

# Sonra seed
python -m scripts.seed_v8_full_demo --apply
python -m scripts.seed_v9_uat_extension --apply
```

Her iki script idempotent — re-run güvenli.
