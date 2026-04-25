# V4 hedef mimari — mevcut akışa dokunmadan hizalama planı

Bu doküman, paylaşılan **hedef tablo/servis/pipeline** ile bugünkü **V1 omurgası** (`activity_logs`, `opportunity_events`, `revenue_signals`, günlük feature store) arasında **çakışma olmadan** tüm hedefleri nasıl karşılayacağımızı tanımlar.

## Temel ilke: “tek gerçek yazım noktası” değişmez

- **Yazma (write path):** `log_activity()`, mevcut quote/email/task API’leri ve scheduler **davranışını değiştirmeyiz**. Yeni özellikler varsayılan **kapalı** feature flag ile gelir.
- **Okuma (read path):** Hedef şemaya yaklaşmak için önce **projeksiyon / görünüm / tüketici servis** ekleriz; gerektiğinde **gölge (shadow) tablolar** veya **materialized view** ile doldurulur — canonical kaynak yine V1 tablolarıdır.
- **Tek omurga hissi:** Uzun vadede `sales_events` hedefi, ya (A) **DB view** + uygulama projektörü ya da (B) **ayrı tablo + idempotent backfill job** ile sağlanır; ikisi de mevcut writer’ları **taşımadan** eklenebilir.

## Hedef → uygulama stratejisi (özet matris)

| Hedef bileşen | Mevcut karşılık (V1) | Additive strateji | Kırılım riski |
|-----------------|----------------------|-------------------|----------------|
| `sales_events` | `activity_logs` + `opportunity_events` | **Projeksiyon API** (`FEATURE_V4_ADDITIVE_READMODEL`) → isteğe bağlı `sales_events_shadow` + nightly sync | Düşük: sadece okuma / arka plan |
| `conversation_signals` | `revenue_signals` (+ kısmen `opportunity_signals`) | **Sinyal görünümü** projektörü; yeni çıktılar `emit_signal` ile aynı envelope | Düşük |
| `opportunity_features_daily` | Var | Kolonları **genişleten** migration’lar; builder’da **append-only** hesap blokları | Düşük (migration sırası) |
| `account_features_daily` / `rep_features_daily` | Var (MVP) | Eksik kolonları fazladan ekleyip builder’ı genişlet | Düşük |
| Deal momentum | `opportunity_features_daily` + sinyaller | İsteğe bağlı `momentum_history` **ayrı tablo** (writer değişmez) | Düşük |
| Buyer state | `buyer_state_history` | State setini genişletmek için **yeni enum değerleri** + skor matrisi (flag arkasında) | Orta (UI metinleri) |
| Decision gaps | `decision_gaps` / `stakeholder_roles` | Expected map’i segment/contact ile zenginleştir; **yeni kolonlar** nullable | Düşük |
| Network intelligence | `network_segments` / `segment_benchmarks_daily` (MVP) | Segment tanımını `industry|size|amount|product` anahtarına genişlet; **yeni satırlar** eski `stage:*` ile yan yana | Düşük |
| Sales DNA | Yok | Yeni tablolar + **sadece okuyan** miner job; writer’a dokunmaz | Düşük |
| Deal replay | Yok | `deal_replay_*` tabloları + feature store + event projeksiyonundan **türetilmiş** yazım | Düşük |
| Dynamic playbooks | V1 `playbooks` | DNA çıktısı → **yeni playbook versiyonu** önerisi (manuel onay kapısı) | Orta (ürün kararı) |
| Timing engine | Yok | `recommended_action_windows` tablosu + segment medyanlarından **read model** | Düşük |
| Objection intelligence | Kısmi sinyaller | `objections` + resolution tabloları; detection **async** | Orta |
| Rep DNA / similarity | Yok | `rep_features_daily` genişletme + embedding tablosu (flag) | Düşük |
| Federated benchmarks | Yok | Ayrı modül; tenant birleştirme **hiç** zorunlu değil | Yok |

## Fazlar (mevcut faz sıranızla uyumlu)

1. **Omurga hizası (read-only):** Birleşik zaman çizelgesi = `activity_logs` ∪ `opportunity_events` → hedef `sales_events` şekline map.
2. **Sinyal hizası:** `revenue_signals` → `conversation_signals` görünümü + isteğe bağlı olarak aynı timeline’da `signal:{type}` satırları (`include_signals`); ayrıca `GET .../conversation-signals`.
3. **Feature store genişlemesi:** Eksik kolonlar (velocity, objection ayrımı, …) nullable eklenir; nightly blokları fail-open.
4. **Learning katmanı:** DNA / replay tabloları; yalnızca okuma veya shadow write.
5. **Network katmanı:** Segment anahtarı zenginleştirme + anomaly (rolling z-score) ayrı job.
6. **Gelişmiş:** embedding, uplift — ayrı flag ve maliyet kontrolü.

## Bu repoda uygulanan somut adımlar (non-breaking)

- `FEATURE_V4_ADDITIVE_READMODEL`: kapalıyken endpoint’ler 404.
- Açıkken:
  - `GET /api/v1/v4/alignment/opportunities/{id}/normalized-timeline` — `activity_logs` ∪ `opportunity_events` ∪ isteğe bağlı `revenue_signals` (`include_signals`, varsayılan `true`).
  - `GET /api/v1/v4/alignment/opportunities/{id}/conversation-signals` — `revenue_signals` → hedef `conversation_signals` alt şeması (read-only).
- `FEATURE_V4_SALES_EVENTS_SHADOW` açıkken:
  - Tablo: `v4_sales_events_shadow` (Alembic: `20260427_v4_sales_events_shadow`).
  - Gecelik job: `v4_sales_events_shadow` (UTC 03:15) — dünün penceresi için idempotent insert.
  - `GET /api/v1/v4/alignment/opportunities/{id}/shadow-timeline` — materialize edilmiş satırlar.
  - `POST /api/v1/v4/alignment/shadow/sync-window` — body `{"days": N}` (1–365), **sales_manager / operations**; son N günü UTC’de rolling pencerede idempotent doldurur.
- `FEATURE_V4_ADDITIVE_READMODEL` açıkken birleşik sinyal okuma:
  - `GET .../conversation-signals` — `revenue_signals` + (varsayılan açık) `opportunity_signals`; `feed` alanı ile ayrışır; `include_legacy_opportunity_signals=false` ile sadece revenue.
  - `GET .../normalized-timeline?include_legacy_opportunity_signals=true` — legacy sinyalleri timeline’a ekler.
- `FEATURE_V4_DEAL_REPLAY` açıkken:
  - Tablo: `v4_deal_replay_snapshots` (Alembic: `20260428_v4_deal_replay_snapshots`).
  - `GET /api/v1/v4/replay/opportunities/{id}/snapshots` — tarih listesi (özet meta).
  - `GET /api/v1/v4/replay/opportunities/{id}/snapshots/{YYYY-MM-DD}` — tek anlık görüntü (`frames` + `meta`).
  - `POST /api/v1/v4/replay/opportunities/{id}/materialize` — additive timeline’dan idempotent upsert (**sales_manager / operations**).
- `FEATURE_V4_SALES_DNA` açıkken:
  - Tablo: `v4_sales_dna_snapshots` (Alembic: `20260429_v4_sales_dna_snapshots`).
  - Miner (salt okuma): `opportunity_features_daily` + son 30g `activity_logs` / `opportunity_events` / `revenue_signals` + `buyer_state_history` (≤ snapshot günü).
  - `GET /api/v1/v4/dna/opportunities/{id}/snapshots` — özet liste.
  - `GET /api/v1/v4/dna/opportunities/{id}/latest` — son kayıtlı snapshot (`traits` + `meta`).
  - `GET /api/v1/v4/dna/opportunities/{id}/snapshots/{YYYY-MM-DD}` — tek gün.
  - `POST /api/v1/v4/dna/opportunities/{id}/materialize` — idempotent upsert (**sales_manager / operations**).

- Gecelik scheduler (UTC): `v4_sales_dna_nightly` (04:05, `FEATURE_V4_SALES_DNA`), `v4_deal_replay_nightly` (04:35, `FEATURE_V4_DEAL_REPLAY`); kota `V4_SALES_DNA_NIGHTLY_MAX_OPPORTUNITIES` / `V4_DEAL_REPLAY_NIGHTLY_MAX_OPPORTUNITIES`; hedef gün **dün (UTC)**; aday: aktif fırsatlar + dün `opportunity_features_daily` veya son 7g aktivite.

Sonraki PR’lar için sıra: isteğe bağlı `opportunity_signals` → `revenue_signals` migrasyonu (ürün kararı); playbook önerisi kapısı; nightly aday seçimini segment/pipeline ile genişletme.

## İlgili doküman

- `docs/v4-on-v1-blueprint.md` — canonical omurga kararları ve MVP eşlemesi.
