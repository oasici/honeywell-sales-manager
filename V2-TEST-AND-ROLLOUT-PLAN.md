# Honeywell Sales Suite v2 — Test + Rollout Planı

Bu plan, v2’nin v1’i bozmadan kademeli olarak üretime alınması için test ve rollout stratejisini tanımlar.

## 1) Test piramidi

### 1.1 Backend (pytest)
Hedef: domain doğruluğu + RBAC + migration güvenliği.
- Opportunity CRUD
- Board aggregation (kanban columns)
- Timeline/event yazımı
- AI endpoints (rate limit + audit)
- Integrations adaptörleri (mock)

Örnek test dosyaları (öneri isimler):
- `backend/tests/test_opportunities_api.py`
- `backend/tests/test_board_kanban.py`
- `backend/tests/test_opportunity_timeline.py`
- `backend/tests/test_ai_summarize.py`
- `backend/tests/test_feature_flags.py`

### 1.2 Frontend (Vitest + RTL)
Hedef: kritik UI state ve erişim kontrolü.
- Board: column render + drag/drop (varsa)
- Opportunity 360: tabs + timeline render
- RoleGuard / RBAC: route block
- Error states: 403/401 handling

Örnek test dosyaları:
- `frontend/src/features/board/BoardPage.test.tsx`
- `frontend/src/features/opportunities/OpportunityDetailPage.test.tsx`
- `frontend/src/features/auth/RoleGuard.test.tsx`

### 1.3 E2E (Playwright)
Hedef: canlı ortamda gerçek akış.
Mevcut smoke yaklaşımını genişlet:
- Login 4 rol
- `/board` erişim (rol bazlı)
- Opportunity create → quote bağla → timeline’da görünür
- Reports ve manager-only sayfalar: rep/ops blok

## 2) Rollout stratejisi (feature-flag)

### 2.1 Flag’ler
Minimum:
- `FEATURE_V2_BOARD`
- `FEATURE_AI_SUMMARIES`
- `FEATURE_AI_PIPELINE_SUGGESTIONS`
- `FEATURE_INTEGRATIONS_*`
- `FEATURE_AI_AUTO_APPLY` (default false)

### 2.2 Kademeli açılım
1) **Dev/Staging**: tüm flag’ler açık (internal)
2) **Prod Canary**: yalnızca `sales_manager` + 1 rep için
3) **Prod Gradual**: %10 → %50 → %100 (kullanıcı/rol bazlı)

### 2.3 Geri dönüş (rollback) planı
- Flag kapat: yeni UI route’ları gizle/redirect
- DB additive olduğundan downgrade şart değil; ama gerekiyorsa migration rollback
- AI auto-apply kapatılınca suggestive modda devam eder

## 3) Observability / SLO
- API P95: board endpoints < 500ms
- UI: board load < 2s (P95)
- AI: latency/cost/timeout oranı; retry sayısı
- Entegrasyon sync: success rate + drift

## 4) CI/CD entegrasyonu
Mevcut:
- Playwright E2E Smoke workflow (Render) çalışıyor.

Öneri:
- PR check: “local backend mock + frontend e2e” (opsiyonel)
- Nightly: full E2E + report artifact

