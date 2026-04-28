# V12 Multi-Tenant CRM — Rollout Runbook

V12 kapsamı:
- ``users``, ``customers``, ``opportunities``, ``quotes``, ``leads``
  tablolarına ``tenant_id`` kolonu (V8 migration ile eklendi)
- ``services/tenant_context.py`` helper'ları: ``scoped_for_user`` +
  ``assert_same_tenant`` + ``ensure_tenant``
- API tarafında: list endpoint'lerinde tenant scoping, detail/update/delete
  endpoint'lerinde cross-tenant 404 koruması, create endpoint'lerinde
  ``current_user.tenant_id`` propagation
- ``scripts/bootstrap_default_tenant.py`` — tenant satırı oluşturup
  NULL ``tenant_id`` rows'ları default tenant'a bağlar (idempotent)

V12'nin amacı tek-kiracılı kurulumları kırmadan **opt-in multi-tenant
moduna** geçirebilmek. ``user.tenant_id IS NULL`` iken helper'lar
no-op davranır → eski deploy'lar değişmeden çalışır.

---

## 0) Önkoşullar

- V8 migration uygulanmış olmalı (``20260427_v8_crm_tenant_id``)
- V12 migration head'inde olmalısın (``20260428_v12_transformer_seq``)
- ``manual-migrate.yml`` workflow'u çalıştırıldıysa zaten head'desin

```bash
# Render shell veya local'den prod'a karşı:
DATABASE_URL=<prod_url> python -m alembic current
# Beklenen: 20260428_v12_transformer_seq (head)
```

---

## 1) Default tenant bootstrap (multi-tenant'a geçiş)

İki yol var. **Üretimde GH Actions yolunu tercih et** — secret'lar
zaten orada, audit trail'de kalır.

### Yol A: GitHub Actions workflow (önerilen)

1. GitHub → Actions → "Bootstrap Default Tenant" → Run workflow
2. Inputs:
   - ``tenant_name``: "Honeywell TR" (veya kullanmak istediğin görünür ad)
   - ``tenant_region``: "TR" (opsiyonel)
   - ``plan_tier``: "standard"
   - ``confirm``: ``APPLY`` (boş bırakırsan dry-run)
3. Run workflow → Log'da:
   ```
   Tenant resolved: id=N name='Honeywell TR'
     users           NULL tenant_id rows: 4
     customers       NULL tenant_id rows: 12
     ...
   Backfilled 42 rows into tenant_id=N.
   ```

Workflow idempotent — yeniden çalıştırırsan no-op olur (``ensure_tenant``
mevcut tenant'ı reuse eder, NULL satır kalmadığı için UPDATE 0 row).

### Yol B: Render shell (manuel)

```bash
# Render dashboard → honeywell-backend → Shell
python -m scripts.bootstrap_default_tenant \
  --name "Honeywell TR" \
  --region TR \
  --plan-tier standard \
  --apply
```

Dry-run modu için ``--apply`` flag'ini omit et.

---

## 2) Doğrulama

Bootstrap sonrası DB'de:

```sql
-- Tenant satırı oluşmuş olmalı
SELECT id, name, region, plan_tier FROM tenants;

-- Hiç NULL kalmamalı
SELECT
  (SELECT COUNT(*) FROM users WHERE tenant_id IS NULL) AS users_null,
  (SELECT COUNT(*) FROM customers WHERE tenant_id IS NULL) AS customers_null,
  (SELECT COUNT(*) FROM opportunities WHERE tenant_id IS NULL) AS opps_null,
  (SELECT COUNT(*) FROM quotes WHERE tenant_id IS NULL) AS quotes_null,
  (SELECT COUNT(*) FROM leads WHERE tenant_id IS NULL) AS leads_null;
```

Hepsi 0 olmalı. Değilse: ya bootstrap çalıştırılmamış ya da yeni
satırlar tenant_id propagation eksik bir kod path'inden geldi
(seed script veya legacy import). O zaman:

```bash
# Kalanı süpür
DATABASE_URL=<prod> python -m scripts.bootstrap_default_tenant \
  --name "Honeywell TR" --apply
```

---

## 3) API davranışı doğrulama

İki kullanıcıyla canlı testle:

```bash
# Token A — tenant 1 kullanıcısı
TOKEN_A=$(curl -s -X POST $API/auth/login \
  -d '{"email":"a@t1.com","password":"..."}' | jq -r '.access_token')

# Token B — tenant 2 kullanıcısı
TOKEN_B=$(curl -s -X POST $API/auth/login \
  -d '{"email":"b@t2.com","password":"..."}' | jq -r '.access_token')

# A, kendi tenant'ını görmeli
curl -s -H "Authorization: Bearer $TOKEN_A" $API/opportunities/ | jq '.items | length'

# A, B'nin opp_id'sini probe etmeli — 404 dönmeli
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $TOKEN_A" $API/opportunities/<B_OPP_ID>
# Beklenen: 404 (NOT 403, NOT 200)
```

Test suite'inde aynı senaryolar otomatize: ``tests/test_v12_multi_tenant_e2e.py``.

---

## 4) Yeni tenant ekleme

Tek-kiracılıdan multi-kiracılıya geçtikten sonra ek tenant eklemek için:

```sql
INSERT INTO tenants (name, region, plan_tier, created_at)
VALUES ('Diğer Müşteri', 'TR', 'enterprise', now());
```

Sonra o tenant'a ait user'ları yarat (``users.tenant_id`` set edilmiş).
Yeni kayıtlar (POST opportunity/customer/lead/quote) otomatik o
tenant'a düşer çünkü create endpoint'leri ``current_user.tenant_id``
propagation yapıyor.

---

## 5) Geri alma (rollback)

V12 enforcement kapatmak için iki seçenek:

1. **Soft rollback** — tüm satırların ``tenant_id``'sini NULL'a çek:
   ```sql
   UPDATE users         SET tenant_id = NULL;
   UPDATE customers     SET tenant_id = NULL;
   UPDATE opportunities SET tenant_id = NULL;
   UPDATE quotes        SET tenant_id = NULL;
   UPDATE leads         SET tenant_id = NULL;
   ```
   Helper'lar otomatik no-op'a düşer, app tek-kiracılı modda çalışır.

2. **Hard rollback** — V8 migration'ını downgrade et:
   ```bash
   DATABASE_URL=<prod> python -m alembic downgrade 20260427_v8_text_embedding
   ```
   Bu kolonları siler — yeniden upgrade etmek gerekirse veri restore edilir.

---

## 6) Audit + observability

- ``tenants`` tablosundaki insert'ler ``audit_logs``'a düşmüyor.
  Bilinçli — bootstrap script tek seferlik op-tooling. Yeni tenant
  eklemelerini elle audit'e yazmak istersen ``log_action`` çağır.
- API erişim audit'inde ``user_id`` (dolayısıyla ``tenant_id``)
  zaten tutuluyor → cross-tenant probe denemesi log'larda
  ``status=404`` olarak görünür ve ``request_id`` ile filtre
  edilebilir.
- Cross-tenant 404 sayısının ani artışı = ID enumeration attack
  sinyali; oncall playbook'a alarm ekle (``rate(http_requests_total{status="404"}[5m]) > N``).

---

## 7) Bilinen sınırlamalar

- ``audit_logs`` tablosunda hâlâ tenant_id kolonu yok. Forensics
  için ``audit_logs`` ⨝ ``users`` join ile çıkarılıyor; doğrudan
  ``tenant_id`` filter'ı için P3 backlog'unda separate migration var.
- ``opportunities/timeline``, ``activity-summary``, ``deal-room``,
  ``comments`` gibi yan endpoint'lerin bir kısmı henüz
  ``assert_same_tenant`` çağırmıyor. Bunlar ``opp_id`` parametresi
  taşıyor ve parent endpoint korumalı olduğu için sızıntı düşük
  ama defensive layer henüz tam değil. P3'te tamamlanacak.
