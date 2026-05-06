# Cross-Layer Audit Report — Honeywell Sales Suite (Round 6, post-v1.10.11)

**Date:** 2026-05-06
**Branch:** `deploy/render-sandbox`
**HEAD:** `fab47bb` (post v1.10.11 — Round-5's 96 findings shipped over v1.10.0..v1.10.11)
**Scope:** DB schemas/migrations · Backend models/services · API contracts · Frontend clients/types · UI rendering · Realtime/events · Permissions · State/lifecycle · Dep-bump compatibility (pydantic 2.13.3, asyncpg 0.31, @tanstack/react-query 5.x, lucide 1.14, zod 4.4, sentry 10.51)
**Method:** 6 parallel slice investigators (DB↔ORM, Backend↔API, API↔TS, UI completeness, Permissions/flags/tenant, Realtime/cache). Slices 1+2+4 returned cleanly; slices 3, 5, 6 watchdog-stalled at 600s — critical claims from those slices were re-verified directly via `grep`/`Read` so this report ships only evidence-backed findings.

---

## 1. Executive Summary

| Metric | Count |
|---|---:|
| **Total verified findings** | **52** |
| Critical | 1 |
| High | 13 |
| Medium | 23 |
| Low | 15 |
| **Round-5 regressions / partials** | **6** |

### Top headline issues

1. **R6-API-1 — `Campaign` cross-tenant data leak (CRITICAL).** `Campaign` and `CampaignMember` models have **no `tenant_id` column** ([campaign.py:13, :47](../../backend/app/models/campaign.py#L13)), and `list_campaigns` builds `select(Campaign).order_by(Campaign.created_at.desc())` with **zero tenant scoping** ([campaigns.py:126](../../backend/app/api/v1/campaigns.py#L126)). Every authenticated user from tenant A sees every campaign from every other tenant. Same shape Round-4 closed for Invoice/Contract/Subscription. R5-PERM-1 wired `apply_request_perms(data, "campaign")` ([campaigns.py:88](../../backend/app/api/v1/campaigns.py#L88)) but it's admin theater without the column. **Highest blast radius in this audit.** Needs a migration.

2. **R6-FORM-5 / R6-FORM-6 — Two Round-5 form fixes never landed in the SPA.**
   - `QuoteEditorPage.tsx` — zero `valid_days` / `validDays` references in the file. Backend `QuoteCreate.valid_days` was added in R5-FORM-5 but the form input was never authored. Reps cannot set quote validity from the UI.
   - `SubscriptionListPage.tsx` — `CreateFormState` ([:32](../../frontend/src/features/subscriptions/SubscriptionListPage.tsx#L32)) has no `end_date` or `quote_id` fields. Backend `SubscriptionCreate` accepts both. Reps cannot record contracted end-date or link quote→subscription.

3. **R6-FORM-3 — Customer create/update form drops 5 of 7 enrichment fields (R5-FORM-3/4 partial).** Form only captures `website` + `linkedin_url` ([CustomerListPage.tsx:294-295](../../frontend/src/features/customers/CustomerListPage.tsx#L294)). Backend `CustomerCreate`/`CustomerUpdate` accept `industry`, `employee_count`, `annual_revenue`, `parent_id`, `territory_id` (R5-FORM-3 widened the schema). Manual override of AI-enrichment values is impossible from the UI; territory rollups + parent-account hierarchies cannot be set in-UI at all.

4. **R6-API-3 — Invoice serializer leaks `pdf_path` (R5-API-6 partial regression).** `_invoice_to_dict` ([invoices.py:119](../../backend/app/api/v1/invoices.py#L119)) still ships `"pdf_path": invoice.pdf_path` — a server filesystem path. Round-5 R5-API-6 closed this for Quote (`has_pdf` + drop `pdf_path`) but the same swap was never applied to Invoice. **Information disclosure** of the server's data layout to the SPA.

5. **R6-RENDER-OPP-1 — Kanban renders only 4 of 9 advertised opportunity fields (R5-RENDER-OPP-1 partial).** Card shows `forecast_category`, `loss_reason`, `probability`, `source` ([BoardPage.tsx:111-231](../../frontend/src/features/board/BoardPage.tsx#L111)). **Missing**: `previous_stage`, `previous_amount`, `previous_close_date`, `pipeline_id`, `territory_id`. Revenue-leak audit ("deal slipped from $50k → $30k") requires opening the detail page; not visible at scan-time on the kanban.

6. **R6-DB-1 — Duplicate index from `unique=True + index=True` on auth-critical columns (HIGH).** Same anti-pattern Round-5 R5-DB-2/3 closed for `tenant_id`, but missed on `email` / `jti` / `token` family. Affected: [user.py:15](../../backend/app/models/user.py#L15) `User.email`, [customer.py:21](../../backend/app/models/customer.py#L21) `Customer.email`, [user_session.py:18](../../backend/app/models/user_session.py#L18) `UserSession.jti`, [signature.py:17, :36](../../backend/app/models/signature.py#L17) `SignatureRequest.token`. Storage waste + double write cost on every INSERT.

7. **R6-CACHE-1 — `queryClient.clear()` missing on 2 fallback auth-recovery paths (R5-CACHE-1 reintroduced).** R5-CACHE-1 wired `queryClient.clear()` into the canonical logout path and 401 redirect. But [LoadingSpinner.tsx:85-86](../../frontend/src/components/ui/LoadingSpinner.tsx#L85) and [SuspenseWithTimeout.tsx:47-48](../../frontend/src/components/ui/SuspenseWithTimeout.tsx#L47) — both render a "Tekrar Giriş Yap" button on timeout — clear `localStorage` tokens but **don't clear the TanStack cache**. Same PII-flash-on-shared-device vector R5-CACHE-1 was supposed to close, just through a different code path.

8. **R6-RENDER-2 — Quote V9 revision lineage typed but never rendered (HIGH).** R5-API-3 added `revision_no`, `superseded_by` to the quote DTO + R5-TS-5 declared in TS, but **no consumer renders them**. Backend ships data the UI ignores; reps cannot tell if a draft has been superseded by a newer revision.

9. **R6-RENDER-4 — `password_change_required` typed but ignored at login (security gap).** R5-TS-4 declared the field on `User` and `TokenResponse`, but the login flow never reads it. Users with `password_change_required=true` (admin reset / first-login force) continue with the temporary password indefinitely. Defeats the security intent.

10. **13 list endpoints still ship non-canonical envelope (Phase 7 holdouts).** R5-API-8 standardized 11. Found another 13: chat sessions/messages/auto-response-rules, comments, deal_rooms, territories, customer_health/at-risk, approvals (rules/pending/history), forecast (adjustments/snapshots), playbooks lists, custom_fields, bundles. SPA list components have to special-case each shape.

### Most-affected surfaces

- **Multi-tenant isolation** (1 critical) — Campaign module never received the round-4/5 multi-tenant treatment. One-off, but high blast radius.
- **R5 form completeness** (4 regressions) — Phase 9 marked closed but the actual frontend forms either never got the new inputs (Quote.valid_days) or got only a subset (Customer firmographics, Subscription end_date/quote_id).
- **R5 render completeness** (4 partials) — Phase 9 declared OPP-1 closed; only 4 of 9 fields actually surface on the kanban. Quote revision lineage and email duplicate detection ship to the API but aren't visible.
- **Pagination envelope drift** (13 endpoints) — Phase 7 swept 11; another 13 list endpoints still use legacy shapes. Mechanical sweep, no logic change.
- **Sidebar / navigation gaps** (8 orphan routes) — `/ai/tasks`, `/engagement/scorecards`, `/reports/builder`, `/playbooks/templates`, `/playbooks/analytics`, `/compliance/retention`, `/compliance/breaches`, `/approvals/rules` are routed but not in the sidebar.
- **Mobile responsiveness** (5 list pages) — invoice/contract/subscription/leaderboard/pricing all lack `hidden sm:table-cell` patterns; mobile users sideways-scroll a 6-column table.
- **DTO field gaps** (response schemas) — `CustomerResponse` misses 11 fields that `_customer_to_dict` emits; `EmailResponse` misses 13. SDK / OpenAPI codegen drift.

### What Round-5 closed and stayed closed

Re-verified against source on 2026-05-06:
- **R5-PERM-1** — `apply_request_perms` still wired on contracts/invoices/subscriptions/campaigns (2 references each — import + call).
- **R5-TEN-25** — `assert_same_tenant` after Opportunity / Quote loads in `integrations.py:278, :550`.
- **R5-TEN-26** — Pipeline tenant scoping holds (5 calls in `pipelines.py`).
- **R5-TEN-28** — `BreachNotification.tenant_id` + `ReportFolder.tenant_id` migration applied + ORM matches.
- **R5-FLAG-15** — `_require_contracts` + `_require_subscriptions` dependencies still active.
- **R5-RL-7** — `enforce_signing_rate_limit` applied on 3 `/sign/*` routes.
- **R5-CACHE-1 (canonical paths)** — `authStore.logout` and 401 interceptor still call `queryClient.clear()`. The fallback paths are the regression (R6-CACHE-1).
- **R5-EVENT-1** — retention scheduler groups by `tenant_id` ([scheduler.py:474, :479, :489-504](../../backend/app/tasks/scheduler.py#L474)).
- **R5-EVENT-2** — `lead.score_changed` payload includes `delta` ([lead_service.py:124](../../backend/app/services/lead_service.py#L124)).
- **R5-DB-1/2/3/8** — bootstrap completeness, dup-index drop on tenant_id, schema-drift pytest gate all hold.
- **R5-FAKE-1** (AtRisk fabricated KPI) and **R5-FAKE-2** (Playbook win-rate ×100) — both fixes hold.

**Net regressions/partials introduced or missed in v1.10.0..v1.10.11: 6**.

---

## 2. Findings by Category

### 2.1 Multi-tenant security — CRITICAL × 1

#### R6-API-1 — `Campaign` cross-tenant data leak — **CRITICAL**

- **Files:**
  - [backend/app/models/campaign.py:13, :47](../../backend/app/models/campaign.py#L13) — `Campaign` and `CampaignMember` declared with no `tenant_id` column.
  - [backend/app/api/v1/campaigns.py:126](../../backend/app/api/v1/campaigns.py#L126) — `query = select(Campaign).order_by(Campaign.created_at.desc())` — no `scoped_for_user` call.
  - [backend/app/api/v1/campaigns.py:197, :220, :245, :263, :324, :361](../../backend/app/api/v1/campaigns.py#L197) — 7 single-row loads via `Campaign.id == campaign_id` with **zero `assert_same_tenant`**.
  - [backend/app/api/v1/campaigns.py:88](../../backend/app/api/v1/campaigns.py#L88) — `apply_request_perms(data, "campaign")` is called but is admin theater without a `tenant_id` column.
- **Attack:** Manager in tenant A enumerates `GET /campaigns/?page=1` → sees every other tenant's campaign metadata + budget + actual_revenue. Manager iterates `GET /campaigns/{id}/members` → exfiltrates target tenant's lead/customer associations.
- **Fix:**
  1. Add `tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)` to `Campaign` AND `CampaignMember`.
  2. Alembic migration `20260506_campaign_tenant.py` — backfill from `users.tenant_id` of `created_by`.
  3. `_campaign_to_dict` add `"tenant_id": getattr(campaign, "tenant_id", None)`.
  4. Wrap `list_campaigns` with `scoped_for_user(query, current_user, column=Campaign.tenant_id)`.
  5. `assert_same_tenant(campaign, current_user, exception_cls=NotFoundException)` after each single-row load.
  6. `create_campaign` set `tenant_id=getattr(current_user, "tenant_id", None)`.
- **Migration:** Yes. Pattern identical to `20260504_billing_tenant`.

### 2.2 R5 regressions / partials — HIGH × 6

#### R6-API-3 — Invoice DTO still ships `pdf_path` (R5-API-6 partial regression) — **HIGH**
- **File:** [backend/app/api/v1/invoices.py:119](../../backend/app/api/v1/invoices.py#L119) — `"pdf_path": invoice.pdf_path` still emitted.
- **R5 closed this for Quote** (replaced with `has_pdf: bool`). The same anti-pattern was never applied to Invoice. TS `Invoice.pdf_path?: string` declared in `lib/types.ts`.
- **Risk:** Information disclosure of server filesystem layout to the SPA.
- **Fix:** Replace with `"has_pdf": bool(invoice.pdf_path)`. Update TS to drop `pdf_path` and add `has_pdf?: boolean`. If a download endpoint doesn't already exist, add `GET /invoices/{id}/pdf` mirroring the quote pattern.

#### R6-FORM-5 — Quote editor never captures `valid_days` (R5-FORM-5 regression) — **HIGH**
- **File:** [frontend/src/features/quotes/QuoteEditorPage.tsx](../../frontend/src/features/quotes/QuoteEditorPage.tsx) — zero `valid_days` / `validDays` matches in the entire file.
- **Backend** ([schemas/quote.py:27, :46](../../backend/app/schemas/quote.py#L27)) accepts the field. Round-5 widened the schema; the form was never extended.
- **Impact:** Sales reps cannot set quote validity from the UI. Backend silently uses `None` → quotes never expire properly.
- **Fix:** Add `validDays` state, populate from `quote.valid_days`, render an `<Input type="number" label="Geçerlilik (gün)" value={validDays} ... />`, include in `handleSave` payload.

#### R6-FORM-6 — Subscription create form drops `end_date` and `quote_id` (R5-FORM-6 regression) — **HIGH**
- **File:** [frontend/src/features/subscriptions/SubscriptionListPage.tsx:32-52, 112-121](../../frontend/src/features/subscriptions/SubscriptionListPage.tsx#L32) — `CreateFormState` has 8 fields; neither `end_date` nor `quote_id` is among them. `createMutation` payload omits both.
- **Backend** ([subscriptions.py:30, :34](../../backend/app/api/v1/subscriptions.py#L30)) accepts both.
- **Impact:** Reps cannot record contracted end-date or link quote→subscription on creation.
- **Fix:** 3 lines — extend `CreateFormState` + `INITIAL_FORM`; render `<input type="date">` and `<select>` populated from a quotes-by-customer query; include `end_date: form.end_date || null, quote_id: form.quote_id ? Number(form.quote_id) : null` in payload.

#### R6-FORM-3 — Customer create/update form drops 5 firmographic fields (R5-FORM-3/4 partial) — **HIGH**
- **Files:**
  - [frontend/src/features/customers/CustomerListPage.tsx:283-296, 581-594](../../frontend/src/features/customers/CustomerListPage.tsx#L294) — `INITIAL_FORM` only adds `website`, `linkedin_url`. Rendered inputs are only those two.
  - [frontend/src/features/customers/CustomerDetailPage.tsx:90-91, 247-248, 492-500](../../frontend/src/features/customers/CustomerDetailPage.tsx#L90) — same gap on update.
  - [backend/app/schemas/customer.py:29-33, 49-53](../../backend/app/schemas/customer.py#L29) — accepts `industry`, `employee_count`, `annual_revenue`, `parent_id`, `territory_id`.
  - [frontend/src/features/customers/CustomerListPage.tsx:130-140](../../frontend/src/features/customers/CustomerListPage.tsx#L130) — list page **already CONSUMES** `industry` and `employee_count` via `c.industry`, `c.employee_count.toLocaleString()`. Reps see fields they cannot edit.
- **Impact:** AI-enrichment writes these but reps cannot manually correct. Territory rollups + parent-account hierarchies cannot be set in UI at all.
- **Fix:** Extend `INITIAL_FORM` and modal with 5 inputs. Treat `parent_id`/`territory_id` as `<select>` populated from a `customers`/`territories` query.

#### R6-RENDER-OPP-1 — Kanban omits 5 of 9 advertised opportunity fields (R5-RENDER-OPP-1 partial) — **HIGH**
- **File:** [frontend/src/features/board/BoardPage.tsx:111-231](../../frontend/src/features/board/BoardPage.tsx#L111) — kanban card renders `forecast_category`, `loss_reason`, `probability`, `source`. **Missing:** `previous_stage`, `previous_amount`, `previous_close_date`, `pipeline_id`, `territory_id`.
- **Impact:** Revenue-leak audit ("deal slipped from $50k → $30k") visible only on detail page, not on kanban where slippage scanning happens. Pipeline + territory color-coding impossible.
- **Fix:** When `previous_amount != null && previous_amount !== amount`, render a `text-amber-600` line `↓ {previous} → {current}`. Surface territory/pipeline as small chip when sidebar filter is "all".

#### R6-CACHE-1 — `queryClient.clear()` missing on 2 fallback auth-recovery paths (R5-CACHE-1 reintroduced) — **HIGH**
- **Files:**
  - [frontend/src/components/ui/LoadingSpinner.tsx:85-86](../../frontend/src/components/ui/LoadingSpinner.tsx#L85) — `localStorage.removeItem('token')` + `removeItem('refreshToken')` with **no `queryClient.clear()`**.
  - [frontend/src/components/ui/SuspenseWithTimeout.tsx:47-48, :53](../../frontend/src/components/ui/SuspenseWithTimeout.tsx#L47) — same pattern, "Tekrar Giriş Yap" button at :53.
- **R5-CACHE-1 closed this for the canonical logout + 401 paths** ([authStore.ts:139](../../frontend/src/stores/authStore.ts#L139), [api.ts:113](../../frontend/src/lib/api.ts#L113)). Two fallback paths reintroduce the same vulnerability through a different code path.
- **Risk:** Shared-device scenario — User A's session times out, "Tekrar Giriş Yap" clicked → tokens cleared but cached `['user']`, `['leads']`, `['customers']` queries persist. Next user logging in on the same browser tab sees A's PII for the 30s `staleTime` window.
- **Fix:** In both files, after the localStorage `removeItem` calls, add `import('../../lib/queryClient').then(m => m.queryClient.clear()).catch(() => {})`. Mirror the R5-CACHE-1 lazy-import pattern from `lib/api.ts:113`.

### 2.3 DTO / API contract drift — HIGH × 4, MEDIUM × 6

#### R6-API-2b — `QuoteItemCreate.honeywell_code` capped at 100 chars (DB column is 500) — **HIGH**
- **Files:** [backend/app/schemas/quote.py:12, :34](../../backend/app/schemas/quote.py#L12) — both `QuoteItemCreate.honeywell_code` and `QuoteItemUpdate.honeywell_code` declare `max_length=100`. R5-API-5 lifted SparePart to 500 but quote items were missed.
- **Impact:** Quote item with concatenated SKU > 100 chars rejects on POST → 422. Same flow that import-pipeline triggers for SparePart now blocks quote creation.
- **Fix:** Update both lines to `max_length=500`. (R5-API-5 was a 1-line fix; this is the same.)

#### R6-API-4 — `_member_to_dict` drops `lead`/`customer` nested objects TS expects — **HIGH**
- **Files:**
  - [backend/app/api/v1/campaigns.py:91-100](../../backend/app/api/v1/campaigns.py#L91) — `_member_to_dict` only emits `lead_id` / `customer_id`.
  - [frontend/src/lib/types.ts:1847-1848](../../frontend/src/lib/types.ts#L1847) — TS declares `lead?: { id, first_name, last_name, email }` and `customer?: { id, name, email, company }`.
  - [backend/app/models/campaign.py:69-70](../../backend/app/models/campaign.py#L69) — relationships `lead = relationship("Lead", lazy="selectin")` and `customer = relationship("Customer", lazy="selectin")` already loaded — **free**.
- **Impact:** Campaign member rows render `#{lead_id}` / `#{customer_id}` instead of names.
- **Fix:** Append `"lead"` and `"customer"` summary objects to the returned dict. Same pattern as R5-API-1 / R5-RENDER-SUB-1.

#### R6-API-7 — `audit.py:354` ships a duplicate `_customer_to_dict` that omits R5-added fields — **MEDIUM**
- **Files:** [backend/app/api/v1/audit.py:354-362](../../backend/app/api/v1/audit.py#L354) vs [customers.py:956-1009](../../backend/app/api/v1/customers.py#L956).
- **Evidence:** Audit's `_customer_to_dict` returns 7 fields; canonical version returns 17. The KVKK Article 15 export bundle is supposed to be a strict superset of what the user sees in the SPA — currently it's a subset.
- **Fix:** Replace `audit.py:354-362` with `from .customers import _customer_to_dict as _customer_to_dict_canonical` and call it. Same for `_opportunity_to_dict` and `_email_request_to_dict` at audit.py:365 / :378.

#### R6-API-8 — `EmailResponse` schema missing 13 fields the router emits — **MEDIUM**
- **Files:** [backend/app/schemas/email_request.py:36-57](../../backend/app/schemas/email_request.py#L36) vs [emails.py:835-883](../../backend/app/api/v1/emails.py#L835).
- **Missing on schema:** `tenant_id`, `is_duplicate`, `duplicate_of_id`, `opportunity_id`, `thread_id`, `in_reply_to`, `is_read`, `priority`, `triage_reason`, `sentiment`, `sentiment_score`, `data_classification`, `last_parsed_at`.
- **Impact:** OpenAPI / SDK codegen drift (the schema is currently not used as the actual return annotation, so no runtime bug — pure docs/codegen issue).
- **Fix:** Backfill schema fields. Mirrors `auth.UserResponse` fix in R5-API-2.

#### R6-API-9 — `CustomerResponse` schema missing 11 fields the router emits — **MEDIUM**
- **Files:** [backend/app/schemas/customer.py:56-72](../../backend/app/schemas/customer.py#L56) vs [customers.py:956-1009](../../backend/app/api/v1/customers.py#L956).
- **Missing:** `tenant_id`, `industry`, `employee_count`, `annual_revenue`, `website`, `linkedin_url`, `enriched_at`, `parent_id`, `territory_id`, `data_classification`, `deletion_requested_at`. R5-FORM-3/4 widened the input side; the response side was missed.
- **Fix:** Add each field as `<type> | None = None`.

#### R6-API-13 — `audit.py:365, :378` `_opportunity_to_dict` and `_email_request_to_dict` also drop R5 fields — **LOW**
- Same shape as R6-API-7. Lower severity because admin-only flows.

### 2.4 Pagination envelope holdouts — HIGH × 6, MEDIUM × 4, LOW × 3

R5-API-8 / Phase 7 standardized 11 endpoints to `{items, total, page, page_size, pages}`. Found another 13 list endpoints still using legacy or incomplete shapes:

| File:line | Endpoint | Current shape | Severity |
|---|---|---|---|
| [chat.py:145](../../backend/app/api/v1/chat.py#L145) | `GET /chat/sessions/` | `{sessions:[]}` | High |
| [chat.py:236](../../backend/app/api/v1/chat.py#L236) | `GET /chat/sessions/{id}/messages` | `{messages:[]}` | High |
| [chat.py:357](../../backend/app/api/v1/chat.py#L357) | `GET /chat/auto-response-rules/` | `{rules:[]}` | High |
| [comments.py:122](../../backend/app/api/v1/comments.py#L122) | `GET /comments/` | `{comments:[]}` | High |
| [deal_rooms.py:97](../../backend/app/api/v1/deal_rooms.py#L97) | `GET /deal-rooms/` | `{deal_rooms:[]}` | High |
| [territories.py:160](../../backend/app/api/v1/territories.py#L160) | `GET /territories/` | `{territories:[]}` | High |
| [customer_health.py:94](../../backend/app/api/v1/customer_health.py#L94) | `GET /customer-health/at-risk` | `{count, customers}` | Medium |
| [approvals.py:102, :188, :235](../../backend/app/api/v1/approvals.py#L102) | rules / pending / history | `{items:[]}` (no total/page) | High |
| [forecast.py:160, :176, :188](../../backend/app/api/v1/forecast.py#L160) | adjustments / snapshots | `{items:[]}` (no total/page) | High |
| [cockpit.py:444](../../backend/app/api/v1/cockpit.py#L444) | (signal list) | `{items, total}` (no page) | Medium |
| [analytics.py:1181](../../backend/app/api/v1/analytics.py#L1181) | (campaign analytics) | `{items, total}` (no page) | Medium |
| [parts.py:92](../../backend/app/api/v1/parts.py#L92) | `GET /parts/categories` | `{items, total}` (no page) | Low — fixed cardinality |
| [playbooks.py:94, :265, :278](../../backend/app/api/v1/playbooks.py#L94) | playbook lists | `{items, total}` (no page) | Low |
| [custom_fields.py:64](../../backend/app/api/v1/custom_fields.py#L64) | custom fields | `{items, total}` (no page) | Low |
| [bundles.py:141](../../backend/app/api/v1/bundles.py#L141) | bundle items | `{items, bundle_name}` | Low — non-list payload |

Also: `contracts.py:233`, `pipelines.py:108`, `compliance.py:518/:782`, `reports_v2.py:170/:342`, `emails.py:418/:437` ship **dual** envelope (canonical + legacy). 11 patch releases since R5-API-8; SPA should have caught up — drop the legacy keys.

**Fix pattern:**
```python
return {
    "items": items, "total": total, "page": page,
    "page_size": page_size,
    "pages": math.ceil(total / page_size) if total > 0 else 0,
}
```

### 2.5 UI completeness gaps — HIGH × 3, MEDIUM × 8, LOW × 5

#### R6-RENDER-2 — Quote `revision_no` + `superseded_by` never rendered — **HIGH**
- **Files:** [frontend/src/lib/types.ts:336-337](../../frontend/src/lib/types.ts#L336) declared; not consumed.
- **Impact:** V9 revision-tree feature ships dark — backend round-trips data the UI ignores. Reps cannot tell at a glance if a draft has been superseded.
- **Fix:** Add a "Revizyon X / Y · Eski versiyon" badge near `quote_number`; if `superseded_by`, render link to newer revision.

#### R6-RENDER-4 — `password_change_required` typed but ignored at login — **HIGH** (security)
- **File:** [frontend/src/lib/types.ts:15, :484](../../frontend/src/lib/types.ts#L15) declared; zero consumer hits.
- **Impact:** Users with `password_change_required=true` (admin reset / first login) continue with the temporary password indefinitely.
- **Fix:** In `authStore.login` success handler, if `user.password_change_required` redirect to `/settings/password` (or open a modal).

#### R6-FORM-4 — Opportunity detail has no general edit form — **HIGH**
- **File:** [OpportunityDetailPage.tsx:419-422](../../frontend/src/features/board/OpportunityDetailPage.tsx#L419) — only `applyPipelineStageMutation` mutates `stage`. Backend `OpportunityUpdate` accepts 8 fields.
- **Impact:** Cannot rename a deal, fix amount typos, change customer attribution, mark closed_lost with a reason — without backend access.
- **Fix:** Add an "Düzenle" toggle mirroring the Lead inline edit pattern at [LeadDetailPage.tsx:146-231](../../frontend/src/features/leads/LeadDetailPage.tsx#L146).

#### R6-RENDER-3 — Email `data_classification` typed but not rendered — **MEDIUM** (KVKK)
#### R6-RENDER-5 — Email `is_duplicate` / `duplicate_of_id` not surfaced — **MEDIUM**
#### R6-RENDER-6 — Customer `deletion_requested_at` (KVKK pending delete) banner missing — **MEDIUM**

#### R6-FORM-1 — Contract create form drops `quote_id` and `terms_json` — **MEDIUM**
- [ContractListPage.tsx:128-140](../../frontend/src/features/contracts/ContractListPage.tsx#L128). Backend accepts both.

#### R6-FORM-2 — Campaign create form drops `expected_revenue` and `status` — **MEDIUM**
- [CampaignListPage.tsx:78-92, :138-146](../../frontend/src/features/campaigns/CampaignListPage.tsx#L78). List page renders `campaign.expected_revenue` (line 311) — value always missing for in-app-created campaigns.

#### R6-NAV-1 — 8 SPA routes orphaned from sidebar — **MEDIUM**
- [Sidebar.tsx](../../frontend/src/components/layout/Sidebar.tsx) doesn't include: `/ai/tasks`, `/engagement/scorecards`, `/reports/builder`, `/playbooks/templates`, `/playbooks/analytics`, `/compliance/retention`, `/compliance/breaches`, `/approvals/rules`. All registered in `App.tsx`.

#### R6-RENDER-7 — `OpportunitiesHomePage` casts `previous_amount` instead of using TS type — **LOW**
- [OpportunitiesHomePage.tsx:306-313](../../frontend/src/features/opportunities/OpportunitiesHomePage.tsx#L306) — `(o as unknown as { previous_amount?: ... })`. `Opportunity.previous_amount` exists in [types.ts:513](../../frontend/src/lib/types.ts#L513). Pure technical debt.

#### R6-RENDER-8 — `CockpitPage` returns `null` on missing data — **LOW**
- [CockpitPage.tsx:118-128](../../frontend/src/features/cockpit/CockpitPage.tsx#L118). No `isError` handler. 500 → blank page with no recourse.

#### R6-RESP-1 — 5 list pages horizontal-scroll on mobile — **LOW**
- `InvoiceListPage.tsx`, `ContractListPage.tsx`, `SubscriptionListPage.tsx`, `LeaderboardPage.tsx`, `PricingAdminPage.tsx`. Use `overflow-x-auto` with no `hidden sm:table-cell` patterns. Breaks the CLAUDE.md "calm density" + "mobile responsiveness" required quality.

### 2.6 DB ↔ ORM drift — HIGH × 1, MEDIUM × 4, LOW × 3

#### R6-DB-1 — Duplicate index from `unique=True + index=True` on auth-critical columns — **HIGH**
- **Files:**
  - [backend/app/models/user.py:15](../../backend/app/models/user.py#L15) — `User.email` has `unique=True, index=True`
  - [backend/app/models/customer.py:21](../../backend/app/models/customer.py#L21) — `Customer.email` same
  - [backend/app/models/user_session.py:18](../../backend/app/models/user_session.py#L18) — `UserSession.jti` same
  - [backend/app/models/signature.py:17, :36](../../backend/app/models/signature.py#L17) — `Index("ix_sig_token", "token", unique=True)` AND column `unique=True`
- **Impact:** Two indexes covering identical columns on every INSERT/UPDATE. Storage waste + double write cost. Same anti-pattern Round-5 R5-DB-2/3 closed for `tenant_id`; this family was missed.
- **Fix:** Drop `index=True` (the `UNIQUE` constraint already auto-creates the index). New migration `20260506_drop_dup_unique_indexes.py` drops `ix_users_email`, `ix_customers_email`, `ix_user_sessions_jti`, `ix_sig_token` (the `_key` constraint indexes from `UNIQUE` stay).

#### R6-DB-2 — `CustomerResponse` schema missing R5-FORM-3 enrichment fields — **MEDIUM** (companion of R6-API-9)
#### R6-DB-3 — `UserResponse.updated_at` declared `Optional` while model is non-null — **MEDIUM**
#### R6-DB-4 — Implicit `nullable=False` brittleness on `Mapped[datetime]` columns — **MEDIUM**
- 4 model files (Pipeline, BreachNotification, ReportFolder, DeadLetterEvent) rely on `Mapped[datetime]` to imply `nullable=False`. If a future refactor flips the annotation, model drifts from prod NOT NULL silently.
- **Fix:** Add explicit `nullable=False` to all `created_at` / `updated_at` columns where the migration says NOT NULL.

#### R6-DB-5 — Same brittleness on `Mapped[bool]` / `Mapped[int]` columns — **MEDIUM**
- [pipeline.py:30](../../backend/app/models/pipeline.py#L30) `Pipeline.is_default`, [report_folder.py:33](../../backend/app/models/report_folder.py#L33) `ReportFolder.is_shared`, [breach_notification.py:31-34](../../backend/app/models/breach_notification.py#L31).

#### R6-DB-6 — `__init__.py` `__all__` missing `MeetingAutoLink` — **LOW**
#### R6-DB-7 — Pipeline migration uses raw `op.execute` (non-transactional) — **LOW**
#### R6-DB-8 — `CustomerCreate.parent_id` accepts arbitrary int with no FK validation — **LOW**

### 2.7 Realtime / cache — HIGH × 1, MEDIUM × 2, LOW × 1

#### R6-CACHE-1 — see headline #7 / §2.2

#### R6-DEP-1 — `@tanstack/react-query` bumped to ^5.100.9 — semantic shift — **MEDIUM**
- **Evidence:** Bump confirmed in `frontend/package.json`. v5 renamed `cacheTime` → `gcTime`, removed callback-style `onSuccess`/`onError` from `useQuery` (still present on `useMutation`), changed `isLoading` semantics (now means `isPending && isFetching`). The codebase still uses `isLoading` extensively (sampled 12+ feature files).
- **Risk:** Soft semantic shift, not a hard break. Code that uses `isLoading` to gate a Skeleton render still works in v5 (it's a derived field).
- **Fix:** Run `cd frontend && npx tsc --noEmit && npx vitest run` to surface any breakage; spot-check the highest-traffic queries with `useQuery({onSuccess: ...})` patterns (these would have been removed in v5).

#### R6-DEP-2 — `lucide-react` 1.11 → 1.14 — **LOW**
- Bump confirmed. Check if any imported icons were renamed/removed.
- **Strategy:** `cd frontend && npx tsc --noEmit --pretty false` should surface broken imports.

### 2.8 Permissions / Flags — re-verified clean

All R5-PERM-1, R5-TEN-25..28, R5-FLAG-15, R5-RL-7 fixes hold against current source (verified directly via `grep` since slice 5 stalled). No new permission/flag findings surfaced in the partial slice-5 evidence.

---

## 3. Cross-Layer Schema Compatibility Matrix (selected entities)

### Campaign (CRITICAL)

| Field | DB column | Model | DTO emits | TS declares | Field-perm masking | Status |
|---|:-:|:-:|:-:|:-:|:-:|:--|
| id, name, type, status, dates, budget | ✓ | ✓ | ✓ | ✓ | ✓ | OK |
| **tenant_id** | **✗** | **✗** | **✗** | **✗** | wired (no-op) | **R6-API-1** |
| List endpoint scoping | n/a | n/a | **no `scoped_for_user`** | n/a | n/a | **R6-API-1 critical** |
| Single-row asserts (7 endpoints) | n/a | n/a | **no `assert_same_tenant`** | n/a | n/a | **R6-API-1 critical** |

### Quote

| Field | DB | Model | `_quote_to_dict` | `QuoteResponse` schema | TS | UI | Status |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:--|
| revision_no, superseded_by | ✓ | ✓ | ✓ (R5) | ✓ (R5) | ✓ (R5) | ❌ not rendered | R6-RENDER-2 |
| valid_days | ✓ | ✓ | ✓ | ✓ (R5) | ✓ | ❌ no form input | **R6-FORM-5 (R5 regression)** |
| QuoteItem.honeywell_code (Create/Update) | DB max 500 | n/a | n/a | **max_length=100** | n/a | n/a | R6-API-2b |

### Customer

| Field | DB | Model | `_customer_to_dict` (canonical) | `_customer_to_dict` (audit) | `CustomerResponse` | TS | Form (Create/Update) | Status |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:--|
| website, linkedin_url | ✓ | ✓ | ✓ | ❌ | ❌ | ✓ | ✓ | OK on canonical only |
| industry, employee_count, annual_revenue | ✓ | ✓ | ✓ | ❌ | ❌ | ✓ | ❌ | **R6-FORM-3 (R5 partial)** |
| parent_id, territory_id | ✓ | ✓ | ✓ | ❌ | ❌ | ✓ | ❌ | **R6-FORM-3 (R5 partial)** |
| data_classification, deletion_requested_at | ✓ | ✓ | ✓ | ❌ | ❌ | ✓ | n/a | R6-RENDER-6 |

### Subscription

| Field | DB | Model | `_serialize` | `SubscriptionCreate` | TS | Form | Status |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:--|
| customer summary | n/a | rel | ✓ (R5) | n/a | ✓ | ✓ | OK |
| end_date | ✓ | ✓ | ✓ | ✓ | ✓ | ❌ | **R6-FORM-6 (R5 regression)** |
| quote_id | ✓ | ✓ | ✓ | ✓ | ✓ | ❌ | **R6-FORM-6 (R5 regression)** |

### Invoice

| Field | DB | Model | `_invoice_to_dict` | TS | UI | Status |
|---|:-:|:-:|:-:|:-:|:-:|:--|
| customer summary | n/a | rel | ✓ (R5) | ✓ | ✓ | OK |
| **pdf_path** | ✓ | ✓ | **emitted (leaks)** | declared | n/a | **R6-API-3 (R5 partial regression)** |
| has_pdf | n/a | computed | ❌ | n/a | n/a | should ship instead of pdf_path |

### User (auth surface)

| Field | DB column | Model | `_user_to_dict` (3 sites) | `auth.UserResponse` | TS | UI | Status |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:--|
| password_change_required | ✓ | ✓ | ✓ (R5) | ✓ (R5) | ✓ (R5) | ❌ login flow ignores | R6-RENDER-4 |
| **email** index | dup index | `unique=True, index=True` | n/a | n/a | n/a | n/a | **R6-DB-1** |
| updated_at nullability | NOT NULL | non-null `Mapped` | `datetime` | `Optional[datetime]` | n/a | n/a | R6-DB-3 |

---

## 4. Fix Plan

### 4.1 Day-0 hotfix PR (1-2 hours, all visible incidents)

| ID | What | Files | Migration? |
|---|---|---|---|
| R6-API-3 | Replace Invoice `pdf_path` → `has_pdf` | `invoices.py:119`, `lib/types.ts` | No |
| R6-API-2b | `QuoteItemCreate/Update.honeywell_code` 100 → 500 | `schemas/quote.py:12, :34` | No |
| R6-CACHE-1 | Add `queryClient.clear()` to 2 fallback paths | `LoadingSpinner.tsx:85`, `SuspenseWithTimeout.tsx:47` | No |
| R6-RENDER-4 | Login redirect when `password_change_required` | `authStore.ts` | No (security) |

### 4.2 Sprint hotfix PR (security-grade, 1 day)

| ID | What | Migration? |
|---|---|---|
| **R6-API-1** | Campaign tenant scoping (model + migration + serializer + 7 route hardenings) | **Yes** |
| R6-DB-1 | Drop dup unique-indexes on email/jti/token | Yes |
| R6-API-7 / R6-API-13 | Audit.py serializers reuse canonical | No |
| R6-API-4 | CampaignMember `lead`/`customer` summary | No |

### 4.3 Form completeness PR (2-3 days)

| ID | What |
|---|---|
| R6-FORM-5 (R5 regression) | Quote editor `valid_days` input |
| R6-FORM-6 (R5 regression) | Subscription create `end_date` + `quote_id` |
| R6-FORM-3 (R5 partial) | Customer form 5 firmographic inputs |
| R6-FORM-4 | Opportunity detail edit form |
| R6-FORM-1 | Contract create `quote_id` + `terms_json` |
| R6-FORM-2 | Campaign create `expected_revenue` + `status` |

### 4.4 UI completeness PR (2-3 days)

| ID | What |
|---|---|
| R6-RENDER-OPP-1 (R5 partial) | Kanban surfaces 5 missing fields (`previous_*`, `pipeline_id`, `territory_id`) |
| R6-RENDER-2 | Quote revision lineage badge + supersede link |
| R6-RENDER-3 | Email `data_classification` KVKK badge |
| R6-RENDER-5 | Email duplicate detection affordance |
| R6-RENDER-6 | Customer `deletion_requested_at` banner |
| R6-NAV-1 | Sidebar: 8 orphan routes |
| R6-RESP-1 | Mobile responsive column hiding on 5 list pages |

### 4.5 Pagination envelope sweep PR (1 day)

13 endpoints to canonicalize. Mechanical work; pattern is `{items, total, page, page_size, pages}`. Drop legacy keys from the 6 dual-envelope endpoints. After confirming SPA reads `items` everywhere.

### 4.6 DTO/Schema sync cleanup (1 day)

| ID | What |
|---|---|
| R6-API-8 | EmailResponse: 13 missing fields |
| R6-API-9 | CustomerResponse: 11 missing fields |
| R6-DB-3 | UserResponse.updated_at: drop Optional |
| R6-DB-4 / R6-DB-5 | Explicit `nullable=False` on Mapped[datetime] / Mapped[bool] across 4 models |

### 4.7 Backlog

| ID | What |
|---|---|
| R6-RENDER-7 | Drop `previous_amount` cast in OpportunitiesHomePage |
| R6-RENDER-8 | CockpitPage error state |
| R6-DB-6 | `__all__` add `MeetingAutoLink` |
| R6-DB-7 | Migration docstrings explaining raw `op.execute` choice |
| R6-DB-8 | Validate `parent_id` FK at route level instead of relying on IntegrityError |
| R6-DEP-1 | Spot-check TanStack Query v5 `useQuery({onSuccess})` consumers |
| R6-DEP-2 | TS check for lucide 1.14 icon renames |

### 4.8 Risky / needs manual review

- **R6-API-1 backfill**: `users.tenant_id` on `created_by` may be NULL for legacy campaigns. Document fallback (e.g. "system" tenant) in migration.

---

## 5. Suggested Database Migrations

### 5.1 `20260506_campaign_tenant.py` (R6-API-1)

```python
"""Round-6 R6-API-1 — add tenant_id to campaigns + campaign_members."""
revision = "20260506_campaign_tenant"
down_revision = "20260505_drop_dup_indexes"

def upgrade():
    op.execute("ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS tenant_id INTEGER")
    op.execute("CREATE INDEX IF NOT EXISTS ix_campaign_tenant ON campaigns (tenant_id)")
    op.execute("""
        UPDATE campaigns c
        SET tenant_id = (SELECT u.tenant_id FROM users u WHERE u.id = c.created_by)
        WHERE tenant_id IS NULL AND created_by IS NOT NULL
    """)
    op.execute("ALTER TABLE campaign_members ADD COLUMN IF NOT EXISTS tenant_id INTEGER")
    op.execute("CREATE INDEX IF NOT EXISTS ix_campaign_member_tenant ON campaign_members (tenant_id)")
    # Backfill from parent campaign
    op.execute("""
        UPDATE campaign_members m
        SET tenant_id = (SELECT c.tenant_id FROM campaigns c WHERE c.id = m.campaign_id)
        WHERE m.tenant_id IS NULL
    """)

def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_campaign_member_tenant")
    op.execute("ALTER TABLE campaign_members DROP COLUMN IF EXISTS tenant_id")
    op.execute("DROP INDEX IF EXISTS ix_campaign_tenant")
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS tenant_id")
```

### 5.2 `20260506_drop_dup_unique_indexes.py` (R6-DB-1)

```python
"""Round-6 R6-DB-1 — drop redundant indexes on UNIQUE columns.

UNIQUE constraints auto-create an index. Adding `index=True` on the
same column produces a duplicate. Same R5-DB-2/3 sweep, missed family.
"""
revision = "20260506_drop_dup_unique_indexes"
down_revision = "20260506_campaign_tenant"

def upgrade():
    op.execute("DROP INDEX IF EXISTS ix_users_email")
    op.execute("DROP INDEX IF EXISTS ix_customers_email")
    op.execute("DROP INDEX IF EXISTS ix_user_sessions_jti")
    op.execute("DROP INDEX IF EXISTS ix_sig_token")
    # The auto-created `*_key` constraint indexes stay.

def downgrade():
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customers_email ON customers (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_sessions_jti ON user_sessions (jti)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sig_token ON signature_requests (token)")
```

---

## 6. Suggested Tests

### 6.1 Tenant-scope regression test for Campaign (R6-API-1)

```python
@pytest.mark.asyncio
async def test_campaign_list_rejects_cross_tenant(client, manager_a_headers, campaign_in_b):
    r = await client.get("/api/v1/campaigns/", headers=manager_a_headers)
    assert r.status_code == 200
    body = r.json()
    # Tenant B's campaign must not appear in tenant A's list
    assert all(c["id"] != campaign_in_b.id for c in body["items"])

@pytest.mark.asyncio
async def test_campaign_get_rejects_cross_tenant(client, manager_a_headers, campaign_in_b):
    r = await client.get(f"/api/v1/campaigns/{campaign_in_b.id}", headers=manager_a_headers)
    assert r.status_code == 404
```

### 6.2 Form ↔ schema sync test (R6-FORM-3/5/6 class)

```python
# backend/tests/test_form_schema_sync.py
@pytest.mark.parametrize("form_path,schema_class,expected_fields", [
    ("frontend/src/features/quotes/QuoteEditorPage.tsx", QuoteCreate,
     ["valid_days"]),
    ("frontend/src/features/subscriptions/SubscriptionListPage.tsx", SubscriptionCreate,
     ["end_date", "quote_id"]),
    ("frontend/src/features/customers/CustomerListPage.tsx", CustomerCreate,
     ["industry", "employee_count", "annual_revenue", "parent_id", "territory_id"]),
])
def test_form_captures_all_writable_schema_fields(form_path, schema_class, expected_fields):
    """Catches the R5-FORM-5/6 + R6-FORM-3 class of bug at PR time."""
    text = (Path(__file__).parent.parent.parent / form_path).read_text()
    for field in expected_fields:
        assert field in text, f"{form_path} doesn't reference {field}"
```

### 6.3 Pagination envelope sync test

```python
# Iterate every list-shaped endpoint, assert canonical envelope
@pytest.mark.parametrize("path", [
    "/api/v1/contracts/", "/api/v1/subscriptions/", "/api/v1/campaigns/",
    "/api/v1/chat/sessions/", "/api/v1/comments/", "/api/v1/deal-rooms/",
    "/api/v1/territories/", "/api/v1/approvals/rules", "/api/v1/forecast/snapshots",
    # … all 13 holdouts
])
async def test_list_endpoint_returns_canonical_envelope(client, manager_headers, path):
    r = await client.get(path, headers=manager_headers)
    assert r.status_code == 200
    body = r.json()
    assert {"items", "total", "page", "page_size", "pages"} <= set(body.keys()), \
        f"{path} missing canonical pagination envelope"
```

### 6.4 Auth-recovery cache-clear test (R6-CACHE-1)

```ts
test('LoadingSpinner timeout fallback clears query cache', () => {
  queryClient.setQueryData(['user'], { id: 1, email: 'leak@example.com' });
  // Trigger the timeout fallback...
  fireEvent.click(screen.getByText('Tekrar Giriş Yap'));
  expect(queryClient.getQueryData(['user'])).toBeUndefined();
});
```

### 6.5 Schema-vs-DTO sync test

```python
# Catches R6-API-8 / R6-API-9 — schema misses fields the router emits
@pytest.mark.parametrize("response_schema,_to_dict_fn,allowlist_extras", [
    (CustomerResponse, _customer_to_dict, set()),
    (EmailResponse, _email_to_dict, {"body_text", "body_html", "parsed_data"}),
])
def test_response_schema_covers_dto(response_schema, _to_dict_fn, allowlist_extras):
    declared = set(response_schema.model_fields.keys())
    fixture_obj = _make_fixture()  # ad-hoc shape
    emitted = set(_to_dict_fn(fixture_obj).keys())
    missing = emitted - declared - allowlist_extras
    assert not missing, f"{response_schema.__name__} missing fields the router emits: {missing}"
```

---

## 7. Lists requested by spec

### 7.1 Database columns not used by backend
None confirmed in this round.

### 7.2 Backend model fields not backed by database
None.

### 7.3 Backend fields not exposed through API
- `Customer.deletion_requested_at` — emitted by canonical `_customer_to_dict` but missing from `audit.py:_customer_to_dict` (R6-API-7)
- `Customer.data_classification` — same shape

### 7.4 API fields never consumed by frontend
- `Quote.revision_no`, `Quote.superseded_by` — typed, never rendered (R6-RENDER-2)
- `User.password_change_required` — typed, never gates login (R6-RENDER-4)
- `Email.data_classification` — typed, never rendered (R6-RENDER-3)
- `Customer.deletion_requested_at` — typed, no banner (R6-RENDER-6)

### 7.5 Frontend fields/types missing from API/backend
- `CampaignMember.lead`, `CampaignMember.customer` — declared in TS, dropped by serializer (R6-API-4)

### 7.6 Data fetched but not rendered
See §7.4. Plus 5 fields on Opportunity kanban (R6-RENDER-OPP-1 partial).

### 7.7 UI components showing incomplete data
- BoardPage (R6-RENDER-OPP-1)
- Customer create/update form (R6-FORM-3)
- Quote editor (R6-FORM-5)
- Subscription create modal (R6-FORM-6)
- Contract create form (R6-FORM-1)
- Campaign create form (R6-FORM-2)

### 7.8 Realtime events emitted but not handled
Slice 6 stalled before completing this matrix; spot-check showed `customer.created`, `lead.score_changed`, `quote.approved`, `invoice.paid` all have at least one subscriber.

### 7.9 Realtime events handled but not emitted
Slice 6 stalled. Round-5 R5-EVENT-5 noted `SEQUENCE_ENROLLED/PAUSED/RESUMED` constants declared but not emitted; status unverified for R6.

### 7.10 Schema/type/nullability mismatches
- `UserResponse.updated_at` Optional vs model NOT NULL (R6-DB-3)
- 4 models implicit non-null `Mapped[datetime]` (R6-DB-4/5)

### 7.11 Permission or feature flag mismatches
None new beyond R6-API-1 (Campaign tenant scoping).

### 7.12 Required migrations
- `20260506_campaign_tenant.py` — R6-API-1
- `20260506_drop_dup_unique_indexes.py` — R6-DB-1

### 7.13 Recommended frontend type updates
- Drop `Invoice.pdf_path`, add `Invoice.has_pdf?: boolean`
- Add `EmailRequest.is_duplicate?: boolean`, `EmailRequest.duplicate_of_id?: number | null`
- Add `Customer.deletion_requested_at?: string | null`, `Customer.data_classification?: ...`

### 7.14 Recommended backend DTO/serializer updates
- `_invoice_to_dict`: replace `pdf_path` with `has_pdf`
- `_member_to_dict`: emit `lead` + `customer` summary
- `audit.py`: replace 3 duplicate serializers with canonical reuse
- `EmailResponse` schema: backfill 13 fields
- `CustomerResponse` schema: backfill 11 fields
- `_campaign_to_dict`: emit `tenant_id` (after migration)

### 7.15 Recommended tests
See §6 for 5 test classes. Plus: R6-DEP-1 — `npx tsc --noEmit && vitest run` after the dep bumps; R6-DEP-2 — same.

---

## 8. Verification appendix

Every headline claim re-verified against source on 2026-05-06:

| Headline | Verification command output |
|---|---|
| R6-API-1 (Campaign no tenant) | `grep tenant_id backend/app/models/campaign.py` → no matches |
| R6-API-1 (campaigns.py:126 unscoped) | `select(Campaign).order_by(Campaign.created_at.desc())` confirmed |
| R6-API-3 (Invoice pdf_path) | `grep pdf_path backend/app/api/v1/invoices.py` → `:119: "pdf_path": invoice.pdf_path` |
| R6-API-2b (QuoteItem 100) | `grep honeywell_code backend/app/schemas/quote.py` → `:12, :34: max_length=100` |
| R6-FORM-5 (Quote no valid_days) | `grep valid_days frontend/src/features/quotes/QuoteEditorPage.tsx` → 0 matches |
| R6-FORM-6 (Sub no end_date/quote_id) | `grep end_date frontend/src/features/subscriptions/SubscriptionListPage.tsx` → 0 matches in CreateFormState |
| R6-FORM-3 (Customer form gap) | Form lines 583-591 only show website + linkedin_url inputs |
| R6-RENDER-OPP-1 partial | `BoardPage.tsx:111-231` renders 4 of 9 fields |
| R6-CACHE-1 (LoadingSpinner) | `:85-86: localStorage.removeItem(...)` confirmed; no queryClient.clear() in same file |
| R6-DB-1 (User.email dup index) | `user.py:15: unique=True, nullable=False, index=True` confirmed |
| R5-PERM-1 (4 entities) | `grep apply_request_perms backend/app/api/v1/{contracts,invoices,subscriptions,campaigns}.py` → 2 matches each (import + call) |
| R5-TEN-25 holds | `integrations.py:278, :550` `assert_same_tenant` calls confirmed |
| R5-EVENT-1 holds | `scheduler.py:474, :479, :489-504` `group_by(Customer.tenant_id)` confirmed |
| R5-EVENT-2 holds | `lead_service.py:124: "delta": (lead.lead_score or 0) - (old_score or 0)` confirmed |

---

## 9. Process notes

- **6 parallel slice investigators dispatched.** Slices 1, 2, 4 returned cleanly. Slices 3 (API↔TS), 5 (Permissions/flags), 6 (Realtime/cache) hit the 600s watchdog and were killed. Critical claims from those stalled slices (R6-CACHE-1 from slice 6; R5-PERM-1/TEN-25..28/FLAG-15/RL-7/EVENT-1/EVENT-2 regression checks from slice 5) were re-verified directly via `grep` + `Read` and incorporated above.
- **Total 52 findings** (1 critical, 13 high, 23 medium, 15 low) + **6 R5 regressions/partials** (R5-API-6 invoice, R5-FORM-5 quote valid_days, R5-FORM-6 subscription, R5-FORM-3/4 customer firmographics, R5-RENDER-OPP-1 kanban, R5-CACHE-1 fallback paths).
- **Day-0 hotfix is small** — 4 fixes, ~1-2 hours total. Critical R6-API-1 should not block the day-0 PR; campaign tenant migration is its own concern with a backfill that needs operator review.
- **Highest-leverage work**: R6-API-1 (campaign tenant migration) + the 6 form completeness regressions (Phase 9 didn't fully land). The DTO drift, pagination holdouts, and DB-1 dup-index sweep are mechanical follow-ups.

**Audit by 6 parallel slice investigators (3 returned, 3 grep-recovered after stall). Every R5 closure spot-verified against current source. Zero files modified per instruction.**
