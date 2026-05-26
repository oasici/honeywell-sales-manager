# Enterprise Hardening Plan — Honeywell Sales Suite (Round-19 → Round-22)

**Date:** 2026-05-26
**Status:** Phase 1 partial-execution in progress (this session).
**Source audit:** `docs/audits/2026-05-22-email-pipeline-round-18.md` + UAT audit (2026-05-26 conversation).

---

## Finding Index

| ID | Finding | Phase | Status |
|---|---|---|---|
| F-001 | Per-tenant DEK envelope encryption | 1 | **SHIPPED Phase 4** (in-PG envelope, KMS swap target) |
| F-002 | Email auth=fail skips LLM | 1 | **SHIPPED Phase 1** |
| F-003 | OCR truncation blocks auto-quote | 1 | **SHIPPED Phase 1** |
| F-004 | First-time-sender manual review | 1 | **SHIPPED Phase 1** |
| F-005 | `/admin/merge` POST + CSRF + nonce | 1 | **SHIPPED Phase 4** (nonce service ready; FE consumes next) |
| F-006 | e-Sign OTP + recipient binding | 2 | **SHIPPED Phase 4** (email-only, no SMS) |
| F-007 | Soft/hard delete policy | 2 | **SHIPPED Phase 4** (universal mixin + tombstones on 7 entities) |
| F-008 | CSV/Excel injection sanitization | 1 | **SHIPPED Phase 1** |
| F-009 | Reports Builder tenant injection + RLS | 2 | DEFERRED — RLS overhead not justified at 20-30 users |
| F-010 | Approval rule self-disable meta-approval | 2 | **SHIPPED Phase 2** |
| F-011 | Operations role split | 2 | **SHIPPED Phase 4** (3 sub-roles + ops_audit; auto-migration) |
| F-012 | Multi-currency forecast | 4 | **SHIPPED Phase 6** (per-currency + base-currency rollup with FX snapshot) |
| F-013 | JWT JTI blocklist | 2 | **SHIPPED Phase 2** (PG-backed) |
| F-014 | Health debounce + batching | 4 | **SHIPPED Phase 6** (in-process dirty-set + LRU eviction; Redis swap-ready) |
| F-015 | Workflow rule cycle detection | 3 | **SHIPPED Phase 2** |
| F-016 | RFQ aggregation 14-day window | 3 | **EXECUTING this session** |
| F-017 | Quote optimistic locking | 3 | **SHIPPED Phase 2** (`row_version` column + helper) |
| F-018 | Approval quorum policy | 3 | **SHIPPED Phase 3** (quorum_policy + decisions ledger) |
| F-019 | Email Message-Id idempotency | 1 | **EXECUTING this session** |
| F-020 | Constant-time 404 cross-tenant | 1 | **EXECUTING this session** |
| F-021 | Bulk imports | 4 | **SHIPPED Phase 5** (CSV: customers + parts, 10K row cap, sync) |
| F-022 | Mobile responsive | 3 | DEFERRED — UX nice-to-have (D-003 designed) |

## Hardening Design v2 (D-NNN) — Status

Tracks the 40-finding follow-up specified in `docs/qa/HARDENING_DESIGN_V2.md`.
Phases align with v2's roadmap; status reflects actual shipped code.

| ID | Title | Status |
|---|---|---|
| D-001 | RLS rollout (5 tables) | DEFERRED — needs middleware sprint |
| D-002 | KMS migration | DEFERRED — needs AWS account |
| D-003 | Mobile responsive | DEFERRED — needs design pass |
| D-004 | AI Tasks model + cron | DEFERRED — new feature |
| D-005 | Coaching Hooks model + watermark | DEFERRED — new feature |
| D-006 | Per-account login rate limit | **SHIPPED** Phase 8 |
| D-007 | JWT rotate on login | DEFERRED — micro-task |
| D-008 | Per-tenant at_risk_threshold | **SHIPPED** Phase 8 |
| D-009 | OCC on remaining 7 entities | DEFERRED — incremental |
| D-010 | Cross-tenant probe detection | **SHIPPED** Phase 8 |
| D-011 | Quote total server-side | **VERIFIED SHIPPED** (schema already enforces) |
| D-012 | Approval decisions ledger + 409 | **SHIPPED** Phase 11 |
| D-013 | Workflow cycle save-time + runtime guard | **SHIPPED** Phase 10 |
| D-014 | Sign-OTP SMTP wire | **SHIPPED** Phase 8 |
| D-015 | KVKK subject notification | **SHIPPED** Phase 8 |
| D-016 | KVKK export worker | **SHIPPED** Phase 8 |
| D-017 | Per-tenant DEK rotation script | DEFERRED — pairs with D-002 |
| D-018 | Field-permission decorator | **SHIPPED** Phase 9 |
| D-019 | DLQ writer + admin endpoints | **SHIPPED** Phase 8 |
| D-020 | Soft-delete on 6 entities | **SHIPPED** Phase 8/CI-fix (model columns) |
| D-021 | Audit log partitioning | DEFERRED — operational |
| D-022 | Notification prefs UI | DEFERRED — feature |
| D-023 | Active sessions table | **SHIPPED** Phase 8 (schema; auth.py has endpoints) |
| D-024 | Sequence unsubscribe placement | **SHIPPED** Phase 8 |
| D-025 | Multi-pipeline support | DEFERRED — feature |
| D-026 | Plan model + subscription mapping | DEFERRED — feature |
| D-027 | TSA-signed timestamps | DEFERRED — needs TSA vendor |
| D-028 | Email pipeline retry on AI fail | DEFERRED — micro-task |
| D-029 | Approval delegation expiry sweep | **SHIPPED** Phase 8 |
| D-030 | Trash UI + bulk restore | DEFERRED — UX |
| D-031 | Bulk import leads + opps | **SHIPPED** Phase 9 (leads); opps deferred |
| D-032 | Outbound webhooks | DEFERRED — feature |
| D-033 | Health zero-data bias | **SHIPPED** Phase 8 |
| D-034 | Forecast cron tenant-local time | DEFERRED — config refactor |
| D-035 | Reports Builder streaming | DEFERRED — refactor |
| D-036 | Audit log explorer UI | DEFERRED — UX |
| D-037 | Playwright E2E harness | DEFERRED — testing infra |
| D-038 | Chaos test harness | DEFERRED — testing infra |
| D-039 | Backup + DR runbook | DEFERRED — operational |
| D-040 | SAST/DAST CI workflow | **SHIPPED** Phase 8 |

**Shipped: 17 of 40 (43%)** with explicit deferral rationale for the rest.
Phase 1 critical items: 8 of 8 shipped.
Phase 2 priorities: D-013, D-018, D-023 schema shipped; D-001 + D-002 are the
remaining 2 large items, both pending infra decisions.
Phase 3 quick wins: D-024, D-029, D-031 (leads), D-033 shipped.
| F-023 | KVKK two-person rule | 3 | **SHIPPED Phase 4** (state machine + DB CHECK constraint) |
| F-024 | Sequences mandatory unsubscribe | 3 | **SHIPPED Phase 4** (validator + opt-out registry) |
| F-025 | AI coaching watermark + preview | 3 | **SCHEMA SHIPPED Phase 2** (cols on `coaching_hooks`; logic awaits model presence) |
| F-026 | Quote v1 supersede | 3 | **SHIPPED Phase 3** (superseded_by_id + helpers) |
| F-027 | Pricing precedence | 3 | **SHIPPED Phase 3** (`price_source` + resolver) |
| F-028 | Approval SLA + escalation | 3 | **SHIPPED Phase 3** (due_at + escalation_level + sla helpers) |
| F-029 | Per-tenant auto-quote threshold | 4 | **SHIPPED Phase 2** |
| F-030 | AI Task auto-dismiss | 3 | **SCHEMA SHIPPED Phase 2** (cols on `ai_tasks`; cron awaits model presence) |

---

## Phase 1 Execution Scope (this session)

Pure-code, no-infra items. The remainder needs human decisions on:
- **KMS vendor** (AWS KMS vs Vault vs GCP) for F-001
- **Operations role split mapping** for F-011
- **PostgreSQL RLS rollout plan** for F-009
- **Redis introduction** for F-013, F-014

Items executed:
- **F-002** Auth=fail short-circuits LLM in email processing
- **F-003** OCR truncation blocks auto-quote eligibility
- **F-004** First-time-sender flag + auto-quote block
- **F-008** CSV injection sanitization for all exports
- **F-016** RFQ aggregation: sender_email + 14-day window (replaces sender_domain-only)
- **F-019** Email Message-Id idempotency (unique index + ON CONFLICT DO NOTHING)
- **F-020** Constant-time 404 cross-tenant audit (single-query pattern verified)

---

## Roadmap (5 phases, ~12 months to enterprise GA)

| Phase | Duration | Effort (dev-weeks) | Outcome |
|---|---|---|---|
| 1 | 4-6 weeks | ~20 | Production-ready for pilot |
| 2 | 6-8 weeks | ~30 | SOC 2 Type II ready |
| 3 | 6-8 weeks | ~25 | Trusted workflows |
| 4 | 8-12 weeks | ~40 | 10K user-ready |
| 5 | Continuous (12mo+) | ~120+ | Enterprise GA |

(Full per-finding fix specifications retained in the 2026-05-26 conversation transcript; see also Round-18 audit doc for the email-pipeline subset.)
