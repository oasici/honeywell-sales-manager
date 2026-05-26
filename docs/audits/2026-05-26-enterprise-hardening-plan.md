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
| F-012 | Multi-currency forecast | 4 | DEFERRED — first international customer trigger |
| F-013 | JWT JTI blocklist | 2 | **SHIPPED Phase 2** (PG-backed) |
| F-014 | Health debounce + batching | 4 | DEFERRED — no bulk imports at 20-30 users scale |
| F-015 | Workflow rule cycle detection | 3 | **SHIPPED Phase 2** |
| F-016 | RFQ aggregation 14-day window | 3 | **EXECUTING this session** |
| F-017 | Quote optimistic locking | 3 | **SHIPPED Phase 2** (`row_version` column + helper) |
| F-018 | Approval quorum policy | 3 | **SHIPPED Phase 3** (quorum_policy + decisions ledger) |
| F-019 | Email Message-Id idempotency | 1 | **EXECUTING this session** |
| F-020 | Constant-time 404 cross-tenant | 1 | **EXECUTING this session** |
| F-021 | Bulk imports | 4 | **SHIPPED Phase 5** (CSV: customers + parts, 10K row cap, sync) |
| F-022 | Mobile responsive | 3 | DEFERRED — UX nice-to-have |
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
