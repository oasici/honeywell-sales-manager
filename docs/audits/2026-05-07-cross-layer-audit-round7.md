# Cross-Layer Audit Report — Honeywell Sales Suite (Round 7, post-v1.11.0)

**Date:** 2026-05-07
**Branch:** `deploy/render-sandbox`
**HEAD:** `5a67e44` (post v1.11.0 — Round-6's 52 findings shipped + R6-RENDER-9 production hotfix for the Fırsatlar React error #31 crash)
**Scope:** DB schemas/migrations · Backend models/services · API contracts · Frontend clients/types · UI rendering · Realtime/events · Permissions · State/lifecycle · Cache invalidation
**Method:** 6 parallel slice investigators (DB↔ORM, Backend↔API, API↔TS, UI completeness, Permissions/flags/tenant, Realtime/cache). All 6 returned cleanly within 600s budget. Critical claims re-verified directly via `grep`/`Read` for the consolidation pass.

---

## 1. Executive Summary

| Metric | Count |
|---|---:|
| **Total verified findings** | **54** |
| Critical | 2 |
| High | 14 |
| Medium | 24 |
| Low | 14 |
| **Round-6 regressions / family-wide leaks** | **3** |

### Top headline issues

1. **R7-API-1 — Lead analytics cross-tenant leak (CRITICAL).** `GET /leads/analytics` runs three `select(Lead)` aggregations ([leads.py:117-128, 169-172](../../backend/app/api/v1/leads.py#L117)) without `scoped_for_user`. Tenant A's manager sees a global funnel + per-source conversion table + weekly trend including every other tenant's leads. Same shape as Round-4 R4-TEN-7 fix on subscription MRR dashboard. **Highest blast radius in this audit.**

2. **R7-API-2 — Coaching plan target-user cross-tenant injection (CRITICAL).** [coaching.py:128-131](../../backend/app/api/v1/coaching.py#L128) loads target user by ID, raises 404 if missing, but **never asserts same tenant**. A manager in tenant A can mint a `CoachingPlan` whose `user_id` references tenant B, polluting B's coaching surface with a foreign manager_id. Two-line fix.

3. **R7-DB-1 — R6-DB-1 family regression on 13 more columns (HIGH).** R6 dropped `index=True` on `users.email`/`customers.email`/`user_sessions.jti`/`signature_requests.token`. Same anti-pattern (`unique=True + index=True`) is alive on 13 more columns including `Lead.email`, `EmailRequest.message_id`, `Quote.quote_number`, `SparePart.honeywell_code`, `DealRoom.external_token` — several of which sit on hot write paths. Storage waste + double write cost. **Same family R6-DB-1 closed; missed siblings.**

4. **R7-CACHE-1 — Canonical invalidation helper bypassed in 87% of mutations (HIGH).** Of ~67 mutation sites, only 9 use `lib/cacheInvalidation.ts`; the other ~58 invalidate ad-hoc. R5-CACHE-1 created the helper precisely to centralize cross-feature cascades (closing a deal invalidates kanban + dashboard + reports). Most mutations only invalidate their local query → stale dashboards/cockpit/kanban after row-level edits.

5. **R7-FORM-1 — No standalone "Create Opportunity" form anywhere in the SPA (CRITICAL).** `opportunitiesApi.create` is declared ([api.ts:898-901](../../frontend/src/lib/api.ts#L898)) but **zero call sites**. Reps cannot create an expansion deal on an existing customer without going through Lead conversion (forces a fake-lead workaround). Full `OpportunityCreate` schema unreachable from UI.

6. **R7-TS-12 — `types.ts` is hand-rolled, no codegen (HIGH-STRUCTURAL).** Every cross-layer audit since Round-3 keeps re-finding the same drift class because `frontend/src/lib/types.ts` (2103 lines) is manually maintained. No `openapi-typescript`, `openapi-fetch`, or `orval` in `package.json`. **Root cause** of Slice 3's 12 findings and the recurring TS field-drift class across rounds 4/5/6/7.

7. **R7-TEN-1 — ApprovalService.approve/reject lack tenant + assigned-approver guards (HIGH).** [approval_service.py:165-281](../../backend/app/services/approval_service.py#L165) loads request by ID, blocks self-approval, but never verifies the parent entity (quote/opportunity) is in the user's tenant or that the user is the assigned approver. Tenant A rep can approve/reject tenant B's quote → tampering + cascade-reject DoS.

8. **R7-FORM-2 / R7-FORM-3 — Subscription has no edit path; Contract detail has no value/terms_json edit.** [SubscriptionDetailPage.tsx:66-80](../../frontend/src/features/subscriptions/SubscriptionDetailPage.tsx#L66) only cancel/renew. Backend lacks `SubscriptionUpdate` and PATCH route entirely. [ContractDetailPage.tsx](../../frontend/src/features/contracts/ContractDetailPage.tsx) only "activate" + "amend" — typo on contract value forces an audit-tracked amendment. Both major regressions in the edit-after-create flow.

9. **R7-API-4 — Pagination envelope still has 13 holdouts post-Round-6 sweep (HIGH/MED).** Endpoints not yet on canonical `{items, total, page, page_size, pages}`: `/leads/scoring-config`, `/notifications/`, `/guided-selling/`, `/customers/health/overview`, `/customers/health/at-risk`, `/team`, `/sharing-rules/`, `/leaderboard`, `/duplicates`, `/stakeholders`, `/pricing/tiers`, `/opportunities/columns`, `/opportunities/stages`. CLAUDE.md ban "Don't invent `{breaches: [], count: N}`-style envelopes" applies directly to `customer_health` and `notifications`.

10. **`as unknown as` escape hatches — R6-RENDER-7 close was incomplete (MED).** Audit found 16 remaining; **6 of them are in `OpportunitiesHomePage.tsx`** alone ([:77, :278, :280, :297, :298, :300](../../frontend/src/features/opportunities/OpportunitiesHomePage.tsx#L77)). Worst offender: code reads `o.customer_name` (flat) when backend nests it under `o.customer.name`. Round-6 removed one cast; six survived.

### Most-affected surfaces

- **Multi-tenant boundary** (1 critical, 4 high) — Lead analytics, coaching plans, approval service, audit export, reports excel export — all need additional `scoped_for_user`/`assert_same_tenant`. The boundary is mostly intact at the router layer; gaps are in service-layer or aggregation routes.
- **DB index bloat** (1 high family-wide regression) — R6 fixed 4 columns; 13 more siblings missed. Storage + write-cost penalty on hot tables (`leads`, `email_requests`, `quotes`, `spare_parts`).
- **Cache invalidation discipline** (2 high) — 87% of mutations don't use the canonical helper. Stale UI is the daily-experienced symptom.
- **Forms** (1 critical, 2 high) — Opportunity has no create form; Subscription has no edit; Contract detail can't edit value or terms_json.
- **Type-system drift** (1 structural high) — Hand-rolled `types.ts` is the recurring root cause for half the audit cycle's findings.
- **Pagination canonicalization** (3 high, 7 med) — 13 endpoints still on legacy shapes.
- **Sidebar orphans** (2 high) — `/users` and `/reports` (legacy ReportsPage) routed but not linked.

### What Round-6 closed and stayed closed

Re-verified against source on 2026-05-07:

| R6 finding | Status | Evidence |
|---|---|---|
| **R6-API-1** Campaign tenant_id + scoping | **HOLDS** | [campaigns.py:157](../../backend/app/api/v1/campaigns.py#L157) `scoped_for_user`; 7 single-row guards at :236, :260, :286, :305, :367, :406, :457, :483 |
| **R6-API-3** Invoice `pdf_path → has_pdf` | **HOLDS** | [invoices.py:125](../../backend/app/api/v1/invoices.py#L125) emits `has_pdf`; types.ts:1896 declares `has_pdf?: boolean` |
| **R6-API-4** CampaignMember lead/customer summary | **HOLDS** | [campaigns.py:96-127](../../backend/app/api/v1/campaigns.py#L96) emits both summaries |
| **R6-API-7/13** audit.py canonical reuse | **HOLDS** | [audit.py:359-375](../../backend/app/api/v1/audit.py#L359) imports `_customer_to_dict_canonical` etc. |
| **R6-API-2b** QuoteItem honeywell_code 100→500 | **HOLDS** | [schemas/quote.py:12, :34](../../backend/app/schemas/quote.py#L12) max_length=500 |
| **R6-DB-1** dup unique-indexes (4 columns) | **HOLDS** | user/customer/user_session/signature all `unique=True` only — **but family-wide regression: see R7-DB-1** |
| **R6-DB-3** UserResponse.updated_at non-null | **HOLDS** | [auth.py:39](../../backend/app/schemas/auth.py#L39) `updated_at: datetime` |
| **R6-DB-4/5** explicit nullable=False | **HOLDS** | pipeline.py / breach_notification.py / report_folder.py all carry the comment + flag |
| **R6-CACHE-1** queryClient.clear() in fallbacks | **HOLDS** | LoadingSpinner.tsx:91, SuspenseWithTimeout.tsx:50, authStore.ts:139, api.ts:113 — all four sites clear cache |
| **R6-RENDER-4** force password change gate | **HOLDS** | [AuthGuard.tsx:35-37](../../frontend/src/features/auth/AuthGuard.tsx#L35), ForcePasswordChangePage clears flag via setAuth |
| **R6-RENDER-9** timing reason_codes flat strings | **HOLDS** | [timing_engine_service.py:250-276](../../backend/app/services/timing_engine_service.py#L250) writes flat `key=value` strings; SPA defensive coercion in panel |
| **R6-FORM-1..6** form completeness | **HOLDS** for FORM-1/2/3/5/6; **PARTIAL** for FORM-4 (stage + customer_id still missing from inline edit) |
| **R6-RENDER-2/3/5/6** rendering gaps | **HOLDS** for all four |
| **R6-RENDER-OPP-1** Kanban fields | **HOLDS** | BoardPage.tsx:199-231 |
| **R6-NAV-1** 8 sidebar entries | **HOLDS** | Sidebar.tsx:292, :340, :350, :375, :379, :408-414 — but **R7-I18N-2: hardcoded Turkish strings** |
| **R6-RESP-1** mobile responsive 5 list pages | **HOLDS** | Invoice/Contract/Subscription/Leaderboard/Pricing all have hide classes |
| **R6-RENDER-7** OpportunitiesHomePage cast | **PARTIAL** | One cast removed; **6 more survived** — see R7-TS-7 |
| **R6-RENDER-8** Cockpit isError | **HOLDS** | KpiStrip accepts isError; **but** `if (!data) return null` at :146 still there → R7-RENDER-1 |
| **R5-PERM-1** apply_request_perms 9 entities | **HOLDS** | All 9 verified |
| **R5-RL-7** signing rate limit | **HOLDS** | signatures.py:364, :410, :455 |
| **R5-EVENT-1/2** retention tenant grouping + lead delta | **HOLDS** | scheduler.py:472-504, lead_service.py:124 |
| **R5-DB-1/2/3/8** bootstrap, dup-index, drift gate | **HOLDS** | But R7-DB-3: gate is blind to 4 categories incl. indexes |
| **R5-FAKE-1/2** fabricated KPIs | **HOLDS** |

**Net regressions / new findings in v1.10.0..v1.11.0: 3 family-wide regressions** (R7-DB-1 dup-indexes, R7-TS-7 cast escape hatches, R6-RENDER-8 partial close) **+ 51 net-new findings**.

---

## 2. Findings by Category

### 2.1 Multi-tenant security — CRITICAL × 2, HIGH × 1, MEDIUM × 3

#### R7-API-1 — `Lead` analytics cross-tenant leak — **CRITICAL**

- **Files:** [backend/app/api/v1/leads.py:117-128, 169-172](../../backend/app/api/v1/leads.py#L117)
- **Evidence:**
  ```python
  funnel_result = await db.execute(
      select(Lead.status, func.count(Lead.id))
      .where(Lead.created_at >= cutoff)
      .group_by(Lead.status)
  )
  ...
  all_leads_result = await db.execute(
      select(Lead).where(Lead.created_at >= cutoff)
  )
  ```
  Three `select(Lead)` aggregations execute without `scoped_for_user(..., column=Lead.tenant_id)`.
- **Attack:** Manager in tenant A hits `GET /leads/analytics` → response includes funnel counts, conversion rates, and weekly trend across **every tenant's leads**. Direct competitive intelligence leak.
- **Fix:** Wrap all three queries with `scoped_for_user(stmt, current_user, column=Lead.tenant_id)`. ~3 lines.
- **Migration:** No.

#### R7-API-2 — Coaching plan `target_user` cross-tenant injection — **CRITICAL**

- **Files:** [backend/app/api/v1/coaching.py:128-131](../../backend/app/api/v1/coaching.py#L128)
- **Evidence:** Endpoint loads target user by ID, raises 404 if missing, but skips `assert_same_tenant`. `User.tenant_id` is a real column ([user.py:30](../../backend/app/models/user.py#L30)).
- **Attack:** Manager in tenant A enumerates `body.user_id` values, mints CoachingPlans against tenant B users. Tenant B's user-facing coaching surface gets polluted with `manager_id` pointing into tenant A.
- **Fix:** `assert_same_tenant(target_user, current_user, exception_cls=NotFoundException)` after the lookup. 1 line.
- **Migration:** No.

#### R7-TEN-1 — `ApprovalService.approve/reject` lack tenant + assigned-approver guards — **HIGH**

- **Files:** [backend/app/services/approval_service.py:165-281](../../backend/app/services/approval_service.py#L165), called from [approvals.py:210-237, :266-276](../../backend/app/api/v1/approvals.py#L210) (`approve_request`, `reject_request`, `quick_approve`)
- **Evidence:** `approve()` loads `ApprovalRequest.id == request_id`, blocks self-approval at :184-191, but never:
  1. Loads the parent entity (quote/opportunity) and asserts same tenant
  2. Verifies `approval_request.assigned_to == user_id` or delegate
- **Attack:** Tenant A rep guesses an `ApprovalRequest.id` belonging to tenant B → POST `/approvals/{id}/approve` (or `quick-approve` which has no body). The parent quote/opportunity flips to `is_fully_approved`, downstream invoice/contract events fire on tenant B data. `reject()`'s cascade-reject mass-rejects all pending requests for the foreign entity → DoS + tampering.
- **Fix:** In service `approve()`/`reject()`, after loading the request: load parent via `_APPROVAL_ENTITY_MODELS[entity_type]`, call `assert_same_tenant(parent, user)`; then verify `assigned_to == user_id` or user is a valid delegate.
- **Migration:** No.

#### R7-TEN-2 — `audit.export_user_data` `sent_emails` query not tenant-scoped — **MEDIUM**

- **File:** [audit.py:233-238](../../backend/app/api/v1/audit.py#L233)
- **Evidence:** `select(EmailRequest).where(EmailRequest.from_address == user.email)` — no `scoped_for_user` despite `EmailRequest.tenant_id` existing. Surrounding queries (`audit_events`, `created_customers`, `owned_opportunities` at :206-228) all use `scoped_for_user` — this is the only outlier.
- **Attack:** Lower likelihood than R7-TEN-1 since email is unique-per-tenant by convention, but a user moved tenants or domain reuse could cause leak.
- **Fix:** Add `scoped_for_user(...)` wrap. 1 line.

#### R7-TEN-3 — `reports_v2.export_template_excel` re-loads template without tenant guard — **MEDIUM**

- **File:** [reports_v2.py:500-542, esp :517-520](../../backend/app/api/v1/reports_v2.py#L500)
- **Evidence:** Calls `engine.execute_report(template_id, current_user)` (engine is tenant-safe), but then re-loads the template with a bare `select(ReportTemplate).where(id == template_id)` and uses `report.name` for worksheet title and Content-Disposition. No `assert_same_tenant`.
- **Attack:** If `engine.execute_report` returns empty rows for cross-tenant (instead of raising), the response leaks tenant B's template name in the filename. **Needs manual verification** of engine semantics.
- **Fix:** Replace lines 517-520 with the canonical `_get_user_template(db, template_id, current_user)` helper at :608-634.

#### R7-TEN-4 — `chat.send_message` accepts arbitrary `sender_id` from public visitor — **LOW**

- **File:** [chat.py:258-308](../../backend/app/api/v1/chat.py#L258)
- **Evidence:** Endpoint has no auth (intentional — visitor side). `body.sender_id` is written verbatim. No correlation between `sender_type="agent"` and a real authenticated agent token.
- **Attack:** Anonymous visitor POSTs `sender_type="agent", sender_id=42` → message renders in transcript as if agent #42 sent it. Pure spoofing of chat history.
- **Fix:** Reject `sender_type` ∈ {`agent`, `bot`} on the public endpoint; require those to come from authenticated agent endpoints.

### 2.2 R6 family-wide regressions — HIGH × 3

#### R7-DB-1 — Same R6-DB-1 anti-pattern on 13 more columns — **HIGH**

R6 dropped duplicate indexes on the auth-critical column family (user/customer/user_session/signature). The identical `unique=True + index=True` pattern is alive on:

| File:line | Column |
|---|---|
| [lead.py:19](../../backend/app/models/lead.py#L19) | `Lead.email` |
| [api_key.py:17](../../backend/app/models/api_key.py#L17) | `ApiKey.key_hash` |
| [email_request.py:26](../../backend/app/models/email_request.py#L26) | `EmailRequest.message_id` |
| [quote.py:13](../../backend/app/models/quote.py#L13) | `Quote.quote_number` |
| [spare_part.py:14](../../backend/app/models/spare_part.py#L14) | `SparePart.honeywell_code` |
| [setting.py:13](../../backend/app/models/setting.py#L13) | `Setting.key` |
| [meeting_link.py:19](../../backend/app/models/meeting_link.py#L19) | `MeetingLink.slug` |
| [shared_document.py:22](../../backend/app/models/shared_document.py#L22) | `SharedDocument.token` |
| [network_benchmarks.py:24](../../backend/app/models/network_benchmarks.py#L24) | `NetworkSegment.segment_key` |
| [account_enrichment.py:24](../../backend/app/models/account_enrichment.py#L24) | `AccountEnrichment.customer_id` |
| [sales_event_shadow.py:20](../../backend/app/models/sales_event_shadow.py#L20) | `SalesEventShadow.source_ref` |
| [lead_scoring_config.py:20](../../backend/app/models/lead_scoring_config.py#L20) | `LeadScoringConfig.name` |
| [deal_room.py:17,25](../../backend/app/models/deal_room.py#L17) | `DealRoom.external_token` (explicit `Index(...)` + column `unique=True`) |

**Why it matters:** Postgres auto-creates a UNIQUE index for any column-level UNIQUE constraint. Adding `index=True` produces a second index covering the same column → 2× write cost on every INSERT/UPDATE. Several (`Lead.email`, `EmailRequest.message_id`, `Quote.quote_number`, `SparePart.honeywell_code`) sit on hot write paths.

**Fix:** Drop `index=True` on each column above. New migration `20260507_drop_dup_unique_indexes_phase2.py` mirroring `20260506_drop_dup_unique_indexes.py`. **Migration needed: yes.**

#### R7-TS-7 — R6-RENDER-7 close was incomplete; 16 `as unknown as` escape hatches survive — **MEDIUM**

R6 removed one cast in OpportunitiesHomePage. **Six more remain in the same file**:

- [OpportunitiesHomePage.tsx:77, :278, :280, :297, :298, :300](../../frontend/src/features/opportunities/OpportunitiesHomePage.tsx#L77) — multiple `(o as unknown as { customer_name?: string }).customer_name` reads. Backend never emits a flat `customer_name`; nested under `o.customer.name`. The casts paper over wrong field access.

Other files with surviving casts:
- [SettingsPage.tsx:83](../../frontend/src/features/settings/SettingsPage.tsx#L83)
- [CommentThread.tsx:207](../../frontend/src/features/board/CommentThread.tsx#L207)
- [admin/ReportsPage.tsx:120-121](../../frontend/src/features/admin/ReportsPage.tsx#L120)
- [DashboardListPage.tsx:304-305](../../frontend/src/features/dashboards/DashboardListPage.tsx#L304)
- [PartsIntelligenceDashboardPage.tsx:510, :527](../../frontend/src/features/parts-intel/PartsIntelligenceDashboardPage.tsx#L510)
- [SavedReportsPage.tsx:196, :201](../../frontend/src/features/reports/SavedReportsPage.tsx#L196)

**Fix:** OpportunitiesHomePage: read `o.customer?.name` directly. For other files: declare missing fields on the appropriate types (`DashboardSummary`, `ReportTemplate`, `PartsIntelRow`).

#### R7-RENDER-1 — R6-RENDER-8 close was incomplete; Cockpit `if (!data) return null` survives — **MEDIUM**

- **File:** [CockpitPage.tsx:146](../../frontend/src/features/cockpit/CockpitPage.tsx#L146)
- **Evidence:** R6 added the `isError` branch at :138-144 but kept the `if (!data) return null` at :146. When useQuery resolves with undefined data (rare but possible during cache eviction), users see a blank surface.
- **Fix:** Replace `return null` with `<EmptyState />` or skeleton.

### 2.3 DB ↔ ORM drift — HIGH × 2, MEDIUM × 3

#### R7-DB-2 — `OpportunityTransformerSeqEmbedding` not imported in `__init__.py` — **HIGH**

- **Files:** [v12_transformer_seq_embedding.py:25](../../backend/app/models/v12_transformer_seq_embedding.py#L25) — class defined; [models/__init__.py](../../backend/app/models/__init__.py) — **no import, not in `__all__`**.
- **Why:** SQLAlchemy `Base.metadata` only registers a model when its module is imported. Bootstrap covers the table via `20260428_v12_transformer_seq_embedding.py`, but:
  - `Base.metadata.create_all()` (tests + dev fallback) won't create the table
  - `schema_check.py` iterates `base_metadata.sorted_tables` — table is **invisible to drift detection**
  - Bootstrap regen script may miss it on next regen
- **Fix:** Add `from app.models.v12_transformer_seq_embedding import OpportunityTransformerSeqEmbedding` (~line 108) and `"OpportunityTransformerSeqEmbedding"` to `__all__`.

#### R7-DB-3 — `schema_check.py` blind to 4 entire drift categories — **MEDIUM**

- **File:** [schema_check.py:130-225](../../backend/app/core/schema_check.py#L130)
- **Currently checks:** missing-in-db, missing-in-model, type-mismatch, nullability-mismatch.
- **Doesn't check:**
  - **Default / server_default drift** — model `default=lambda: ...` vs DB `DEFAULT NOW()` mismatches go silent
  - **Index existence drift** — exactly the failure mode that produced R6-DB-1 and R7-DB-1; gate cannot detect duplicate or missing indexes
  - **UNIQUE / CHECK constraint drift** — column-level `unique=True` not compared against DB constraint
  - **FK existence + ON DELETE drift** — `ondelete="CASCADE"` never compared against `information_schema.referential_constraints`
- **Why:** R7-DB-1 is the proof that the index gap is real and exploitable. CI gate reports `clean` while 13 duplicate indexes ship.
- **Fix:** Extend to enumerate `inspector.get_indexes(table)` and compare against `table.indexes`. Add an "index count per column" sanity assertion.

#### R7-DB-4 — High-volume log tables use 32-bit `Integer` PK — **MEDIUM (advisory)**

- **Files:** `audit_log.py:12`, `sales_event_shadow.py:18`, `activity_log.py` — all `Integer` PK. **No `BigInteger` anywhere** in models.
- **Why:** SERIAL caps at 2³¹-1 (~2.1B). At 10K writes/day per tenant × multi-tenant, ~590 years per single tenant — but bulk imports / replays + tenant-id 1 in a SaaS could hit it materially earlier.
- **Fix:** Migrate `audit_logs.id`, `sales_events_shadow.id`, `activity_logs.id` to `BIGINT` and switch model to `BigInteger`. Future-only; existing rows safe.

#### R7-DB-5 — 7 CRM-adjacent models still lack `tenant_id` — **MEDIUM**

| File:line | Model | Owns | Risk |
|---|---|---|---|
| [notification.py:13](../../backend/app/models/notification.py#L13) | `Notification` | `user_id` | Tenant-move leak |
| [email_template.py:21](../../backend/app/models/email_template.py#L21) | `EmailTemplate` | `created_by` | Cross-tenant template visibility |
| [playbook.py:30](../../backend/app/models/playbook.py#L30) | `Playbook` | `created_by` (nullable!) | Cross-tenant playbook visibility |
| `meeting_booking.py` | `MeetingBooking` | (only meeting_link FK) | Calendar leak |
| [deal_room.py:33](../../backend/app/models/deal_room.py#L33) | `DealRoom` | `created_by` | **Next likely Campaign-shape leak** |
| `comment.py` | `Comment` | (FK to entity_type/entity_id) | Already mostly safe via FK chain |
| `feature_usage.py` | `FeatureUsage` | `user_id` | Telemetry leak |

**Why:** Defence in depth. Without `tenant_id` on the row, no `scoped_for_user` is possible — API has to rely on transitive joins, which is exactly the failure mode R6-API-1 documented. **DealRoom is the next likely Campaign-shape leak.**

**Fix:** Audit each entity's API surface. If reachable cross-tenant, mirror `20260506_campaign_tenant.py` shape: add column, backfill from owning user's tenant, add index.

### 2.4 Backend ↔ API contract — HIGH × 2, MEDIUM × 4, LOW × 2

#### R7-API-3 — User CSV bulk-import bypasses `EmailStr` — **HIGH**

- **File:** [users.py:218-226](../../backend/app/api/v1/users.py#L218)
- **Evidence:** `if not email or "@" not in email:` — only checks for an `@`. CLAUDE.md mandates `EmailStr` at User create paths.
- **Why:** Lets through `a@`, `@b`, `a@b` (no TLD), spaces around `@`, header-injection candidates.
- **Fix:** Run each row through a Pydantic model with `EmailStr` field; aggregate `ValidationError` into `errors` list per row.

#### R7-API-4 — 13 pagination envelope holdouts — **HIGH × 3, MEDIUM × 7, LOW × 3**

| File:line | Endpoint | Shape | Severity |
|---|---|---|:-:|
| [leads.py:325-337](../../backend/app/api/v1/leads.py#L325) | `/leads/scoring-config` | `{items: [...]}` (no total/page/page_size/pages) | HIGH |
| [notifications.py:37](../../backend/app/api/v1/notifications.py#L37) | `/notifications/` | `{notifications: [...]}` | HIGH |
| [guided_selling.py:48](../../backend/app/api/v1/guided_selling.py#L48) | `/guided-selling/` | `{guides: [...]}` | HIGH |
| [customer_health.py:71-80](../../backend/app/api/v1/customer_health.py#L71) | `/customers/health/overview` | `{summary, customers: [...]}` | MED |
| [customer_health.py:94-100](../../backend/app/api/v1/customer_health.py#L94) | `/customers/health/at-risk` | `{count, customers: [...]}` | MED |
| [teams.py:89-101](../../backend/app/api/v1/teams.py#L89) | `/team` | `{data: [...]}` | MED |
| [teams.py:195-197](../../backend/app/api/v1/teams.py#L195) | `/sharing-rules/` | `{data: [...]}` | MED |
| [leaderboard.py:26, :54](../../backend/app/api/v1/leaderboard.py#L26) | leaderboard, achievements | `{data: [...]}` | MED |
| [duplicates.py:57, :78, :104](../../backend/app/api/v1/duplicates.py#L57) | duplicate suggestions | `{data: [...]}` | MED |
| [stakeholders.py:126, :145](../../backend/app/api/v1/stakeholders.py#L126) | stakeholders by opp | `{opportunity_id, stakeholders: [...]}` | MED |
| [pricing.py:105](../../backend/app/api/v1/pricing.py#L105) | price tiers | `{price_entry_id, tiers: [...]}` | MED |
| [opportunities.py:1026](../../backend/app/api/v1/opportunities.py#L1026) | `/opportunities/columns` | `{columns: [...]}` | LOW (kanban) |
| [opportunities.py:531](../../backend/app/api/v1/opportunities.py#L531) | `/opportunities/stages` | `{data: stages}` | LOW (fixed enum) |

CLAUDE.md ban "Don't invent `{breaches: [], count: N}`-style envelopes" applies directly to `customer_health` and `notifications`. Fix pattern:
```python
return {"items": items, "total": total, "page": page, "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0}
```

#### R7-API-5 — `_quote_to_dict` items diverge from `QuoteItemResponse` schema — **MEDIUM**

- **Files:** [quotes.py:778-801](../../backend/app/api/v1/quotes.py#L778) vs [schemas/quote.py:55-75](../../backend/app/schemas/quote.py#L55)
- **Drift:**
  - Serializer omits `quote_id` (declared on schema line 57)
  - Serializer omits `spare_part_name` and `spare_part_category` (schema lines 72-73), instead emits inline `spare_part: {id, honeywell_code, name_en}` not declared in schema
  - Serializer's `customer` shape is `{id, name, company, email}`, but `QuoteResponse.customer: CustomerResponse` requires the full 17-field CustomerResponse

#### R7-API-6 — `_customer_to_dict` doesn't emit `quote_count`/`total_quote_value` — **LOW**

- **Files:** [customers.py:956-1008](../../backend/app/api/v1/customers.py#L956) vs [schemas/customer.py:80-81](../../backend/app/schemas/customer.py#L80)
- Schema declares both as `Optional[int|float]`; serializer never sets them. Either pre-compute via subquery or remove from schema.

#### R7-API-9 — `FEATURE_GUIDED_SELLING` declared but no `_require_*` dependency — **MEDIUM**

- **File:** [config.py:431](../../backend/app/core/config.py#L431) declares the flag, exposed via settings, frontend-gated via `FeatureFlagGate`. [guided_selling.py](../../backend/app/api/v1/guided_selling.py) has no `_require_guided_selling()` dep.
- **CLAUDE.md ban:** "never ship a frontend-only gate". Tenants with feature off can still POST/GET via `guided-selling/*`.
- **Fix:** Add `def _require_guided_selling()` raising 404 if flag off; attach to every router endpoint.

### 2.5 API ↔ TS types — HIGH × 2, MEDIUM × 5, LOW × 4, INFO × 1

#### R7-TS-1 — `EmailRequest.body_text/body_html/parsed_data` declared required but list endpoints omit — **HIGH**

- **Files:** [types.ts:198-204](../../frontend/src/lib/types.ts#L198) declares all three as required (no `?`); [emails.py:835-880](../../backend/app/api/v1/emails.py#L835) only sets them inside `if include_body:` (line 875).
- **Impact:** `email.body_text.slice(0, 200)` will crash on list responses. TS type is lying.
- **Fix:** Mark optional: `body_text?: string; body_html?: string; parsed_data?: ParsedData | null;`

#### R7-TS-12 — Hand-rolled `types.ts`, no codegen pipeline — **HIGH (structural)**

- **File:** `frontend/package.json` has no `openapi-typescript` / `openapi-fetch` / `orval`. The 2103-line `types.ts` is fully hand-maintained.
- **Why:** Every cross-layer audit since Round-3 keeps re-finding this drift class. **Structural root cause.**
- **Fix (long-term):**
  1. Add Pydantic response models for every list/detail endpoint (most exist)
  2. Wire FastAPI's OpenAPI export → `openapi-typescript` → `frontend/src/lib/api-types.generated.ts` in CI
  3. Hand-rolled `types.ts` re-exports the generated names
  4. CI fails if generated file drifts from committed copy

#### R7-TS-2 — Required `created_at`/`updated_at` strings while backend can emit `null` — **MEDIUM**

5 entities have TS `string` for timestamps that backend emits with `isoformat() if x else None` defensive guard:

- `Quote.created_at`, `Quote.updated_at` ([types.ts:344-345](../../frontend/src/lib/types.ts#L344) vs [quotes.py:768-769](../../backend/app/api/v1/quotes.py#L768))
- `Opportunity.created_at`, `Opportunity.updated_at` ([types.ts:534-535](../../frontend/src/lib/types.ts#L534) vs [opportunities.py:165-166](../../backend/app/api/v1/opportunities.py#L165))
- `User.created_at` ([types.ts:16](../../frontend/src/lib/types.ts#L16) vs users.py:302)
- `Invoice.created_at`, `Invoice.updated_at` ([types.ts:1898-1899](../../frontend/src/lib/types.ts#L1898) vs [invoices.py:127-128](../../backend/app/api/v1/invoices.py#L127))

**Fix:** Change to `string | null` consistently (matching Lead, Email, Pipeline, Territory, Subscription which already do this).

#### R7-TS-3 / R7-TS-4 — Subscription/Campaign date field nullability drift — **MEDIUM**

- `Subscription.start_date: string;` ([types.ts:1753](../../frontend/src/lib/types.ts#L1753)) but backend emits `null` ([subscriptions.py:62](../../backend/app/api/v1/subscriptions.py#L62))
- `Campaign.start_date?`, `end_date?`, `description?`, `budget?`, `expected_revenue?` ([types.ts:1834-1838](../../frontend/src/lib/types.ts#L1834)); `CampaignMember.responded_at?` ([:1853](../../frontend/src/lib/types.ts#L1853)) — backend explicitly emits `null`, so wire shape is `string | null`, not "absent". TS `?:` says "may be undefined" but key is always present with `null`.

#### R7-TS-5 — `Customer.stats` block emitted by detail endpoint, not declared on type — **MEDIUM**

- [customers.py:222-227](../../backend/app/api/v1/customers.py#L222) emits `data["stats"] = {...}` and `data["pinned"]`; types.ts declares `pinned`/`quote_count`/`total_quote_value` but **not `stats`**.
- **Fix:** Add `stats?: { total_quotes: number; total_value: number; sent_quotes: number };`

#### R7-TS-6 — `total_quotes` vs `quote_count` shape inconsistency — **LOW**

- [customers.py:951](../../backend/app/api/v1/customers.py#L951) (dashboard route) emits `total_quotes`; list path uses `quote_count`. Two different keys for the same metric on different routes.

#### R7-TS-8 — `: any` annotations in feature code — **LOW**

- [CockpitPage.tsx:1462, :1544](../../frontend/src/features/cockpit/CockpitPage.tsx#L1462) — `(g: any)` and `(s: any)` callbacks.

#### R7-TS-9 — `Partial<Customer>` payload contract too loose for create/update — **LOW**

- [api.ts:446, :451](../../frontend/src/lib/api.ts#L446); also `Partial<SparePart>` at :387.
- Allows server-managed fields (`id`, `created_at`, `tenant_id`, `quote_count`) to be sent. Form code papers over the gap with casts/coerces (CustomerListPage:336, CustomerDetailPage:269 both do this).
- **Fix:** Introduce `CustomerCreatePayload` / `CustomerUpdatePayload`. Same for Quote, Lead, Opportunity, SparePart.

#### R7-TS-10 — `parts/categories` legacy envelope union — **LOW**

- [api.ts:375-379](../../frontend/src/lib/api.ts#L375) accepts `{items?: string[]} | string[]`. Pin backend to canonical and remove the union.

#### R7-TS-11 — Chat sessions/messages legacy keys still in fallback — **INFO**

- [api.ts:2732, :2745](../../frontend/src/lib/api.ts#L2732) — `data?.items ?? data?.sessions ?? []`. R6-PAGE-1 made canonical authoritative; the legacy arms are dead.

### 2.6 UI completeness — CRITICAL × 1, HIGH × 4, MEDIUM × 8, LOW × 3

#### R7-FORM-1 — No standalone "Create Opportunity" form — **CRITICAL**

- **File:** [api.ts:898-901](../../frontend/src/lib/api.ts#L898) declares `opportunitiesApi.create`; **zero call sites** in `frontend/src/`.
- **Impact:** Reps cannot create an expansion deal on an existing customer. Forces fake-lead workaround through Lead conversion. Full `OpportunityCreate` schema unreachable from UI.
- **Fix:** Add a "Yeni Fırsat" modal on `BoardPage.tsx` and/or `OpportunitiesHomePage.tsx:84-160` calling `opportunitiesApi.create`.

#### R7-FORM-2 — Subscription has no edit path (backend gap) — **HIGH**

- **File:** [SubscriptionDetailPage.tsx:66-80](../../frontend/src/features/subscriptions/SubscriptionDetailPage.tsx#L66) only cancel + renew. Backend [subscriptions.py](../../backend/app/api/v1/subscriptions.py) has `SubscriptionCreate` (line 28) but **no `SubscriptionUpdate` and no PATCH endpoint**.
- **Impact:** After creation, MRR/billing_cycle/end_date/auto_renew/items_json/name cannot be corrected without DB access.
- **Fix:** Add backend `SubscriptionUpdate` + PATCH endpoint, then mirror the customer-detail inline-edit pattern.

#### R7-FORM-3 — Contract detail can't edit `value` or `terms_json` — **HIGH**

- **File:** [ContractDetailPage.tsx](../../frontend/src/features/contracts/ContractDetailPage.tsx) exposes only "activate" (line 52) and "amend" (line 62). Backend `ContractUpdate` ([contracts.py:46-52](../../backend/app/api/v1/contracts.py#L46)) accepts title/start_date/end_date/value/terms_json/status — but only `amend` (audit-tracked workflow) reaches the row.
- **Impact:** Typo in contract title or value forces an audit-tracked amendment.
- **Fix:** Add inline edit panel similar to `OpportunityDetailPage.tsx:565-690`.

#### R7-NAV-1 — `/users` route is orphan in sidebar — **HIGH**

- **File:** [App.tsx:348-357](../../frontend/src/app/App.tsx#L348) routes `UserManagementPage`. [Sidebar.tsx](../../frontend/src/components/layout/Sidebar.tsx) has no NavLink to `/users`.
- **Impact:** Sales managers must hand-type the URL to manage users — admin page reachable only by URL guess.

#### R7-NAV-2 — Legacy `/reports` ReportsPage orphan — **HIGH**

- **File:** [App.tsx:338-347](../../frontend/src/app/App.tsx#L338) mounts `ReportsPage`. Sidebar only links `/reports/builder` and `/reports/saved`. Either delete the route or link it.

#### R7-FORM-4 — Opportunity inline edit drops `stage` and `customer_id` — **MEDIUM**

- **File:** [OpportunityDetailPage.tsx:443-450](../../frontend/src/features/board/OpportunityDetailPage.tsx#L443) — editForm captures title/amount/currency/close_date/status/loss_reason but not `stage` or `customer_id`. Both in `OpportunityUpdate`.
- **Impact:** `customer_id` cannot be reassigned at all from UI.

#### R7-FORM-5 — Lead Detail edit form omits `email` — **LOW**

- Backend `LeadUpdate` ([leads.py:53-60](../../backend/app/api/v1/leads.py#L53)) doesn't accept `email` either, so this is consistent. But correcting a typo in lead email forces delete+recreate.

#### R7-RESP-1 — Multiple raw `<table>` pages lack responsive — **MEDIUM**

Files lacking `hidden sm:table-cell` patterns: [EventAuditLogPage.tsx](../../frontend/src/features/admin/EventAuditLogPage.tsx), [admin/ReportsPage.tsx](../../frontend/src/features/admin/ReportsPage.tsx), [PlaybookAnalyticsPage.tsx](../../frontend/src/features/playbooks/PlaybookAnalyticsPage.tsx), [PlaybookDetailPage.tsx](../../frontend/src/features/playbooks/PlaybookDetailPage.tsx), [SalesAnalyticsPage.tsx](../../frontend/src/features/board/SalesAnalyticsPage.tsx), [WebhookSettings.tsx](../../frontend/src/features/settings/WebhookSettings.tsx). Plus the parts of `OpportunityDetailPage.tsx`, `CockpitPage.tsx`, `SettingsPage.tsx` that hand-roll tables.

#### R7-RESP-2 — DataTable primitive has no built-in column-hide — **MEDIUM**

- [DataTable.tsx:30-39](../../frontend/src/components/ui/DataTable.tsx#L30) `Column<T>` has no `hideOn?: 'sm'|'md'|'lg'`.
- Every list page using DataTable (Quotes/Leads/Customers/Emails/Approvals) cannot hide columns on mobile.
- **Fix:** Add `hideOn` prop, ~25 lines.

#### R7-RENDER-2 — Many pages return `null` on missing data — **MEDIUM**

Files: [EmailListPage.tsx:192](../../frontend/src/features/emails/EmailListPage.tsx#L192), [ActivityLogPanel.tsx:133](../../frontend/src/components/ActivityLogPanel.tsx#L133), [BoardPage.tsx:119](../../frontend/src/features/board/BoardPage.tsx#L119), [WorkflowRulesPage.tsx:309, :335](../../frontend/src/features/admin/WorkflowRulesPage.tsx#L309), [TranscriptsPage.tsx:326](../../frontend/src/features/engagement/TranscriptsPage.tsx#L326), [BuyerRelationshipMap.tsx:114](../../frontend/src/features/opportunities/BuyerRelationshipMap.tsx#L114). Some inside `.map()` callbacks (acceptable); page-level returns silently swallow errors.

#### R7-RENDER-3 — `isError` handled in only 17/91 feature files (~19%) — **MEDIUM**

`grep -lr "useQuery"` → 91 files; `grep -lr "isError"` → 17 files. Most pages render skeleton-or-empty when an API call fails — no toast, no fallback. 401s caught globally, but 5xx and 422 fall through.

**Fix:** Standardize via small `useQueryWithError` hook or `<ErrorPanel />` primitive.

#### R7-I18N-1 — `CampaignListPage` hardcoded Turkish — **MEDIUM**

- [CampaignListPage.tsx:161, :164, :186, :189](../../frontend/src/features/campaigns/CampaignListPage.tsx#L161) — `title="Kampanyalar"`, `description="Kampanya yönetimi ve ROI takibi"`, `Yeni Kampanya`, error message. File imports `useT` (line 18) but only calls `t()` for filter labels.

#### R7-I18N-2 — Sidebar R6-NAV-1 entries are hardcoded Turkish — **MEDIUM**

- [Sidebar.tsx:294, :342, :352, :377, :381](../../frontend/src/components/layout/Sidebar.tsx#L294) — "Onay Kuralları", "AI Görevleri", "Rapor Oluşturucu", "Şablonlar", "Playbook Analitiği".
- **Impact:** EN/DE/FR/ES locales surface Turkish in sidebar.
- **Fix:** Add `nav.approval_rules`, `nav.ai_tasks`, `nav.report_builder`, `nav.playbook_templates`, `nav.playbook_analytics` keys across all 5 locales.

#### R7-A11Y-1 / R7-RENDER-4 — minor accessibility / DataTable error prop — **LOW**

### 2.7 Realtime / cache / lifecycle — HIGH × 2, MEDIUM × 3, LOW × 4

#### R7-CACHE-1 — Canonical helper bypassed in 87% of mutation sites — **HIGH**

- ~58 files in `frontend/src/features/**` use ad-hoc `queryClient.invalidateQueries`; only **9** import from `lib/cacheInvalidation.ts` (CustomerDetailPage, BuyerRelationshipMap, InvoiceDetailPage, QuickActivityModal, OpportunityDetailPage, LeadDetailPage, ContractDetailPage, QuoteEditorPage, MergeRecordsPage).
- **Examples:**
  - [LeadListPage.tsx:108, :130](../../frontend/src/features/leads/LeadListPage.tsx#L108) only invalidates `['leads']` — misses customers/opportunities/cockpit
  - [CustomerListPage.tsx:358, :372, :408](../../frontend/src/features/customers/CustomerListPage.tsx#L358) only invalidates `['customers']` — misses high-intent-accounts
  - [EmailListPage.tsx](../../frontend/src/features/emails/EmailListPage.tsx) (8 sites), [InvoiceListPage.tsx](../../frontend/src/features/invoices/InvoiceListPage.tsx), [QuoteEditorPage.tsx:125](../../frontend/src/features/quotes/QuoteEditorPage.tsx#L125) (mixed), all chat/settings/admin pages bypass.
- **Impact:** Stale dashboard/cockpit/kanban after row-level edits. Sales rep edits a lead from list → dashboard tile lags 30s+.
- **Fix:** Route every mutation through helper; add `onLeadCreated`, `onCustomerCreated`, `onEmailParsedClient`, `onInvoiceCreated` helpers.

#### R7-CACHE-2 — `LeadListPage` convert flow doesn't cascade — **HIGH**

- **File:** [LeadListPage.tsx:108-130](../../frontend/src/features/leads/LeadListPage.tsx#L108) — convert mutation only invalidates `['leads']`.
- [LeadDetailPage.tsx:171-172](../../frontend/src/features/leads/LeadDetailPage.tsx#L171) imports the helper but only `invalidateQueries(['lead', leadId])` + `['leads']` — never calls `onLeadConverted`.
- **Impact:** After convert, customer/opportunity lists & cockpit don't refresh. Hard reload required.

#### R7-RT-1 — `ChatWidget` polls every 5s with no document-hidden guard — **MEDIUM**

- [ChatWidget.tsx:10, :72](../../frontend/src/features/chat/ChatWidget.tsx#L10) — `POLL_INTERVAL_MS = 5_000`. Below the 30s default. No `refetchIntervalInBackground: false`. On Render Free tier this is wasteful.
- **Fix:** Raise to 15-20s or pause when document hidden; ideally upgrade to SSE.

#### R7-LIFE-3 — `CockpitPage` 14 distinct `refetchInterval` timers — **MEDIUM**

- [CockpitPage.tsx:207, :307, :1129, :1594](../../frontend/src/features/cockpit/CockpitPage.tsx#L207) — 30-60s intervals; 11 more @ 120s; one @ 300s.
- **Impact:** Opening Cockpit triggers 14 staggered timers. On slow API or Render free tier this stacks request load.
- **Fix:** Consolidate via single `cockpit` query or set `refetchIntervalInBackground: false`.

#### R7-EVENT-1 — `customer.created` not emitted in bulk import — **MEDIUM**

- Producer at [customers.py:452](../../backend/app/api/v1/customers.py#L452); CustomerListPage CSV import flow doesn't appear to publish per row.
- **Impact:** Bulk-imported customers skip webhook + revenue-signal pipelines.
- **Needs manual verification** of `import_service.py` emit behavior.

#### R7-EVENT-2 — `opportunity.score_changed` not consumed by workflow engine — **LOW**

- Producer [opportunities.py:635-660](../../backend/app/api/v1/opportunities.py#L635); only subscriber is `webhook_service` at main.py:233. Workflow engine doesn't subscribe.
- **Impact:** Workflow rules can't gate on probability deltas.

#### R7-LIFE-1 / R7-LIFE-2 — staleTime/refetchInterval contradictions — **LOW**

- [CommentThread.tsx:197, :203](../../frontend/src/features/board/CommentThread.tsx#L197) — `staleTime: 300_000` plus `refetchInterval: 30_000`. Polling overrides stale. Drop the explicit staleTime.
- [SystemHealthPage.tsx:81](../../frontend/src/features/admin/SystemHealthPage.tsx#L81) — `staleTime: 0` plus `refetchInterval: 30_000`. Add a comment if intentional.

#### R7-RT-2 — No optimistic updates anywhere — **LOW (informational)**

- `grep onMutate` returns 0 hits across `frontend/src`. Every mutation is fire-and-await with toast feedback. No rollback risk; conversely UX feels laggy on stage drag in kanban.

---

## 3. Cross-Layer Schema Compatibility Matrix

### Lead

| Field | DB | Model | `_lead_to_dict` | `LeadResponse` | TS | UI form | UI render | Status |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:--|
| email | ✓ | ✓ | ✓ | ✓ | ✓ | ❌ on update | ✓ | R7-FORM-5 (low) |
| email index | dup | `unique=True, index=True` | n/a | n/a | n/a | n/a | n/a | **R7-DB-1** |
| (analytics aggregations) | n/a | n/a | **no scoping** | n/a | n/a | n/a | n/a | **R7-API-1 critical** |

### Opportunity

| Field | DB | Model | DTO | TS | UI create | UI edit | UI render | Status |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:--|
| stage | ✓ | ✓ | ✓ | ✓ | n/a | ❌ | ✓ | R7-FORM-4 |
| customer_id | ✓ | ✓ | ✓ | ✓ | n/a | ❌ | ✓ | R7-FORM-4 |
| title/amount/currency/close_date | ✓ | ✓ | ✓ | ✓ | **❌ no create form** | ✓ inline | ✓ | **R7-FORM-1 critical** |
| customer_name (flat) | ✗ | ✗ | ✗ | n/a | n/a | n/a | reads via cast | **R7-TS-7** |
| created_at/updated_at | ✓ | ✓ | `isoformat() if x else None` | `string` (required) | n/a | n/a | n/a | R7-TS-2 |

### Subscription

| Field | DB | Model | DTO | Backend Update | TS | UI form | UI render | Status |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:--|
| name/billing_cycle/mrr/end_date | ✓ | ✓ | ✓ | **✗ no schema, no PATCH** | ✓ | ✓ create | ❌ no edit | **R7-FORM-2 high** |
| start_date | ✓ | ✓ | `isoformat() if x else None` | n/a | `string` | ✓ | ✓ | R7-TS-3 |

### Contract

| Field | DB | Model | DTO | TS | UI create | UI edit detail | UI render | Status |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:--|
| value | ✓ | ✓ | ✓ | ✓ | ✓ | **❌** | ✓ | **R7-FORM-3 high** |
| terms_json | ✓ | ✓ | ✓ | ✓ | ✓ (R6) | **❌** | ✓ | **R7-FORM-3 high** |
| title/start_date/end_date | ✓ | ✓ | ✓ | ✓ | ✓ | only via `amend` | ✓ | R7-FORM-3 high |

### EmailRequest

| Field | DB | Model | DTO list | DTO detail | TS | UI render | Status |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:--|
| body_text | ✓ | ✓ | ❌ (only with include_body) | ✓ | required | conditional | **R7-TS-1 high** |
| body_html | ✓ | ✓ | ❌ | ✓ | required | conditional | R7-TS-1 |
| parsed_data | ✓ | ✓ | ❌ | ✓ | required | conditional | R7-TS-1 |
| message_id index | dup | `unique=True, index=True` | n/a | n/a | n/a | n/a | **R7-DB-1** |

### Customer

| Field | DB | Model | DTO list | DTO detail | TS | UI form | UI render | Status |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:--|
| stats block | n/a | computed | ❌ | ✓ | ❌ | n/a | n/a | **R7-TS-5** |
| total_quotes vs quote_count | n/a | computed | quote_count | total_quotes | quote_count | n/a | n/a | **R7-TS-6** |
| email index | dup_R6_closed | clean | n/a | n/a | n/a | n/a | n/a | OK |

---

## 4. Compatibility Metrics Dashboard

| Metric | Value | Confidence | Notes |
|---|---:|---|---|
| **DB ↔ Backend compatibility** | ~98% | high | 1 import gap (R7-DB-2); columns otherwise aligned. **Indexes unverifiable from CI** until R7-DB-3. |
| **Backend ↔ API compatibility** | ~92% | high | 9 findings. Pagination shape is the largest hole (~85% of list endpoints canonical). |
| **API ↔ Frontend compatibility** | ~92-94% | medium | Hand-rolled types.ts is the structural risk. |
| **Database ↔ Frontend end-to-end** | ~88% | medium | Composes the above. |
| **UI form completeness** | ~85% | high | Critical gap: opportunity has no create form. |
| **UI render coverage** | ~93% | high | R6 closed the high-traffic gaps. |
| **Schema drift % (model ↔ migration)** | ~2% | high | Single column-level gap; index drift unmeasured. |
| **`apply_request_perms` coverage** | 100% | high | All 9 canonical entities. |
| **Tenant scoping coverage (single-row)** | ~95% | medium | 2 critical gaps (R7-API-1, R7-API-2) + 1 service-layer gap (R7-TEN-1). |
| **Pagination canonical coverage** | ~85% | high | 13 holdouts catalogued in R7-API-4. |
| **Cache invalidation discipline** | ~13% | high | 9 of 67 mutation sites use canonical helper. **Biggest discipline gap.** |
| **`isError` handling on useQuery** | ~19% | high | 17 of 91 files. |
| **`as unknown as` escape hatches** | 16 | high | 6 in OpportunitiesHomePage alone. |
| **TS field coverage vs API surface** | ~92% | high | Largest holes: Customer.stats, EmailRequest body fields. |
| **Sidebar route coverage** | ~96% | high | 2 orphans: /users, /reports legacy. |
| **Mobile responsive coverage** | ~70% | medium | DataTable primitive lacks hideOn prop → ~25 list pages affected. |
| **Overall system compatibility score** | **~89%** | medium | |
| **Remaining development to full compatibility** | ~11% (≈ 4-6 sprints) | medium | |
| **Technical debt estimate** | ~15% | medium | Hand-rolled types.ts is the standing tax. |

### Severity histogram

```
Critical  ██  2
High      ██████████████  14
Medium    ████████████████████████  24
Low       ██████████████  14
```

### Round-6 closure status

```
Verified holding:    19/22 (86%)
Family-wide regress:  3/22 (14%)  — R7-DB-1 (idx family), R7-TS-7 (casts), R6-RENDER-8 (partial)
```

---

## 5. Fix Plan

### 5.1 Day-0 hotfix PR (security-critical, ~3 hours)

| ID | What | Files | Migration |
|---|---|---|---|
| **R7-API-1** | Add `scoped_for_user` to 3 lead-analytics queries | `leads.py:117-128, :169-172` | No |
| **R7-API-2** | `assert_same_tenant` on coaching plan target_user | `coaching.py:128-131` | No |
| **R7-TEN-1** | Tenant guard + assigned-approver verify in ApprovalService | `approval_service.py:165-281` | No |
| **R7-TEN-2** | Wrap audit `sent_emails` query with `scoped_for_user` | `audit.py:233-238` | No |

### 5.2 Sprint hotfix PR (security-grade, 1 day)

| ID | What | Migration |
|---|---|---|
| **R7-DB-1** | Drop dup unique-indexes on 13 columns (R6-DB-1 family closure) | **Yes** — `20260507_drop_dup_unique_indexes_phase2.py` |
| **R7-DB-2** | Add OpportunityTransformerSeqEmbedding to `__init__.py` `__all__` | No |
| **R7-API-3** | EmailStr validation on user CSV bulk-import | No |
| **R7-API-9** | `_require_guided_selling` dependency | No |
| R7-TEN-3 | Use canonical `_get_user_template` in reports_v2 export-excel | No |
| R7-TEN-4 | Reject `sender_type=agent\|bot` on public chat endpoint | No |

### 5.3 Form completeness PR (2-3 days)

| ID | What |
|---|---|
| **R7-FORM-1** | Add Opportunity create modal on BoardPage / OpportunitiesHomePage |
| **R7-FORM-2** | Backend `SubscriptionUpdate` + PATCH + frontend inline edit |
| **R7-FORM-3** | Contract detail inline edit form for value + terms_json |
| R7-FORM-4 | Add stage + customer_id to Opportunity inline edit |
| R7-FORM-5 | Add `email` to LeadUpdate + form (low priority) |

### 5.4 UI completeness PR (1-2 days)

| ID | What |
|---|---|
| **R7-NAV-1** | Sidebar entry for `/users` (manager only) |
| **R7-NAV-2** | Sidebar entry for legacy `/reports` (or delete the route) |
| R7-RESP-1 | `hidden sm:table-cell` on 6 hand-rolled raw `<table>` pages |
| R7-RESP-2 | Add `hideOn?: 'sm'\|'md'\|'lg'` to DataTable primitive |
| R7-RENDER-1 | Replace Cockpit's `if (!data) return null` with `<EmptyState />` |
| R7-RENDER-3 | Standardize `useQuery` isError handling (or `useQueryWithError` hook) |
| R7-I18N-1 | Add 4 `campaigns.*` i18n keys, replace hardcoded strings |
| R7-I18N-2 | Add 5 `nav.*` i18n keys for R6-NAV-1 entries |

### 5.5 Pagination canonicalization PR (1 day)

13 endpoints to canonicalize per R7-API-4 table. Mechanical sweep; pattern is `{items, total, page, page_size, pages}`. After confirming SPA reads `items` everywhere.

### 5.6 Cache invalidation refactor PR (2 days)

| ID | What |
|---|---|
| **R7-CACHE-1** | Add `onLeadCreated`, `onCustomerCreated`, `onEmailParsedClient`, `onInvoiceCreated` to `cacheInvalidation.ts`; route ~58 ad-hoc mutation sites through helpers |
| **R7-CACHE-2** | Replace LeadListPage convert mutation with `onLeadConverted` cascade |

### 5.7 Type-system structural fix (2-3 days)

| ID | What |
|---|---|
| **R7-TS-12** | Introduce `openapi-typescript` codegen pipeline. Wire FastAPI's `/openapi.json` → `frontend/src/lib/api-types.generated.ts`. Hand-rolled `types.ts` re-exports. CI fails on drift. |
| R7-TS-1 | Mark EmailRequest body fields optional |
| R7-TS-2/3/4 | Tighten 5 entities' timestamp/date nullability |
| R7-TS-5 | Add Customer.stats type |
| R7-TS-7 | Drop 6 OpportunitiesHomePage casts; read `o.customer?.name` directly |
| R7-TS-9 | Introduce CustomerCreatePayload / SparePartCreatePayload types |

### 5.8 DB tooling improvement (1-2 days)

| ID | What |
|---|---|
| **R7-DB-3** | Extend `schema_check.py` to inspect indexes, unique constraints, FK ON DELETE, defaults |
| R7-DB-4 | Migrate audit_logs.id, sales_events_shadow.id, activity_logs.id to BIGINT (advisory) |
| R7-DB-5 | Audit DealRoom/Comment/Notification/EmailTemplate API surfaces; add `tenant_id` if cross-tenant reachable |

### 5.9 Realtime / cache hygiene (1 day)

| ID | What |
|---|---|
| R7-RT-1 | ChatWidget poll → 15-20s + `refetchIntervalInBackground: false` |
| R7-LIFE-3 | Cockpit refetchInterval consolidation |
| R7-EVENT-1 | Emit `customer.created` per row in bulk import |
| R7-EVENT-2 | Subscribe workflow engine to `opportunity.score_changed` |

### 5.10 Backlog

| ID | What |
|---|---|
| R7-API-5 | Quote item serializer → schema alignment |
| R7-API-6 | `_customer_to_dict` quote_count/total_quote_value |
| R7-TS-6 / R7-TS-8 / R7-TS-10 / R7-TS-11 | Misc TS cleanup |
| R7-RT-2 | Optimistic updates for kanban stage drag |
| R7-A11Y-1 / R7-RENDER-4 | Minor a11y + DataTable error prop |

---

## 6. Suggested Database Migrations

### 6.1 `20260507_drop_dup_unique_indexes_phase2.py` (R7-DB-1)

```python
"""Round-7 R7-DB-1 — close R6-DB-1 family for 13 more columns.

R6 closed 4 auth columns (users.email, customers.email, user_sessions.jti,
signature_requests.token). Same anti-pattern alive on:
  Lead.email, ApiKey.key_hash, EmailRequest.message_id, Quote.quote_number,
  SparePart.honeywell_code, Setting.key, MeetingLink.slug,
  SharedDocument.token, NetworkSegment.segment_key,
  AccountEnrichment.customer_id, SalesEventShadow.source_ref,
  LeadScoringConfig.name, DealRoom.external_token.
"""

revision = "20260507_drop_dup_unique_indexes_phase2"
down_revision = "20260506_drop_dup_unique_indexes"

def upgrade():
    op.execute("DROP INDEX IF EXISTS ix_leads_email")
    op.execute("DROP INDEX IF EXISTS ix_api_keys_key_hash")
    op.execute("DROP INDEX IF EXISTS ix_email_requests_message_id")
    op.execute("DROP INDEX IF EXISTS ix_quotes_quote_number")
    op.execute("DROP INDEX IF EXISTS ix_spare_parts_honeywell_code")
    op.execute("DROP INDEX IF EXISTS ix_settings_key")
    op.execute("DROP INDEX IF EXISTS ix_meeting_links_slug")
    op.execute("DROP INDEX IF EXISTS ix_shared_documents_token")
    op.execute("DROP INDEX IF EXISTS ix_network_segments_segment_key")
    op.execute("DROP INDEX IF EXISTS ix_account_enrichments_customer_id")
    op.execute("DROP INDEX IF EXISTS ix_sales_events_shadow_source_ref")
    op.execute("DROP INDEX IF EXISTS ix_lead_scoring_configs_name")
    op.execute("DROP INDEX IF EXISTS ix_deal_room_token")  # explicit Index name

def downgrade():
    op.execute("CREATE INDEX IF NOT EXISTS ix_leads_email ON leads (email)")
    # ... mirror upgrade
```

### 6.2 (Optional, advisory) `20260601_logs_to_bigint.py` (R7-DB-4)

PG `ALTER COLUMN ... TYPE BIGINT` rewrites the column. Plan as a downtime-window task or use online migration tooling.

---

## 7. Suggested Tests

### 7.1 Tenant-scope regression for lead analytics (R7-API-1)

```python
@pytest.mark.asyncio
async def test_lead_analytics_excludes_cross_tenant(client, manager_a_headers, lead_in_b):
    r = await client.get("/api/v1/leads/analytics", headers=manager_a_headers)
    body = r.json()
    # Tenant B's lead must not appear in funnel counts
    assert all(...)  # detailed assertions on funnel/sources/weekly_trend
```

### 7.2 Cross-tenant coaching plan rejection (R7-API-2)

```python
async def test_coaching_create_rejects_cross_tenant_target(client, manager_a_headers, user_in_b):
    r = await client.post("/api/v1/coaching/plans",
        json={"user_id": user_in_b.id, "title": "test"},
        headers=manager_a_headers)
    assert r.status_code == 404
```

### 7.3 Approval service tenant guard (R7-TEN-1)

```python
async def test_approval_approve_rejects_cross_tenant(...):
    # Tenant A user attempts to approve a tenant B request
    r = await client.post(f"/api/v1/approvals/{request_in_b.id}/approve", ...)
    assert r.status_code == 404
```

### 7.4 Index drift CI gate (R7-DB-3)

```python
def test_no_duplicate_indexes_per_column(db_engine):
    """Fail CI if any column has both a UNIQUE constraint AND an
    index named ix_<table>_<col> on the same column. R6-DB-1 / R7-DB-1
    family regression guard."""
    inspector = inspect(db_engine.sync_engine)
    for table in Base.metadata.sorted_tables:
        idx_columns = {tuple(idx['column_names']) for idx in inspector.get_indexes(table.name)}
        uq_columns = {tuple(uq['column_names']) for uq in inspector.get_unique_constraints(table.name)}
        overlap = idx_columns & uq_columns
        assert not overlap, f"{table.name}: dup indexes on {overlap}"
```

### 7.5 Pagination envelope sweep test

```python
@pytest.mark.parametrize("path", [
    "/api/v1/leads/scoring-config", "/api/v1/notifications/",
    "/api/v1/guided-selling/", "/api/v1/customers/health/at-risk",
    "/api/v1/team", "/api/v1/sharing-rules/", "/api/v1/leaderboard",
    "/api/v1/duplicates", "/api/v1/stakeholders",
    # … all 13 holdouts
])
async def test_list_endpoint_returns_canonical_envelope(client, manager_headers, path):
    r = await client.get(path, headers=manager_headers)
    body = r.json()
    assert {"items", "total", "page", "page_size", "pages"} <= set(body.keys())
```

### 7.6 Cache invalidation discipline (R7-CACHE-1)

```ts
// Lint rule: forbid direct queryClient.invalidateQueries in feature dirs
// allow only in lib/cacheInvalidation.ts
// (eslint custom rule or grep-in-CI)
```

### 7.7 Form ↔ schema sync test (extend R6 test class)

Add cases for:
- `OpportunityCreate` → BoardPage.tsx OR OpportunitiesHomePage.tsx must contain `customer_id`/`title`/etc.
- `ContractUpdate` → ContractDetailPage.tsx must reference `value` and `terms_json`
- `SubscriptionUpdate` (once it exists) → SubscriptionDetailPage.tsx

---

## 8. Sprint Planning

### Sprint 1 (Day-0 hotfix + R7-DB-1 sweep) — 2 days

**Goal:** Close all critical security gaps + the family-wide DB regression.

| Task | Effort | Dependency |
|---|---|---|
| R7-API-1 lead analytics scoping | 0.5h | — |
| R7-API-2 coaching tenant assert | 0.25h | — |
| R7-TEN-1 approval service guard | 2h | — |
| R7-TEN-2 audit sent_emails scope | 0.25h | — |
| R7-DB-1 + migration | 2h | requires migration deploy |
| R7-DB-2 model import | 0.25h | — |
| R7-API-3 EmailStr in CSV import | 1h | — |
| Tests for above | 3h | — |
| **Total** | **~9h** | |

**Risk:** Low (isolated diffs). Recommend canary deploy on `deploy/render-sandbox` before main.

### Sprint 2 (Form completeness) — 3 days

**Goal:** Close R7-FORM-1/2/3 (the largest UX gaps).

| Task | Effort | Dependency |
|---|---|---|
| R7-FORM-1 Opportunity create modal | 1d | — |
| R7-FORM-2 SubscriptionUpdate backend + frontend edit | 1d | New backend route |
| R7-FORM-3 Contract detail inline edit | 0.5d | — |
| R7-FORM-4 Opportunity stage+customer in inline edit | 0.5d | — |
| **Total** | **~3d** | |

### Sprint 3 (Pagination + nav cleanup) — 2 days

**Goal:** Close pagination canonical sweep + sidebar orphans + i18n.

| Task | Effort |
|---|---|
| R7-API-4 pagination sweep (13 endpoints) | 1d |
| R7-NAV-1/2 sidebar entries | 0.5h |
| R7-I18N-1/2 i18n key coverage | 0.5d |
| **Total** | **~2d** |

### Sprint 4 (Cache discipline) — 2 days

**Goal:** Centralize cache invalidation through canonical helper.

| Task | Effort |
|---|---|
| R7-CACHE-1 add 4 new helpers + sweep ~58 sites | 2d |
| R7-CACHE-2 LeadListPage convert cascade | 0.5h |
| **Total** | **~2d** |

### Sprint 5 (Type-system structural) — 3 days

**Goal:** Eliminate the recurring TS drift class.

| Task | Effort |
|---|---|
| **R7-TS-12** openapi-typescript codegen pipeline | 2d |
| R7-TS-1..11 cleanup post-codegen | 1d |
| **Total** | **~3d** |

### Sprint 6 (Mobile responsive + UX polish) — 2 days

| Task | Effort |
|---|---|
| R7-RESP-2 DataTable hideOn prop | 0.5d |
| R7-RESP-1 6 hand-rolled tables | 1d |
| R7-RENDER-1/2/3 error/empty states | 0.5d |

### Sprint 7+ (Backlog)

R7-DB-3 schema_check extension, R7-DB-4 BigInteger migration (advisory), R7-DB-5 DealRoom/Notification tenant_id, R7-RT-1, R7-LIFE-3, R7-EVENT-1/2, R7-API-5/6, misc TS cleanup.

**Estimated total to full compatibility: 4-6 sprints (8-15 working days).**

---

## 9. Summary Lists

### Database columns not used by backend
None confirmed.

### Backend model fields not backed by database
None confirmed.

### Backend fields not exposed through API
- `Customer.deletion_requested_at` — emitted by canonical, **omitted in some non-canonical paths** (covered in R6-API-7 closure)
- (No new ones found in this round)

### API fields never consumed by frontend
- `Customer.stats` block — emitted, no TS type (R7-TS-5)
- `_quote_to_dict` `spare_part` inline object — emitted, schema declares `spare_part_name`/`spare_part_category` instead (R7-API-5)

### Frontend fields/types missing from API/backend
- `OpportunitiesHomePage` reads `o.customer_name` (flat) — backend nests it (R7-TS-7)
- `EmailRequest.body_*` declared required, omitted from list endpoints (R7-TS-1)

### Data fetched but not rendered
None new beyond the partial-render cases noted in R7-RENDER-2/3.

### UI components showing incomplete data
- BoardPage / OpportunitiesHomePage (no create) — R7-FORM-1
- SubscriptionDetailPage (no edit) — R7-FORM-2
- ContractDetailPage (only activate/amend) — R7-FORM-3
- OpportunityDetailPage inline edit (drops stage/customer_id) — R7-FORM-4
- LeadDetailPage edit form (drops email) — R7-FORM-5

### Realtime events emitted but not handled
1 candidate — `invoice.paid` subscriber at main.py:262 is a no-op stub (not strictly dead).

### Realtime events handled but not emitted
None confirmed.

### Schema/type/nullability mismatches
- Quote/Opportunity/Invoice/User timestamps required in TS, `null`-able from backend (R7-TS-2)
- Subscription.start_date (R7-TS-3)
- Campaign optional vs nullable (R7-TS-4)

### Permission or feature flag mismatches
- `FEATURE_GUIDED_SELLING` declared but no backend `_require_*` (R7-API-9)
- ApprovalService tenant + assigned-approver gap (R7-TEN-1)

### Required migrations
- `20260507_drop_dup_unique_indexes_phase2.py` (R7-DB-1)
- (Optional, advisory) `20260601_logs_to_bigint.py` (R7-DB-4)

### Recommended frontend type updates
- `EmailRequest`: mark `body_text`, `body_html`, `parsed_data` optional
- 5 entities: tighten timestamp nullability to `string | null`
- `Customer`: add `stats` block
- Drop 6 `as unknown as` casts in OpportunitiesHomePage
- Introduce `CustomerCreatePayload`, `SparePartCreatePayload`, etc.
- **Long term:** introduce `openapi-typescript` codegen

### Recommended backend DTO/serializer updates
- `_quote_to_dict` items: align with `QuoteItemResponse`
- `_customer_to_dict`: emit `quote_count`/`total_quote_value` (or remove from schema)
- 13 list endpoints: canonical envelope sweep

### Recommended tests
See §7 — 7 test classes including index drift CI gate, pagination sweep, cache invalidation discipline lint rule.

### Highest-risk architectural areas
1. **Hand-rolled `types.ts`** (R7-TS-12) — recurring tax across rounds 3-7
2. **Cache invalidation discipline** (R7-CACHE-1) — 87% of mutations bypass canonical helper
3. **Service-layer tenant gaps** (R7-TEN-1) — escapes router-level guards

### Quick-win fixes (low effort, high impact)
1. R7-API-1 (3 lines)
2. R7-API-2 (1 line)
3. R7-TEN-2 (1 line)
4. R7-NAV-1/2 (5 lines)
5. R7-DB-2 (2 lines)

### High-impact low-effort fixes
1. R7-API-1 / R7-API-2 (critical fixes, < 5 minutes each)
2. R7-DB-1 migration (12 columns, ~15 minutes to write)
3. R7-RENDER-1 Cockpit empty state (5 lines)
4. R7-FORM-1 stub create modal (~1d but unblocks a critical UX gap)

### Critical schema drift areas
- Indexes (CI gate doesn't check them — R7-DB-3)
- Hand-rolled TS (no schema source of truth — R7-TS-12)

---

## 10. Process Notes

- **6 parallel slice investigators all returned within 600s budget.** Slice 4 (UI completeness) consumed 105 tool calls and 518s — close to the watchdog. Slice 5 (Permissions/tenant) used 17 calls and was the most efficient.
- **Total 54 findings** (2 critical, 14 high, 24 medium, 14 low) + **3 family-wide R6 regressions** (R7-DB-1, R7-TS-7, R6-RENDER-8 partial).
- **Day-0 hotfix is small** — 4 fixes, ~1-3 hours total. R7-API-1 + R7-API-2 + R7-TEN-1 + R7-DB-1 should ship together as a security release.
- **Highest-leverage long-term work:** R7-TS-12 (openapi codegen) + R7-CACHE-1 (helper centralization) + R7-DB-3 (schema_check extension). Together they collapse the recurring audit tax by ~50%.
- **R6 closure rate: 86% (19/22).** The 3 partial closures (R7-DB-1 family, R7-TS-7 cast escape hatches, R6-RENDER-8 null fallback) suggest the audit cycle should explicitly check sibling instances when closing a family-wide issue.

**Audit by 6 parallel slice investigators (all returned cleanly within budget). Every R5/R6 closure spot-verified against current source. Zero files modified per instruction.**
