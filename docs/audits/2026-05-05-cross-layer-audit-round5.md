# Cross-Layer Audit Report — Honeywell Sales Suite (Round 5, post-v1.9.15)

**Date:** 2026-05-05
**Branch:** `deploy/render-sandbox`
**HEAD:** `977ef82` (post v1.9.15 — round-4's 84 findings shipped over v1.9.0..v1.9.15)
**Scope:** DB schemas/migrations · Backend models/services · API contracts · Frontend clients/types · UI rendering · Realtime/events · Permissions/flags · State/lifecycle/cache
**Method:** 6 parallel layer-focused investigators (DB↔ORM, Backend↔API, API↔Frontend, UI completeness, Realtime/cache/state, Permissions/flags). Every headline claim re-verified against source via `grep` + `Read` before being included here.

---

## 1. Executive Summary

| Metric | Count |
|---|---:|
| **Total verified findings** | **96** |
| Critical | 14 |
| High | 39 |
| Medium | 32 |
| Low | 11 |

### Top headline issues — single hotfix PR before anything else

1. **R5-FAKE-1** — `AtRiskPage` "Risk Altındaki Gelir" KPI is `opps.length × 100,000 TRY` ([AtRiskPage.tsx:141](../../frontend/src/features/board/AtRiskPage.tsx#L141)). Fully fabricated — no relation to any opportunity amount. Sales managers see a TRY value that lands in screenshots / weekly exec reports as a real risk number. **Manager-facing data-credibility incident.**
2. **R5-FAKE-2 / R5-PLAY-1** — `PlaybookAnalyticsPage` win-rate displayed 100× too large. Backend already returns 0–100 (`round(won_with / total_with * 100, 1)` at [playbooks.py:219](../../backend/app/api/v1/playbooks.py#L219)); frontend re-multiplies by 100 (`(rate * 100).toFixed(1)` at [PlaybookAnalyticsPage.tsx:31](../../frontend/src/features/playbooks/PlaybookAnalyticsPage.tsx#L31)) → "77.0%" reads as **"7700.0%"**.
3. **R5-PERM-1** — Field-permission masking is **dead code for 4 of 9 registered entity types** (`contract`, `invoice`, `subscription`, `campaign`). Admins configure rules at `/admin/field-permissions`; rules are never enforced for these entities. The same admin-theater shape that round-4's R4-PERM-1 closed for the other five entity types has reappeared on the round-4-shipped Invoice/Contract/Subscription/Campaign features.
4. **R5-TEN-25** — `integrations.py` calendar-link-meeting (line 272) and esign-request-stub (line 540) load `Opportunity` / `Quote` by ID with **zero `assert_same_tenant`**. Manager in tenant A injects events into tenant B's deal timeline.
5. **R5-TEN-26** — Six routers regress on the round-4 tenant-scoping pattern: `pipelines.py` (4 endpoints), `stakeholders.py` (2), `dashboard_builder.py`, `feature_store.py`, `deal_rooms.py` (4), `admin_dead_letters.py` (which additionally ships with only `get_current_user` — no role gate at all).
6. **R5-PII-4** — `GET /api/v1/settings/` returns ALL `Setting` rows in plaintext, masking only `email_password`. Per-provider esign webhook secrets and any DB-stored secret round-trip in cleartext to the SPA. Combined with R5-PII-5 (esign webhook secret stored unencrypted), an attacker with a stolen manager token can forge esign webhook callbacks marking arbitrary documents signed.
7. **R5-FORM-3 / R5-FORM-4** — Customer create + update forms send `website` + `linkedin_url` ([CustomerListPage.tsx:283-296](../../frontend/src/features/customers/CustomerListPage.tsx#L283), [CustomerDetailPage.tsx:244](../../frontend/src/features/customers/CustomerDetailPage.tsx#L244)) but `CustomerCreate`/`CustomerUpdate` schemas omit them ([customer.py:8-25](../../backend/app/schemas/customer.py#L8)). Pydantic silently drops the keys, toast says "success", values disappear.
8. **R5-RENDER-INVOICE-1** — `_invoice_to_dict` ([invoices.py:86](../../backend/app/api/v1/invoices.py#L86)) never includes a `customer` object, but TS declares `Invoice.customer?: { id, name, company }` ([types.ts:1842](../../frontend/src/lib/types.ts#L1842)) and three pages dereference it. Every invoice list row falls back to `#${customer_id}`; every detail-page header reads "for ".
9. **R5-FLAG-15** — `contracts.py` and `subscriptions.py` have **no backend feature-flag gate**. Frontend has **no `<FeatureFlagGate>`** either. Both pages are always live regardless of FEATURE_INVOICING / FEATURE_REV_REC cousins.
10. **R5-CACHE-1 / HIGH-1** — `authStore.logout()` ([authStore.ts:123](../../frontend/src/stores/authStore.ts#L123)) clears localStorage + Zustand state but **never calls `queryClient.clear()`**. Combined with `staleTime: 30_000` ([main.tsx:19](../../frontend/src/main.tsx#L19)), the next user logging in on the same browser tab sees the previous user's PII for 30s+. **PII leak on shared devices** (BYO laptop / shared kiosks / training environments).
11. **R5-EVENT-1 / HIGH-2** — KVKK retention scheduler ([scheduler.py:455-509](../../backend/app/tasks/scheduler.py#L455)) selects overdue customers globally and notifies *every active sales_manager across every tenant* with the **global aggregate count**. Manager in tenant A learns tenant B has overdue records.
12. **R5-EVENT-2 / HIGH-3** — `lead.score_changed` payload contains `old_score`, `new_score`, `reason` ([lead_service.py:118](../../backend/app/services/lead_service.py#L118)) — no `delta`. Frontend `score-history` UI reads `payload?.delta` ([LeadDetailPage.tsx:71](../../frontend/src/features/leads/LeadDetailPage.tsx#L71)), so every score-history row shows red `TrendingDown` icon and "0" delta value, even after a positive rescore.

### Most-affected surfaces

- **Multi-tenant isolation regressions** (8 critical+high findings) — round-4 closed 16 modules; round-5 finds 8 net-new endpoints across `integrations`, `pipelines`, `stakeholders`, `dashboard_builder`, `feature_store`, `deal_rooms`, `admin_dead_letters`. Pattern is recurring because there is no automated test that scans every router for `select(Model).where(Model.id == X)` without a follow-on `assert_same_tenant`.
- **Field-permission masking coverage gaps** (4 entities × ~4 endpoints each) — round-4's `apply_request_perms` was wired only on customer/quote/opp/lead/email; the new round-4 modules (contract/invoice/subscription/campaign) shipped without it.
- **Pagination envelope drift** (11 endpoints) — round-4 standardized `{items,total,page,page_size,pages}` for the largest endpoints; eleven smaller ones still return `{contracts:[]}`, `{schedules:[]}`, `{breaches:[]}`, `{policies:[]}`, `{data:[]}`, `{emails:[]}`, `{count, page, page_size, data}`, or bare `list[str]`.
- **DTO regressions / TS type drift** (20 findings) — `User.tenant_id` not surfaced in any of the three `_user_to_dict` copies; `EmailRequest.tenant_id` / `is_duplicate` / `duplicate_of_id` missing; `Quote.revision_no` / `superseded_by` missing (V9 revision tree unusable from UI); `SparePart.min_margin_pct` invisible end-to-end; phantom `customer` on Invoice TS type; phantom `Quote.customer` typed as full Customer but only 4 fields returned; same pattern for `QuoteItem.spare_part`; `PlaybookAnalytics.win_rate_*` and `avg_completion_days` typed as required but nullable on backend.
- **UI completeness gaps** (16 high) — kanban card hides 9 fields the API returns (source, forecast_category, loss_reason, previous_*, probability, pipeline_id, territory_id); contract/invoice/subscription lists have **no customer column**; opportunity detail never renders `source` or revenue-leak diff fields.
- **Form completeness gaps** (7 forms) — Lead create has no `notes`; Lead detail has no inline edit; Customer enrichment fields aren't editable; Quote `valid_days` not editable; Subscription `end_date`/`quote_id` not on create form.
- **Frontend feature-flag gating** (10 routes) — `<FeatureFlagGate>` component shipped in round-4 (R4-FLAG-1) but 10 routes the backend gates with `FEATURE_*` are still rendered unconditionally in the SPA, producing the click → 403 → blank page pattern.
- **Cache hygiene** (5 mutations) — `pdfMutation`, `saveMutation` (report builder), `createCustomer`, `rescore`, etc. either skip `invalidateQueries` or use ad-hoc invalidation instead of the round-4 `cacheInvalidation.ts` helper (~50% adoption).

### What round-4 closed that stayed closed

Verified via spot-checks: R4-TEN-1..24 fixes on the 16 originally-flagged modules hold; `apply_request_perms` is wired on the 5 originally-flagged routers; bootstrap migration runs from empty schema clean (CI green); webhook HMAC + dead-letter store + Fernet encryption for calendar/esign config still active. **Zero regressions on round-4 fixes themselves** — the new findings all live in shipped-during-round-4 surfaces (Invoice/Contract/Subscription/Campaign) or net-new shapes that didn't exist when round-4 ran.

---

## 2. Findings by Category

### 2.1 Multi-tenant security — CRITICAL × 3, HIGH × 5

#### R5-TEN-25 — `integrations.py` cross-tenant Opportunity / Quote linking — **CRITICAL**
- **Files:** [backend/app/api/v1/integrations.py:272](../../backend/app/api/v1/integrations.py#L272), [:540](../../backend/app/api/v1/integrations.py#L540).
- **Evidence:** Both load by ID with no tenant check:
  ```python
  opp = (await db.execute(select(Opportunity).where(Opportunity.id == body.opportunity_id))).scalar_one_or_none()
  ```
- **Attack:** Manager in tenant A POSTs `{"opportunity_id": <tenant_B_opp_id>, "event_title": "Pricing intel", "notes": "..."}` to `/integrations/calendar/link-meeting` → an `OpportunityEvent` is injected into tenant B's deal timeline. Same shape on `/integrations/esign/request` (Quote).
- **Fix:** `assert_same_tenant(opp, current_user, exception_cls=NotFoundException)` after each load.
- **Migration needed:** No.
- **Tests:** Add `tests/test_integrations_tenant.py` with cross-tenant opp/quote attempt → expect 404.

#### R5-TEN-26 — Six routers do bare `.where(.id == X)` lookups — **CRITICAL**
- **Files (line numbers):**
  | File | Lines | Model |
  |---|---|---|
  | [backend/app/api/v1/pipelines.py](../../backend/app/api/v1/pipelines.py) | 110, 126, 157, 179 | `Pipeline` (4 endpoints) |
  | [backend/app/api/v1/stakeholders.py](../../backend/app/api/v1/stakeholders.py) | 158, 188 | `Stakeholder` |
  | [backend/app/api/v1/dashboard_builder.py](../../backend/app/api/v1/dashboard_builder.py) | 219 | `DashboardConfig` (only `owner_id` checked, no tenant) |
  | [backend/app/api/v1/feature_store.py](../../backend/app/api/v1/feature_store.py) | 54 | `OpportunityFeaturesDaily` (no opp-tenant check) |
  | [backend/app/api/v1/deal_rooms.py](../../backend/app/api/v1/deal_rooms.py) | 108, 124, 140, 154 | `DealRoom` |
  | [backend/app/api/v1/admin_dead_letters.py](../../backend/app/api/v1/admin_dead_letters.py) | 100, 142 | `DeadLetterEvent` |
- **Fix:** `assert_same_tenant(...)` after each lookup; for `admin_dead_letters.py`, also escalate dependency from `get_current_user` to `require_role(SALES_MANAGER, OPERATIONS)` — see R5-TEN-27.
- **Tests:** Extend the `test_*_tenant.py` pattern to each router.

#### R5-TEN-27 — `admin_dead_letters.py` requires only `get_current_user` — **HIGH**
- **File:** [backend/app/api/v1/admin_dead_letters.py](../../backend/app/api/v1/admin_dead_letters.py) — every endpoint depends on `Depends(get_current_user)` not `require_role`.
- **Risk:** Sales rep can list every tenant's dead-letter event payloads (raw event JSON likely contains PII).
- **Fix:** `require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS)`.

#### R5-TEN-28 — `BreachNotification` and `ReportFolder` models lack `tenant_id` — **HIGH**
- **Files:** model definitions for both. `BreachNotification` is reachable via `compliance.py:717` (returns `{breaches:[]}` unbounded — see also R5-API-8 below). `ReportFolder` ([reports_v2.py:128](../../backend/app/api/v1/reports_v2.py#L128)) is shared across tenants when `is_shared=True`.
- **Risk:** Compliance officer in tenant A lists tenant B's breaches; report folder marked `is_shared` in tenant A is visible from tenant B.
- **Fix:** Migration adds `tenant_id` column + backfill from owner→tenant lookup; serializers add `assert_same_tenant`/`scoped_for_user`.
- **Migration:** `20260505_add_tenant_id_to_breach_and_folder.py`. Backfill via `UPDATE breach_notifications b SET tenant_id = (SELECT tenant_id FROM customers WHERE id = b.customer_id)` (and analogous for folders via owner→user→tenant). Risk: rows with NULL customer_id need a default tenant.

### 2.2 Permissions / Field-masking / Flags — CRITICAL × 2, HIGH × 5, MEDIUM × 4

#### R5-PERM-1 — Field-permission masking missing on contract / invoice / subscription / campaign — **CRITICAL**
- **Files:**
  - Registered: [backend/app/services/field_permission_service.py:18-29](../../backend/app/services/field_permission_service.py#L18) — `VALID_ENTITY_TYPES` includes all 4.
  - Wired: [customers.py:989](../../backend/app/api/v1/customers.py#L989), [quotes.py:796](../../backend/app/api/v1/quotes.py#L796), [opportunities.py:179](../../backend/app/api/v1/opportunities.py#L179), [leads.py:597](../../backend/app/api/v1/leads.py#L597), [emails.py:852](../../backend/app/api/v1/emails.py#L852).
  - **Not wired** (verified via `grep apply_request_perms` returns zero): [contracts.py:51-79](../../backend/app/api/v1/contracts.py#L51), [invoices.py:86-111](../../backend/app/api/v1/invoices.py#L86), [subscriptions.py:29-49](../../backend/app/api/v1/subscriptions.py#L29), [campaigns.py:67](../../backend/app/api/v1/campaigns.py#L67).
- **Fix:** Append `return apply_request_perms(data, "contract")` (etc) to each serializer. Add a regression test that fakes a `mask` perm and asserts the output dict masks the field.

#### R5-PERM-2 — `dependencies.py` always prefetches field perms even when flag is OFF — **HIGH**
- **File:** [backend/app/core/dependencies.py:74-85](../../backend/app/core/dependencies.py#L74).
- **Cost:** ~5 ms per authenticated request on cold cache.
- **Fix:** Short-circuit when `not settings.FEATURE_FIELD_PERMISSIONS`.

#### R5-PERM-5 — `quotes.py` ownership check excludes OPERATIONS role — **MEDIUM**
- **Files:** [quotes.py:44, 94, 253, 346, 464, 522, 578, 671](../../backend/app/api/v1/quotes.py#L44).
- **Bug:** `if current_user.role != UserRole.SALES_MANAGER.value and quote.created_by != current_user.id:` — OPERATIONS user (back-office persona) gets 403 on every quote they didn't create. Sidebar shows the link.
- **Fix:** Treat OPERATIONS as elevated.

#### R5-FLAG-15 — Contracts and Subscriptions have no flag gate at either layer — **CRITICAL**
- **Files:**
  - [backend/app/api/v1/contracts.py](../../backend/app/api/v1/contracts.py) — no `_require_*` dependency.
  - [backend/app/api/v1/subscriptions.py](../../backend/app/api/v1/subscriptions.py) — same.
  - [frontend/src/app/App.tsx:921, 931, 827, 837](../../frontend/src/app/App.tsx#L921) — routes rendered without `<FeatureFlagGate>`.
- **Risk:** Customer A signs an MSA stating "no Contracts module enabled". Operator never sets a flag. Sales rep navigates to `/contracts` and creates contract rows for Customer B. Audit later finds Contract records that were never approved as a contracted feature.
- **Fix:** Add `FEATURE_CONTRACTS` and `FEATURE_SUBSCRIPTIONS` to settings (default `False`); `_require_contracts` / `_require_subscriptions` dependencies; wrap UI routes with `<FeatureFlagGate>`; add to `_PUBLIC_FEATURE_FLAGS` allow-list.

#### R5-FLAG-16 — 10 backend-flagged routes the frontend renders unconditionally — **HIGH**
| Route | Backend flag | Backend file |
|---|---|---|
| `approvals`, `approvals/rules` | `FEATURE_APPROVAL_ROUTING` | `approvals.py:54` |
| `engagement/sequences*` | `FEATURE_SEQUENCES_V2` | router gate |
| `admin/territories` | `FEATURE_TERRITORIES` | `territories.py` |
| `admin/workflow-rules*` | `FEATURE_WORKFLOW_RULES` | `workflow_rules.py:24` |
| `admin/product-rules` | `FEATURE_PRODUCT_RULES` | `product_rules.py:21` |
| `admin/custom-fields` | `FEATURE_CUSTOM_FIELDS` | `custom_fields.py:24` |
| `admin/chat` | `FEATURE_LIVE_CHAT` | `chat.py:_require_live_chat` |
| `settings/pipelines` | `FEATURE_MULTI_PIPELINE` | `pipelines.py:26` |
| `subscriptions*` | (R5-FLAG-15) | — |
- **Fix:** Wrap each `<Route>` with `<FeatureFlagGate>` and gate the corresponding sidebar `NavLink`.

#### R5-FLAG-17 — Symmetry not enforced; `<FeatureFlagGate>` is advisory-only — **HIGH**
- **Risk:** Any flag the SPA wraps without a backend `_require_*` is bypassable via direct API call. Add a CI assertion (`tests/test_flag_symmetry.py`) iterating `_PUBLIC_FEATURE_FLAGS` × backend router import-time deps.

#### R5-PII-4 — `GET /settings/` leaks all DB-stored secrets in cleartext — **CRITICAL**
- **File:** [backend/app/api/v1/settings.py:103-118](../../backend/app/api/v1/settings.py#L103).
- **Code:** `settings_dict = {s.key: s.value for s in settings}` — only `email_password` masked.
- **Risk:** A tenant with `esign_docusign_webhook_secret` configured exposes the HMAC signing secret. The secret can then forge esign callbacks (`POST /integrations/esign/webhook`) marking arbitrary documents as signed.
- **Fix:** `_SENSITIVE_KEY_PATTERNS = {"password", "secret", "_token", "api_key", "_key"}`; redact in GET, encrypt in PUT.

#### R5-PII-5 — Esign webhook secret stored unencrypted (companion to R5-PII-4) — **HIGH**
- **File:** [backend/app/api/v1/integrations.py:597-602](../../backend/app/api/v1/integrations.py#L597).
- **Fix:** Use existing `encrypt_str` / `decrypt_str` helpers (added in round-4); single read site to update.

#### R5-RL-7 — `POST /signatures/sign/{token}` (public) has no rate-limit — **HIGH**
- **File:** [backend/app/api/v1/signatures.py:358, 401, 447](../../backend/app/api/v1/signatures.py#L358).
- **Exploit:** Token is `secrets.token_urlsafe()` of finite length. Iteration bounded only by network → forge signatures.
- **Fix:** New `enforce_signing_rate_limit` bucket (5/minute per IP) on all three `/sign/*` endpoints; log failed-token attempts.

#### R5-RL-8 — `coaching`, `v5_intelligence`, `v6_intelligence`, `guided_selling` lack AI rate-limit — **HIGH**
- **Evidence:** [ai.py:60-69](../../backend/app/api/v1/ai.py#L60) installs `enforce_tenant_ai_rate_limit` + `enforce_ai_rate_limit` at the router level. The 4 listed AI-touching routers do not.
- **Fix:** Lift the same dependencies to each router's `APIRouter(...)`.

#### R5-RL-9 — `/audit/export` and `/compliance/breach/*` flag-gated but no per-tenant cap — **MEDIUM**
- **Fix:** Layer `enforce_tenant_kvkk_rate_limit` analogous to the tenant_ai pattern.

#### R5-PERM-3 — Inline role checks proliferate (65+ sites) — **HIGH**
- **Files:** `cockpit.py:52, 74, 165, ...`; `compliance.py:201, 387, 427, 475` mixed with `require_role`.
- **Risk:** Adding a new role means combing every inline check. Easy to miss → authz hole.
- **Fix:** Use `is_manager(user)` / `can_view_team(user, opp)` helpers in `app/services/access_service.py` (already exists). Replace gradually.

#### R5-ROLE-3 — Sidebar references non-existent `'admin'` role — **HIGH**
- **File:** [frontend/src/components/layout/Sidebar.tsx:76](../../frontend/src/components/layout/Sidebar.tsx#L76) — `roles: ['sales_manager', 'admin']`. Valid roles: only `sales_rep, sales_manager, operations`.
- **Impact:** Operations users (legitimate parts-intel consumers) never see the link; backend has no role gate, so any rep with API token bypasses the SPA gate.
- **Fix:** Replace `'admin'` with `'operations'`; add backend role gate on `v10_parts_intel.py`.

#### R5-FLAG-18, R5-FLAG-19, R5-FLAG-20, R5-PERM-4, R5-PERM-6, R5-PERM-7
See full slice 6 for medium/low details; these are coverage hygiene (`FEATURE_TRANSFORMER_SEQ_EMBEDDING` exposed without SPA action; `FEATURE_INVOICE_PAID_EVENT` hidden from SPA but driving event emission; manager-CSV-import allows escalation to manager role).

### 2.3 DTO / API contract drift — CRITICAL × 1, HIGH × 6, MEDIUM × 12

#### R5-API-1 — `_invoice_to_dict` never returns `customer` object but TS asserts it — **CRITICAL**
- **Files:** [backend/app/api/v1/invoices.py:86-111](../../backend/app/api/v1/invoices.py#L86) (no `customer` key), [frontend/src/lib/types.ts:1842](../../frontend/src/lib/types.ts#L1842) (`customer?: { id, name, company }`), [InvoiceListPage.tsx:329](../../frontend/src/features/invoices/InvoiceListPage.tsx#L329) (renders `invoice.customer?.name ?? '#'+customer_id`), [InvoiceDetailPage.tsx:138](../../frontend/src/features/invoices/InvoiceDetailPage.tsx#L138) (subtitle "for ").
- **Fix:** Either add `relationship("Customer", lazy="selectin")` to Invoice and emit `{id, name, company}` in serializer, or remove the phantom field from TS.

#### R5-API-2 — `_user_to_dict` (3 copies) drops `tenant_id` — **HIGH**
- **Files:** [users.py:282-291](../../backend/app/api/v1/users.py#L282), [audit.py:327-336](../../backend/app/api/v1/audit.py#L327), `auth.py:UserResponse`.
- **Fix:** Add `"tenant_id": getattr(user, "tenant_id", None)` to all three; extend TS `User` type.

#### R5-API-3 — `_quote_to_dict` and `QuoteResponse` schema drop `revision_no`, `superseded_by` — **HIGH**
- **Files:** [backend/app/models/quote.py:42, 47, 48](../../backend/app/models/quote.py#L42), [backend/app/api/v1/quotes.py:724-767](../../backend/app/api/v1/quotes.py#L724), [backend/app/schemas/quote.py:69-95](../../backend/app/schemas/quote.py#L69).
- **Impact:** V9 revision tree UI cannot render the `v1 → v2 → v3` chain.
- **Fix:** Add both keys to dict + schema.

#### R5-API-4 — `_email_to_dict` drops `tenant_id`, `is_duplicate`, `duplicate_of_id` — **HIGH**
- **File:** [emails.py:810-851](../../backend/app/api/v1/emails.py#L810).
- **Impact:** Dedupe UI cannot render "duplicate of" links.

#### R5-API-5 — `SparePartCreate.honeywell_code max_length=100` rejects valid 500-char DB values — **HIGH**
- **Files:** [backend/app/schemas/spare_part.py:9, 22](../../backend/app/schemas/spare_part.py#L9) vs [backend/app/models/spare_part.py:13](../../backend/app/models/spare_part.py#L13).
- **Fix:** `max_length=500`. Also drop `max_length` from `name_en/name_tr` (DB is `Text`).

#### R5-API-6 — `QuoteResponse` schema still declares removed `pdf_path` — **HIGH**
- **File:** [backend/app/schemas/quote.py:86](../../backend/app/schemas/quote.py#L86).
- **Fix:** `has_pdf: bool | None = None`.

#### R5-API-7 — `_part_to_dict` drops `min_margin_pct` (pricing guardrail) — **MEDIUM**
- **File:** [parts.py:291-311](../../backend/app/api/v1/parts.py#L291).
- **Impact:** Operator workaround = direct DB edit.

#### R5-API-8 — Pagination envelope drift on 11 endpoints — **HIGH**
| Route | Current shape | Issue |
|---|---|---|
| `/contracts/expiring` | `{contracts:[], count:N}` | Non-canonical, no pagination |
| `/subscriptions/` | `{items:[]}` | No total/page/page_size |
| `/subscriptions/renewals` | `{items:[]}` | No total/page/page_size |
| `/revenue-schedules/` | `{schedules:[]}` | Non-canonical, unbounded, N+1 |
| `/compliance/breaches` | `{breaches:[]}` | Non-canonical, unbounded |
| `/compliance/retention-policies` | `{policies:[]}` | Non-canonical |
| `/reports/v2/folders` | `{data:[]}` | Wrong key name |
| `/reports/v2/templates` | `{data:[]}` | Wrong key name |
| `/emails/training-data` | `{count, page, page_size, data}` | `count`→`total`, `data`→`items` |
| `/emails/{id}/thread` | `{thread_id, emails:[]}` | Add `total`, rename `emails`→`items` |
| `/parts/categories` | bare `list[str]` | Wrap as `{items, total}` |
| `/pipelines/` | `{pipelines:[]}` | Non-canonical |
- **Fix:** Bulk PR with `paginate(query, page, page_size)` helper.

#### R5-API-9 — `LeadCreate.email` uses `str` not `EmailStr` — **LOW**
- **Files:** [leads.py:42, 69](../../backend/app/api/v1/leads.py#L42).

#### R5-API-10..21 — see slice 2 for the full DTO list (User.manager_id, Customer.data_classification + deletion_requested_at, Lead.converted_by, ReportTemplateResponse 6-field hidden-by-`from_attributes`, EmailResponse 12-field schema gap, audit.py serializer subset drift, SparePart name caps, etc).

### 2.4 TS type / frontend consumer drift — CRITICAL × 3, HIGH × 5

#### R5-TS-1 — `PlaybookAnalytics.avg_completion_days` typed required, returned nullable → crash — **CRITICAL**
- **Files:** [types.ts:1024](../../frontend/src/lib/types.ts#L1024) (`avg_completion_days: number`), [PlaybookAnalyticsPage.tsx:66](../../frontend/src/features/playbooks/PlaybookAnalyticsPage.tsx#L66) (`.toFixed(1)`), [playbooks.py:193](../../backend/app/api/v1/playbooks.py#L193) (returns `None` when no completions).
- **Crash:** `null.toFixed()` → `TypeError`. Page is unmountable for tenants with no completed playbooks.
- **Fix:** Type as `number | null`; UI `?.toFixed(1) ?? '—'`.

#### R5-TS-2 / R5-FAKE-2 — `PlaybookAnalyticsPage` win-rate × 100 twice — **CRITICAL**
- See headline #2.

#### R5-TS-3 — `Lead.score_breakdown` field-name lie — **HIGH**
- **Files:** [types.ts:1951](../../frontend/src/lib/types.ts#L1951) declares `Array<{ name; label; points }>`; backend builds `{factor, points, reason}` ([lead_service.py:389-471](../../backend/app/services/lead_service.py#L389)).
- **Consumer compensates:** [LeadDetailPage.tsx:246-258](../../frontend/src/features/leads/LeadDetailPage.tsx#L246) re-casts. Future consumers will silently fail.
- **Fix:** Rewrite TS as `Array<{ factor: string; points: number; reason?: string }>`.

#### R5-TS-4 — `User.password_change_required` never typed — **HIGH**
- **Files:** [auth.py:27, 37](../../backend/app/schemas/auth.py#L27) vs [types.ts:2-10, 455-460](../../frontend/src/lib/types.ts#L2).
- **Impact:** Forced password rotation flag never reaches login flow. Compliance/security risk.

#### R5-TS-5, R5-TS-6 — `Quote.customer` and `QuoteItem.spare_part` shape lies — **HIGH**
- **Files:** [quotes.py:761-789](../../backend/app/api/v1/quotes.py#L761) returns 4-field summaries; [types.ts:278, 318](../../frontend/src/lib/types.ts#L278) declare full `Customer` / `SparePart`.
- **Impact:** Quote PDF preview that displays `quote.customer.address` silently prints blank.
- **Fix:** Introduce `QuoteEmbeddedCustomer` and `QuoteItemSparePartSummary` summary types.

#### R5-TS-7..16 — created_at marked `string` but defensive `.isoformat() if x else None` returns `null` — **MEDIUM**
- 8 entities affected (Lead, SparePart, Pipeline, Territory, Campaign, CampaignMember, EmailRequest, Subscription).
- **Fix:** Batch `string → string | null`. No runtime issue today; latent crash any time NULL is produced.

#### R5-TS-17..20 — `Invoice.tenant_id`, `Subscription.tenant_id`, `Contract.tenant_id`, `ApprovalRule.tenant_id` not declared in TS — **LOW**
- Backend round-trips them; TS doesn't know. Consistent with v1.9 multi-tenant rollout — just sync.

### 2.5 Data fetched but not rendered + UI completeness — CRITICAL × 4, HIGH × 16, MEDIUM × 16

#### R5-FAKE-1 — `AtRiskPage` fabricated revenue KPI — **CRITICAL** (headline #1)
- **File:** [AtRiskPage.tsx:140-143](../../frontend/src/features/board/AtRiskPage.tsx#L140).
- **Code:** `formatCurrency(opps.length * 100000, 'TRY')`.
- **Fix:** Either backend adds `amount` per item (so the KPI can be the sum of `opp.amount`) OR remove the KPI. Removal is the safer + faster fix.

#### R5-RENDER-OPP-1 — Kanban card hides 9 fields the API returns — **HIGH**
- **File:** [BoardPage.tsx:80-156](../../frontend/src/features/board/BoardPage.tsx#L80) renders 7 of 16 dict keys.
- **Missing:** `source`, `forecast_category`, `loss_reason`, `previous_stage`, `previous_amount`, `previous_close_date`, `probability`, `pipeline_id`, `territory_id`.
- **Impact:** Managers can't see momentum (probability), revenue-leak diff (`previous_amount`), or close-lost reason without opening the detail.

#### R5-RENDER-OPP-2 — `OpportunityDetailPage` never renders `source`, `forecast_category` (current value), `loss_reason`, `previous_*` — **HIGH**
- **File:** [OpportunityDetailPage.tsx](../../frontend/src/features/board/OpportunityDetailPage.tsx).
- Same gap round-4 flagged as `R4-RENDER-3`. **Carry-over** — not fixed.

#### R5-RENDER-CONTRACT-1 — Contract list has no customer column — **HIGH**
- **File:** [ContractListPage.tsx:301-321](../../frontend/src/features/contracts/ContractListPage.tsx#L301).
- **Impact:** Two contracts with same title for different customers indistinguishable.
- **Fix:** Backend includes `customer.name`/`customer.company` in `_serialize_contract`; UI adds column.

#### R5-RENDER-INVOICE-1 — see R5-API-1 above (CRITICAL)

#### R5-RENDER-SUB-1 — Subscription list/detail has no customer name column (only `#id`) — **MEDIUM**

#### R5-RENDER-AUDIT-1 — Audit log hides `tenant_id` — **LOW**

(See slice 4 for the full 42-finding catalogue with file:line for every page audited.)

### 2.6 Form completeness — CRITICAL × 1, HIGH × 4, MEDIUM × 2

#### R5-FORM-3 / R5-FORM-4 — Customer create/update silently drops `website` + `linkedin_url` — **CRITICAL**
- **Files:** [CustomerListPage.tsx:283-296, 583-594](../../frontend/src/features/customers/CustomerListPage.tsx#L283), [CustomerDetailPage.tsx:244](../../frontend/src/features/customers/CustomerDetailPage.tsx#L244), [backend/app/schemas/customer.py:8-25](../../backend/app/schemas/customer.py#L8).
- Pydantic ignores extras by default → discards values; toast says success.
- **Fix:** Add `website`, `linkedin_url`, `industry`, `annual_revenue`, `employee_count`, `parent_id`, `territory_id` to both `CustomerCreate` and `CustomerUpdate`; thread into model insert at [customers.py:420-431](../../backend/app/api/v1/customers.py#L420).

#### R5-FORM-1 — Lead create has no `notes` field — **HIGH**

#### R5-FORM-2 — Lead detail has no inline edit form — **HIGH**

#### R5-FORM-5 — Quote `valid_days` not editable — **MEDIUM**

#### R5-FORM-6 — Subscription `end_date`, `quote_id` not on create — **HIGH**

### 2.7 Realtime / event / cache — HIGH × 3, MEDIUM × 5, LOW × 4

#### R5-CACHE-1 / HIGH-1 — Logout doesn't clear TanStack cache → PII flash on shared device — **HIGH** (headline #10)
- **Files:** [authStore.ts:123-141](../../frontend/src/stores/authStore.ts#L123), [main.tsx:15-23](../../frontend/src/main.tsx#L15).
- **Verified:** `grep "queryClient.clear\|queryClient.removeQueries" frontend/src/` returns zero hits.
- **Fix:** Inject `queryClient` into auth flow; call `queryClient.clear()` in `logout()` AND in the 401-redirect interceptor.

#### R5-EVENT-1 / HIGH-2 — Retention scheduler cross-tenant notification leak — **HIGH** (headline #11)
- **File:** [scheduler.py:455-509](../../backend/app/tasks/scheduler.py#L455).
- **Fix:** `GROUP BY Customer.tenant_id`; per-tenant manager notify.

#### R5-EVENT-2 / HIGH-3 — `lead.score_changed` payload missing `delta` — **HIGH** (headline #12)
- **Files:** [lead_service.py:113-124](../../backend/app/services/lead_service.py#L113) emits `{lead_id, old_score, new_score, reason}`; [LeadDetailPage.tsx:71](../../frontend/src/features/leads/LeadDetailPage.tsx#L71) reads `payload?.delta`.
- **Fix:** Include `delta = new_score - old_score` in publisher payload OR compute on consumer.

#### R5-CACHE-2..4 — `pdfMutation`, `saveMutation`, `createCustomer` skip / mis-invalidate — **MEDIUM**
- Files: [QuoteListPage.tsx:81-102](../../frontend/src/features/quotes/QuoteListPage.tsx#L81), [ReportBuilderPage.tsx:159-177](../../frontend/src/features/reports/ReportBuilderPage.tsx#L159), [CustomerListPage.tsx:319-333](../../frontend/src/features/customers/CustomerListPage.tsx#L319).

#### R5-EVENT-3..4 — Workflow rule notifications silently skipped for `quote.approved` / `email.parsed` — **MEDIUM**
- **File:** [workflow_service.py:103-114](../../backend/app/services/workflow_service.py#L103) reads `owner_id || created_by`; payloads carry `approved_by`. Notification appears to fire (matches) but no user sees it.

#### R5-EVENT-5 — `SEQUENCE_ENROLLED/PAUSED/RESUMED` declared, never emitted — **MEDIUM**
- **File:** [domain_events.py:30-33](../../backend/app/services/domain_events.py#L30) — false-promise constants.
- **Fix:** Either publish or delete.

#### R5-EVENT-6..9 — `invoice.paid` no-op subscriber, `revenue_signal.created` payload missing `owner_id`, etc — **LOW**

### 2.8 DB ↔ ORM drift — HIGH × 1, MEDIUM × 6, LOW × 2

#### R5-DB-1 — Bootstrap missing `opportunity_transformer_seq_embeddings` — **MEDIUM**
- **Files:** [v12_transformer_seq_embedding.py:25-39](../../backend/app/models/v12_transformer_seq_embedding.py#L25), [20260428_v12_transformer_seq_embedding.py:28-37](../../backend/alembic/versions/20260428_v12_transformer_seq_embedding.py#L28). Bootstrap (20260101) has 128 tables; should be 129.
- **Fix:** Re-run `python backend/scripts/regenerate_bootstrap_migration.py`.
- **Prod impact:** None.

#### R5-DB-2 / R5-DB-3 — Duplicate indexes on `signature_requests.tenant_id` and `webhook_deliveries.tenant_id` — **LOW**
- Both have `Index("ix_..._tenant", "tenant_id")` in `__table_args__` AND `index=True` on column → 2 indexes per table.
- **Fix:** Drop `index=True`; new migration drops the redundant index.

#### R5-DB-4 — 15 model files cite alembic revision IDs that don't exist — **MEDIUM**
- 4 names referenced in docstrings, none match actual revision IDs (e.g., `20260504_add_tenant_id_to_engagement_billing` → `20260504_phase4_tenant`).
- **Fix:** Sweep find-and-replace in `backend/app/models/*.py`.

#### R5-DB-5..7 — `subscriptions`/`customers` `CREATE TABLE` declared in two migrations; FK constraint name divergence — **MEDIUM/LOW**
- Defensive `IF NOT EXISTS` keeps it safe today; latent risk for future `DROP CONSTRAINT` migrations.

#### R5-DB-8 — Schema-drift gate runs only as shell command in CI, not as pytest — **HIGH**
- **Risk:** Local `pytest` doesn't catch what CI catches; first signal of drift is a red CI build.
- **Fix:** Add `backend/tests/test_schema_drift.py` with `@pytest.mark.schema` marker.

---

## 3. Cross-Layer Schema Compatibility Matrix (selected entities)

### Customer

| Field | DB (model) | Migration | Backend `_to_dict` | API schema | TS type | UI rendered? | Status |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:--|
| id | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | OK |
| name, email, company, phone, address, tax_id | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | OK |
| tenant_id | ✓ | ✓ | ✓ | ✓ | ✓ | partial | OK |
| website, linkedin_url | ✓ | ✓ | ✓ | ❌ create/update | ✓ | display only | **FORM-DROP** |
| industry, employee_count, annual_revenue | ✓ | ✓ | ✓ | ❌ create/update | ✓ | display only | **FORM-DROP** |
| parent_id, territory_id | ✓ | ✓ | ✓ | ❌ create/update | ✓ | partial | **FORM-DROP** |
| data_classification, deletion_requested_at | ✓ | ✓ | ❌ | ❌ | ❌ | ❌ | **DTO-DROP** |
| stats (computed) | n/a | n/a | ✓ (detail only) | ❌ | ❌ | ✓ (re-typed locally) | **TS-DRIFT** |

### Invoice

| Field | DB | Migration | Backend `_to_dict` | TS type | UI | Status |
|---|:-:|:-:|:-:|:-:|:-:|:--|
| id, invoice_number, status, total, currency, dates | ✓ | ✓ | ✓ | ✓ | ✓ | OK |
| customer_id | ✓ | ✓ | ✓ | ✓ | ✓ | OK |
| **`customer` object** | n/a | n/a | **❌** | ✓ (`{id,name,company}`) | **broken (`#id` fallback)** | **CRITICAL** |
| tenant_id | ✓ | ✓ | ✓ | ❌ | ❌ | **TS-DRIFT** |
| customer name on list | n/a | n/a | ❌ | n/a | ❌ no column | **RENDER-GAP** |
| Field-permission masking | n/a | n/a | **❌** | n/a | n/a | **CRITICAL (R5-PERM-1)** |

### Quote

| Field | DB | Backend `_to_dict` | API schema | TS type | UI | Status |
|---|:-:|:-:|:-:|:-:|:-:|:--|
| revision_no, superseded_by | ✓ | ❌ | ❌ | ❌ | ❌ | **DTO-DROP (V9 broken)** |
| pdf_path | ✓ (column) | ❌ removed (returns `has_pdf`) | ✓ stale schema | ❌ | n/a | **SCHEMA-STALE** |
| customer (nested) | n/a | 4-field summary | ✓ full | ✓ full Customer | ✓ partial | **TS-LIE** |
| valid_days | ✓ | ✓ | ❌ in Create/Update | ✓ | display only | **FORM-DROP** |

### Opportunity (kanban card render)

| Field | DB | Backend `_to_dict` | TS type | Kanban card | Detail page | Status |
|---|:-:|:-:|:-:|:-:|:-:|:--|
| source | ✓ | ✓ | ✓ | ❌ | ❌ | **RENDER-GAP** |
| forecast_category (current) | ✓ | ✓ | ✓ | ❌ | partial (form only) | **RENDER-GAP** |
| loss_reason | ✓ | ✓ | ✓ | ❌ | ❌ | **RENDER-GAP** |
| previous_stage/amount/close_date | ✓ | ✓ | ✓ | ❌ | ❌ | **R4-RENDER-3 carry-over** |
| probability | ✓ | ✓ | ✓ | ❌ | ✓ once | partial |

### User

| Field | DB | `users.py:_user_to_dict` | `audit.py:_user_to_dict` | `auth.py:UserResponse` | TS `User` | Status |
|---|:-:|:-:|:-:|:-:|:-:|:--|
| tenant_id | ✓ | ❌ | ❌ | ✓ | ❌ | **DTO-DROP × 3 + TS-DRIFT** |
| password_change_required | ✓ | ❌ | n/a | ✓ | ❌ | **TS-DRIFT (compliance)** |
| manager_id | ✓ | ❌ | ❌ | ❌ | ❌ | **DTO-DROP × 3** |

---

## 4. Fix Plan

### 4.1 Day-0 hotfix PR (visible incidents — 1 day)

| ID | What | Files | Effort |
|---|---|---|---|
| R5-FAKE-1 | Remove `opps.length × 100000` KPI or replace with sum of `opp.amount` | AtRiskPage.tsx | 10 min |
| R5-FAKE-2 | Drop `* 100` in PlaybookAnalyticsPage WinRateCard | PlaybookAnalyticsPage.tsx:31 | 5 min |
| R5-TS-1 | Type `avg_completion_days: number \| null` + `?.toFixed` | types.ts:1024, PlaybookAnalyticsPage.tsx:66 | 5 min |
| R5-API-1 | Add `customer` to `_invoice_to_dict` (lazy="selectin") | invoices.py:86, models/invoice.py | 30 min |
| R5-CACHE-1 | `queryClient.clear()` on logout + 401 interceptor | authStore.ts, main.tsx, lib/apiClient.ts | 30 min |
| R5-FORM-3/4 | Add 7 fields to `CustomerCreate` + `CustomerUpdate`; thread through model insert | schemas/customer.py, customers.py | 45 min |
| R5-API-5 | `max_length=500` for SparePart `honeywell_code` | schemas/spare_part.py:9, 22 | 2 min |

### 4.2 Sprint hotfix PR (security, 2-3 days)

| ID | What | Migration? |
|---|---|---|
| R5-PERM-1 | Wire `apply_request_perms` on contracts/invoices/subscriptions/campaigns | No |
| R5-TEN-25 | `assert_same_tenant` after Opportunity / Quote loads in integrations.py | No |
| R5-TEN-26 | Same on pipelines, stakeholders, dashboard_builder, feature_store, deal_rooms, admin_dead_letters | No |
| R5-TEN-27 | `require_role` on admin_dead_letters | No |
| R5-TEN-28 | Add `tenant_id` to BreachNotification + ReportFolder | **Yes** — `20260505_add_tenant_id_to_breach_and_folder.py` |
| R5-PII-4 | `_SENSITIVE_KEY_PATTERNS` masking + encrypt-on-PUT | No (data already in cleartext, leave existing values until rotated) |
| R5-PII-5 | Encrypt esign webhook secret at-rest | No |
| R5-FLAG-15 | Add `FEATURE_CONTRACTS` + `FEATURE_SUBSCRIPTIONS` flags + dependencies + UI gates | No |
| R5-RL-7 | New `enforce_signing_rate_limit` bucket on `/sign/*` | No |
| R5-RL-8 | Lift AI rate-limit deps to coaching/v5/v6/guided_selling routers | No |
| R5-EVENT-1 | Tenant-group the retention scheduler | No |
| R5-EVENT-2 | Add `delta` to `lead.score_changed` payload | No |

### 4.3 Cleanup PR (DTO drift + envelope, 2-3 days)

| ID | What |
|---|---|
| R5-API-2 | `tenant_id` in 3 `_user_to_dict` copies + auth.UserResponse + TS |
| R5-API-3 | `revision_no` + `superseded_by` in `_quote_to_dict` + schema + TS |
| R5-API-4 | `tenant_id`, `is_duplicate`, `duplicate_of_id` in `_email_to_dict` |
| R5-API-6 | Drop `pdf_path` from `QuoteResponse` schema; add `has_pdf` |
| R5-API-7 | `min_margin_pct` in `_part_to_dict` + schemas + part editor form |
| R5-API-8 | Pagination envelope sweep across 11 endpoints with `paginate(query, page, page_size)` helper |
| R5-API-9 | `EmailStr` on Lead create/web-lead schemas |
| R5-TS-3 | Rewrite `Lead.score_breakdown` TS as `{factor, points, reason?}[]` |
| R5-TS-4 | Add `password_change_required` to `User`/`TokenResponse` TS |
| R5-TS-5/6 | Introduce `QuoteEmbeddedCustomer`, `QuoteItemSparePartSummary` TS types |
| R5-TS-7..16 | Batch `created_at: string → string \| null` |
| R5-TS-17..20 | Add `tenant_id` to Invoice/Subscription/Contract/ApprovalRule TS |
| R5-FLAG-16 | Wrap 10 routes with `<FeatureFlagGate>` |
| R5-ROLE-3 | Replace `'admin'` with `'operations'` in Sidebar.tsx:76 |
| R5-FORM-1/2 | Add Lead `notes` create field + inline edit form |

### 4.4 UI completeness PR (3-4 days)

- R5-RENDER-OPP-1/2: kanban card + opp detail render `source`, `forecast_category`, `loss_reason`, `previous_*`.
- R5-RENDER-CONTRACT-1: customer column on contract list (DTO + UI).
- R5-RENDER-SUB-1: customer name on subscription list/detail.
- R5-RENDER-LIST-INVOICE-2: surface `tax_rate`, `subtotal`, `tax_amount`, `paid_at`, `quote_id` on invoice list.
- Mobile: add `hidden sm:table-cell` on lower-priority columns of 5 list pages; stage-tab fallback for kanban on `<md`.

### 4.5 Backlog (1-2 weeks)

- R5-DB-1: regenerate bootstrap snapshot.
- R5-DB-4: revision-name doc rot sweep.
- R5-DB-8: pytest schema-drift gate (see §6).
- R5-PERM-3: refactor 65+ inline role checks to `is_manager(user)` / `can_view_team(...)` helpers.
- R5-FLAG-17 CI assertion: `tests/test_flag_symmetry.py`.
- R5-EVENT-5: publish or delete `SEQUENCE_ENROLLED/PAUSED/RESUMED` constants.
- R5-CACHE-helper-adoption: lint rule banning ad-hoc `invalidateQueries` outside `cacheInvalidation.ts`.

### 4.6 Risky changes needing manual review

- **R5-API-8 pagination sweep** — frontend list-rendering logic for affected pages must be reviewed; some pages already loop on `data.contracts` etc., and renaming to `items` is a breaking client change.
- **R5-TEN-28 BreachNotification + ReportFolder tenant_id backfill** — rows with NULL `customer_id` (BreachNotification) or `is_shared=True` (ReportFolder) need a default tenant or per-row decision.

---

## 5. Suggested Code Patches (representative; full set in slice reports)

### 5.1 R5-FAKE-2 — single-line frontend fix
```tsx
// frontend/src/features/playbooks/PlaybookAnalyticsPage.tsx:31
- const percentage = `${(rate * 100).toFixed(1)}%`;
+ const percentage = rate == null ? '—' : `${rate.toFixed(1)}%`;
```

### 5.2 R5-PERM-1 — append `apply_request_perms` to 4 serializers
```python
# backend/app/api/v1/contracts.py — _serialize_contract
def _serialize_contract(c: Contract) -> dict:
    data = {...}  # existing
    return apply_request_perms(data, "contract")
# Same for invoices.py:_invoice_to_dict, subscriptions.py:_serialize, campaigns.py:_campaign_to_dict
```

### 5.3 R5-CACHE-1 — clear cache on logout
```ts
// frontend/src/lib/queryClient.ts — export the shared instance (it already exists; ensure exported)
// frontend/src/stores/authStore.ts:logout
import { queryClient } from '../lib/queryClient';
logout: async () => {
  // existing await + localStorage clear
  queryClient.clear();
  set({ ... });
}
// frontend/src/lib/apiClient.ts — also call queryClient.clear() in 401 redirect path
```

### 5.4 R5-TEN-25 — assert_same_tenant after lookups
```python
# backend/app/api/v1/integrations.py:272
opp = (await db.execute(select(Opportunity).where(Opportunity.id == body.opportunity_id))).scalar_one_or_none()
if not opp:
    raise NotFoundException("Firsat bulunamadi")
+assert_same_tenant(opp, current_user, exception_cls=NotFoundException)
```

### 5.5 R5-PII-4 — masking in GET /settings/
```python
# backend/app/api/v1/settings.py:103
SENSITIVE_PATTERNS = ("password", "secret", "_token", "api_key", "_key")
def _is_sensitive(key: str) -> bool:
    k = key.lower()
    return any(p in k for p in SENSITIVE_PATTERNS)

@router.get("/")
async def get_settings(...):
    settings_dict = {s.key: ("********" if _is_sensitive(s.key) else s.value) for s in settings}
    return {"settings": settings_dict}
```

### 5.6 R5-EVENT-1 — tenant-group retention scheduler
```python
# backend/app/tasks/scheduler.py:455
result = await db.execute(
    select(Customer.tenant_id, func.count(Customer.id))
    .where(Customer.data_retention_until < now, Customer.deletion_requested_at.is_(None))
    .group_by(Customer.tenant_id)
)
for tenant_id, count in result.all():
    managers = (await db.execute(
        select(User).where(
            User.role == "sales_manager",
            User.is_active.is_(True),
            User.tenant_id == tenant_id,
        )
    )).scalars().all()
    # notify each manager with this tenant's count
```

---

## 6. Suggested Database Migrations

### 6.1 `20260505_add_tenant_id_to_breach_and_folder.py` (R5-TEN-28)
```python
def upgrade():
    op.add_column("breach_notifications", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column("report_folders", sa.Column("tenant_id", sa.Integer(), nullable=True))
    # Backfill from owner→tenant
    op.execute("""
      UPDATE breach_notifications b
        SET tenant_id = (SELECT tenant_id FROM customers c WHERE c.id = b.customer_id)
        WHERE tenant_id IS NULL AND customer_id IS NOT NULL
    """)
    op.execute("""
      UPDATE report_folders f
        SET tenant_id = (SELECT tenant_id FROM users u WHERE u.id = f.created_by)
        WHERE tenant_id IS NULL
    """)
    op.create_index("ix_breach_notifications_tenant_id", "breach_notifications", ["tenant_id"])
    op.create_index("ix_report_folders_tenant_id", "report_folders", ["tenant_id"])

def downgrade():
    op.drop_index("ix_breach_notifications_tenant_id", "breach_notifications")
    op.drop_index("ix_report_folders_tenant_id", "report_folders")
    op.drop_column("breach_notifications", "tenant_id")
    op.drop_column("report_folders", "tenant_id")
```
- **Backfill safety:** rows with NULL `customer_id` in breach_notifications need a default tenant — either fail-loud (`SELECT COUNT(*) WHERE tenant_id IS NULL` after backfill) or assign to a designated "system" tenant. Document the decision in the migration.
- **Rollback:** safe (additive column).

### 6.2 `20260505_drop_dup_indexes.py` (R5-DB-2/3)
```python
def upgrade():
    op.execute("DROP INDEX IF EXISTS ix_signature_requests_tenant_id")
    op.execute("DROP INDEX IF EXISTS ix_webhook_deliveries_tenant_id")

def downgrade():
    op.execute("CREATE INDEX IF NOT EXISTS ix_signature_requests_tenant_id ON signature_requests (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_tenant_id ON webhook_deliveries (tenant_id)")
```

### 6.3 Bootstrap regeneration (R5-DB-1) — script-only, no migration

```bash
python backend/scripts/regenerate_bootstrap_migration.py
git diff backend/alembic/versions/20260101_bootstrap_legacy.py  # expect: + CREATE TABLE opportunity_transformer_seq_embeddings ...
```

---

## 7. Suggested Tests

### 7.1 R5-DB-8 — Schema-drift pytest gate
```python
# backend/tests/test_schema_drift.py
import os, pytest
from sqlalchemy import create_engine
from app.core.database import Base
from app.core.schema_check import check_schema
from app import models  # noqa: F401

@pytest.mark.schema
def test_no_schema_drift_against_test_db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL not set")
    engine = create_engine(url.replace("+asyncpg", ""))
    report = check_schema(engine, Base.metadata)
    assert report.is_clean, report.summary()
```

### 7.2 Bootstrap snapshot completeness
```python
# backend/tests/test_bootstrap_snapshot_complete.py
import re
from pathlib import Path
from app.core.database import Base
from app import models  # noqa: F401

def test_bootstrap_creates_every_model_table():
    src = (Path(__file__).parent.parent / "alembic/versions/20260101_bootstrap_legacy.py").read_text()
    declared = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", src))
    expected = {t.name for t in Base.metadata.sorted_tables}
    missing = expected - declared
    assert not missing, f"Bootstrap missing: {sorted(missing)}. Run regenerate script."
```

### 7.3 Tenant-scope regression test (one per router added in R5-TEN-25/26)
```python
# backend/tests/test_pipelines_tenant.py
@pytest.mark.asyncio
async def test_pipeline_get_rejects_cross_tenant(client, manager_a_headers, pipeline_in_b):
    r = await client.get(f"/api/v1/pipelines/{pipeline_in_b.id}", headers=manager_a_headers)
    assert r.status_code == 404  # not 200 with foreign data
```

### 7.4 Field-permission masking coverage
```python
# backend/tests/test_field_permissions_coverage.py
@pytest.mark.parametrize("entity,fixture", [
    ("contract", contract_fixture),
    ("invoice", invoice_fixture),
    ("subscription", subscription_fixture),
    ("campaign", campaign_fixture),
])
def test_serializer_applies_field_perms(entity, fixture, mocker):
    mock = mocker.patch("app.services.field_permission_service.apply_request_perms",
                        side_effect=lambda d, _e: d)
    serialize(fixture)
    mock.assert_called_once()
```

### 7.5 Flag symmetry CI assertion
```python
# backend/tests/test_flag_symmetry.py
PUBLIC_FLAGS = {...}  # import from settings
ROUTER_FLAG_DEPS = {  # build from grep at test time
    "FEATURE_INVOICING": ["app.api.v1.invoices"],
    ...
}
def test_every_public_flag_has_backend_gate():
    for flag in PUBLIC_FLAGS:
        assert ROUTER_FLAG_DEPS.get(flag), f"{flag} exposed to SPA but no backend router gates it"
```

### 7.6 Pydantic schema ↔ ORM sync test
```python
# backend/tests/test_dto_orm_sync.py
@pytest.mark.parametrize("model,schema_create,schema_update", [
    (Customer, CustomerCreate, CustomerUpdate),
    (Quote, QuoteCreate, QuoteUpdate),
    ...
])
def test_create_schema_covers_writable_columns(model, schema_create, schema_update):
    declared = set(schema_create.model_fields)
    writable = {c.name for c in model.__table__.columns
                if not c.primary_key and c.name not in {"created_at", "updated_at", "tenant_id", "created_by"}}
    missing = writable - declared
    # Allow allow-listed exclusions (e.g., enrichment fields written only by services)
    assert not missing, f"{model.__name__}Create missing writable columns: {missing}"
```

This catches R5-FORM-3 / R5-FORM-4 / R5-FORM-5 / R5-FORM-6 class-of-bugs at PR time.

### 7.7 Frontend type contract test
```ts
// frontend/src/__tests__/api-contract.test.ts
// For each entity, fetch a fixture API response and assert TS interface accepts it.
// Use zod-to-typescript or runtime parser to fail on unknown / missing keys.
```

### 7.8 Cache-clear-on-logout regression test
```ts
test('logout clears query cache', async () => {
  queryClient.setQueryData(['user'], { id: 1 });
  await act(async () => await useAuthStore.getState().logout());
  expect(queryClient.getQueryData(['user'])).toBeUndefined();
});
```

---

## 8. Lists requested by spec

### 8.1 Database columns not used by backend
None confirmed — every model column has at least one backend reader. (R5-DB-1 is the inverse — model column not in bootstrap snapshot.)

### 8.2 Backend model fields not backed by database
None. Round-4 closed `Quote.pdf_path` — column kept, schema reference stale (R5-API-6).

### 8.3 Backend fields not exposed through API
- `User.tenant_id` (3 dict copies + UserResponse) — R5-API-2
- `User.manager_id` (all)
- `Customer.data_classification`, `deletion_requested_at` — R5-API
- `Lead.converted_by` — R5-API-10
- `Quote.revision_no`, `superseded_by` — R5-API-3
- `EmailRequest.tenant_id`, `is_duplicate`, `duplicate_of_id` — R5-API-4
- `SparePart.min_margin_pct` — R5-API-7
- `ReportTemplate.tenant_id`, `folder_id`, `email_schedule`, `email_recipients`, `created_at`, `updated_at` — R5-API-14

### 8.4 API fields never consumed by frontend
- `password_change_required` (auth) — R5-TS-4
- `tenant_id` on `Invoice`, `Subscription`, `Contract`, `ApprovalRule` — R5-TS-17..20
- `Opportunity.previous_stage/close_date/amount` (typed in TS, no consumer) — feeds R5-RENDER-OPP-1/2

### 8.5 Frontend fields/types missing from API/backend
- `Quote.has_pdf` (typed; backend returns it; OK)
- `Invoice.customer` (typed; backend doesn't return) — R5-API-1 **CRITICAL**
- `Subscription.customer` (typed; backend doesn't return) — analogous

### 8.6 Data fetched but not rendered
- Kanban opp card: 9 fields hidden — R5-RENDER-OPP-1
- Quote list: 11 fields hidden — R5-RENDER-LIST-QUOTE-1
- Invoice list: 9 fields hidden + customer phantom — R5-RENDER-INVOICE-1/2
- Subscription list: 7 fields hidden — R5-RENDER-LIST-SUB-1
- Audit log: tenant_id hidden — R5-RENDER-LIST-AUDIT-1
- See slice 4 for full table.

### 8.7 UI components showing incomplete data
- Same as 8.6.

### 8.8 Realtime events emitted but not handled
- `sequence.enrolled_auto` — emitted in scoring_service, no subscriber
- `invoice.paid` — one `pass` subscriber, webhook service not subscribed
- `revenue_signal.created` — only playbook auto-trigger subscribes

### 8.9 Realtime events handled but not emitted
- `DomainEvents.SEQUENCE_ENROLLED/PAUSED/RESUMED` — declared, never published
- Frontend `lead.score_changed` reads `payload.delta` — never emitted (R5-EVENT-2)

### 8.10 Schema/type/nullability mismatches
See §2.4 (R5-TS-1..20) and §2.3 (R5-API-5).

### 8.11 Permission or feature-flag mismatches
See §2.2 (R5-PERM-1..7, R5-FLAG-15..20, R5-ROLE-3).

### 8.12 Required migrations
- `20260505_add_tenant_id_to_breach_and_folder.py` (R5-TEN-28)
- `20260505_drop_dup_indexes.py` (R5-DB-2/3) — low priority

### 8.13 Recommended frontend type updates
- `Invoice.customer` (drop or wire backend)
- `User.tenantId`, `User.passwordChangeRequired`
- `Lead.score_breakdown` shape rewrite
- `PlaybookAnalytics.win_rate_*` and `avg_completion_days` to `number | null`
- `QuoteEmbeddedCustomer`, `QuoteItemSparePartSummary` summary types
- `Quote.revisionNo`, `Quote.supersededBy`
- `Email.isDuplicate`, `Email.duplicateOfId`
- 8 `created_at` fields → `string | null`
- `tenant_id` on Invoice/Subscription/Contract/ApprovalRule

### 8.14 Recommended backend DTO/serializer updates
- `apply_request_perms` on contract/invoice/subscription/campaign serializers
- `customer` object in `_invoice_to_dict`
- `tenant_id` in 3 `_user_to_dict` copies + `auth.UserResponse`
- `revision_no` + `superseded_by` in `_quote_to_dict` + schema
- `tenant_id` + `is_duplicate` + `duplicate_of_id` in `_email_to_dict`
- `min_margin_pct` in `_part_to_dict` + spare-part schemas
- Pagination envelope helper across 11 endpoints
- `ReportTemplateResponse` 6-field schema sync
- `EmailStr` on Lead + WebLead create
- Drop `pdf_path` from `QuoteResponse` schema; add `has_pdf`

### 8.15 Recommended tests
See §7 (8 test classes covering schema drift, bootstrap completeness, tenant-scope regression, field-perm masking, flag symmetry, DTO↔ORM sync, frontend type contract, cache-clear-on-logout).

---

## 9. Verification appendix

Every headline claim spot-checked against source on 2026-05-05:

| Headline | Verification |
|---|---|
| R5-FAKE-1 (`opps.length * 100000`) | `grep "100000" frontend/src/features/board/AtRiskPage.tsx` → line 141 confirmed |
| R5-FAKE-2 (backend × 100, frontend × 100) | `grep "rate \* 100\|won_with"` confirmed both sites |
| R5-PERM-1 (4 serializers without masking) | `grep "apply_request_perms" backend/app/api/v1/{contracts,invoices,subscriptions,campaigns}.py` → exit code 1 (zero matches) |
| R5-TEN-25 (integrations.py no tenant assert) | `sed -n '265,285p;530,550p' backend/app/api/v1/integrations.py` confirmed |
| R5-TEN-26 (pipelines.py 4 endpoints) | `grep "select(Pipeline)" backend/app/api/v1/pipelines.py` → 4 lines (110, 126, 157, 179) |
| R5-PII-4 (settings only masks email_password) | `sed -n '95,130p' backend/app/api/v1/settings.py` confirmed |
| R5-FORM-3 (Customer schema misses fields) | `grep "website\|linkedin" backend/app/schemas/customer.py` → no matches; `grep` of CustomerListPage.tsx confirmed inputs at L583-589 |
| R5-CACHE-1 (logout no clear) | `sed -n '120,145p' frontend/src/stores/authStore.ts` — body confirmed; no `queryClient` import or call |
| R5-EVENT-1 (retention scheduler global) | `sed -n '450,510p' backend/app/tasks/scheduler.py` — confirmed no tenant grouping |
| R5-EVENT-2 (lead.score_changed payload missing delta) | Backend `grep "old_score\|new_score" lead_service.py` → 4 lines, no `delta`; frontend `grep "payload?.delta"` → confirmed at LeadDetailPage.tsx:71 |
| R5-FLAG-15 (contracts/subscriptions no flag) | `grep "_require_\|FEATURE_CONTRACT\|FEATURE_SUB" backend/app/api/v1/{contracts,subscriptions}.py` → no matches |
| R5-RL-7 (signing endpoints no rate-limit) | `grep "@router.post.*sign\|enforce_.*rate_limit" backend/app/api/v1/signatures.py` confirmed bare decorators |
| R5-API-1 (Invoice phantom customer) | `grep "_invoice_to_dict\|customer\?:" backend/app/api/v1/invoices.py frontend/src/lib/types.ts` confirmed mismatch |
| R5-FORM-1 (Lead create no notes) | `grep "notes\|first_name\|INITIAL" frontend/src/features/leads/LeadListPage.tsx` confirmed only basic fields in form |

---

**Audit by 6 parallel slice investigators (DB↔ORM, Backend↔API, API↔Frontend, UI completeness, Realtime/cache/state, Permissions/flags). Total 96 distinct findings; 14 critical, 39 high, 32 medium, 11 low. Zero files modified per instruction. Highest-leverage hotfix is the Day-0 PR (~2 hours) closing 7 visible incidents (fake KPIs, runtime crash, PII flash, silent form drops, phantom invoice customer).**
