# Email Feature — Hardening Audit

> **Date:** 2026-06-02 · **Scope:** the inbound email feature end-to-end — IMAP ingestion (scheduled + manual), sender-auth, attachment handling/AV, tenant isolation on email read paths, and the parse→review→auto-quote workflow.
> **Method:** direct first-hand code review (no reliance on USER_MANUAL.md). Every finding carries a `file:line` reference verified at audit time.
> **Standard:** a paying multi-tenant pilot — no spoofed sender may auto-quote, no attachment may be parsed unscanned when a scanner is configured, and no user may read another tenant's email.
>
> **Status:** ✅ **REMEDIATED 2026-06-02.** E1–E4 + E6–E7 fixed test-first; E5 documented as a known limitation. See "Remediation status" below.

---

## Remediation status (executed 2026-06-02)

| # | Sev | Fix shipped | Tests |
|---|---|---|---|
| E1 | HIGH | New `app/services/email_ingestion_service.ingest_fetched_email` is the single row builder; both the manual `/poll` and `scheduler._run_imap_poll` call it. Scheduled rows now carry `sender_auth_status` + `tenant_id` (resolved from the persisted `email_owner_user_id`) + `attachments_json`. | `test_email_ingestion_hardening.py::TestIngestStampsFields`, `::TestSchedulerPollParity` |
| E2 | HIGH | `scan_attachments` wired into the shared routine; infected ⇒ `text`/`heuristic_parts` cleared, `av_status` recorded in `attachments_json`, `review_status=pending_review`, `parse_skipped_reason="av_infected"`; `_auto_quote_eligible` blocks on that reason. Default `_NoopScanner` ⇒ no behavioural change. | `::TestAvScanWiring`, `::TestAutoQuoteGateAv` |
| E3 | HIGH | `list_emails` now applies `scoped_for_user(..., column=EmailRequest.tenant_id)` to both the page and count queries. | `::TestListTenantIsolation` |
| E4 | MED | `/{id}/thread` member query is `scoped_for_user`-filtered. | (covered by the scoping helper; manual verify) |
| E5 | MED | **Documented, not changed** — single global mailbox; per-tenant inbound routing deferred. The scheduler now attributes ingested mail to the configuring manager's tenant as the best available signal. | — |
| E6 | LOW | Internal-domain skip now lives in the shared routine ⇒ both paths apply it. | `::TestSkips::test_internal_domain_skipped` |
| E7 | LOW | Shared routine guards the INSERT with a `SAVEPOINT` (`begin_nested`) so a concurrent-poll `message_id` race drops only that row. | `::TestSkips::test_duplicate_message_id_skipped` |

**New/changed files:** `app/services/email_ingestion_service.py` (new), `app/tasks/scheduler.py`, `app/api/v1/emails.py`, `app/api/v1/settings.py`, `app/services/email_processing_service.py`; tests `tests/test_email_ingestion_hardening.py`.

**Note for the manual:** §6.1 step 9 (AV) and the scheduled-poll auth/tenant behaviour described in `USER_MANUAL.md` are now actually true. The manual was intentionally not consulted for this audit; a separate pass can drop the discrepancy notes added on 2026-06-01.

---

## 0. The two ingestion paths (this is the root of most findings)

There are **two** ways an `EmailRequest` row is created from IMAP, and they do **not** share code:

```
A. Manual  POST /emails/poll   →  emails.poll_emails()              [emails.py:249]
      _fetch_emails_via_imap → per-item: dup-skip, internal-skip, OCR enrich,
      build row WITH {tenant_id, sender_auth_status, attachments_json,
      truncation flags}, IntegrityError-guarded flush, process_email()   ✅ thorough

B. Cron    poll_emails_via_imap_task → _run_imap_poll()             [scheduler.py:83]
      _fetch_emails_via_imap → build row with ONLY {message_id, from,
      subject, body, is_read, status, received_at}                      ⚠ drops everything else
      → later parsed by batch_process_pending_emails()
```

Both call the **same** `_fetch_emails_via_imap`, which already returns `sender_auth_status`, `attachments`, and `raw_attachments` for every message ([emails.py:1000-1015](../../backend/app/api/v1/emails.py#L1000)). Path B simply throws that data away. Every divergence below follows from these being two hand-maintained copies instead of one shared routine.

---

## 1. HIGH — security / correctness

### E1 — Scheduled IMAP poll bypasses the auth gate, tenancy, and attachment parsing
- **Where:** `backend/app/tasks/scheduler.py:126-134` (`_run_imap_poll`).
- **What:** the row is built with only `message_id / from_address / subject / body_text / is_read / status / received_at`. It omits `sender_auth_status`, `tenant_id`, and `attachments_json` — all of which `_fetch_emails_via_imap` already computed and returned.
- **Why it matters:**
  1. **Auth-gate bypass.** `batch_process_pending_emails` later parses the row, and `_auto_quote_eligible` reads `sender_auth_status`. With it `NULL`, the guard `if auth and auth != "pass"` is a **no-op** ([email_processing_service.py:64-66](../../backend/app/services/email_processing_service.py#L64)). A spoofed/unauthenticated sender that arrives via the cron poll is **eligible to auto-quote** — the exact thing F-002 was built to stop. (The manual `/poll` sets it, so the spoof is only let through on the scheduled path.)
  2. **Tenant-less rows.** `tenant_id` is `NULL`, so every cross-tenant guard no-ops for these rows and they're unattributed in a multi-tenant deployment.
  3. **Lost attachment parts.** `attachments_json` is never set, so a spreadsheet/PDF RFQ ingested by cron looks like an empty body — the heuristic part rows never reach `parsed_data`.
- **Contrast:** the manual path does all three correctly ([emails.py:438-454](../../backend/app/api/v1/emails.py#L438)).

### E2 — AV scan hook is dead code; attachment bytes are never scanned
- **Where:** `backend/app/services/email_av_scanner.py` (`scan_attachments`, fully implemented + 5 passing tests) — **invoked nowhere**. `grep -rn scan_attachments app/` returns only the definition.
- **What:** `raw_attachments` (the actual bytes) are explicitly dropped before persistence ("NOT serialised to the DB" — [emails.py:1009-1013](../../backend/app/api/v1/emails.py#L1009)); nothing scans them first. Attachments are handed to `openpyxl` / `pdfplumber` / PIL / Claude Vision **unscanned**.
- **Also:** the module docstring claims "the column lands on the email row so ops can audit what was checked," but **no `av_status` column exists** on `EmailRequest` ([email_request.py](../../backend/app/models/email_request.py)).
- **Impact:** with `AV_SCAN_BACKEND=clamav` configured, ops would reasonably believe attachments are scanned; they are not.

### E3 — `list_emails` has no tenant filter (managers see every tenant's mail)
- **Where:** `backend/app/api/v1/emails.py:62-119`.
- **What:** the only scoping condition is `assigned_to == current_user.id` **for non-managers**. A `SALES_MANAGER` gets **no tenant filter at all** → the list returns emails across **all** tenants. Non-managers are incidentally safe (a user belongs to one tenant, so `assigned_to` implies same-tenant), but managers are not.
- **Violates** the documented invariant in `CLAUDE.md`: "Every list endpoint must use `scoped_for_user(stmt, current_user, column=Model.tenant_id)`."

---

## 2. MEDIUM

### E4 — `/{email_id}/thread` returns thread members without a tenant filter
- **Where:** `backend/app/api/v1/emails.py:534-539`.
- **What:** the anchor email is tenant-checked (`_assert_email_same_tenant`), but the follow-up query selects **all** rows with the same `thread_id` and is **not** tenant-scoped. `thread_id` comes from message headers and can collide across tenants → a crafted/colliding thread id could surface foreign-tenant emails in the thread view.

### E5 — Single global mailbox: inbound email is not per-tenant (architectural)
- **Where:** IMAP credentials live in the global `Setting` table (key/value, **no `tenant_id`** — [setting.py](../../backend/app/models/setting.py)); `_get_imap_credentials` ([scheduler.py:45](../../backend/app/tasks/scheduler.py#L45)) reads one shared set.
- **What:** there is exactly one configured mailbox for the whole deployment and no mailbox→tenant mapping. So the scheduled poll has no principled way to know which tenant an inbound email belongs to. Acceptable for the **single-tenant pilot** (tenant_id stays `NULL`), but true multi-tenant inbound routing is undefined and must be designed before onboarding a second tenant's mailbox.

---

## 3. LOW

- **E6 — Cron poll skips the internal-domain filter.** The manual path drops mail from `internal_domains_list` ([emails.py:333-335](../../backend/app/api/v1/emails.py#L333)); the scheduler doesn't, so internal/no-reply mail gets ingested and LLM-parsed on the cron path.
- **E7 — Cron poll lacks the F-019 idempotency guard.** It does SELECT-then-INSERT with an `existing_ids` set but no `IntegrityError` rollback; a concurrent manual+cron poll can raise on the unique `message_id`. The manual path handles this ([emails.py:461-470](../../backend/app/api/v1/emails.py#L461)).

---

## 4. What is genuinely solid (build on this)

- **Manual `/poll` is thorough** — auth verdict, attachment payload, OCR enrichment, truncation flags, tenant stamp, idempotency, then `process_email`.
- **IMAP TLS** uses an explicit context with `check_hostname=True` + `CERT_REQUIRED` ([emails.py:856-859](../../backend/app/api/v1/emails.py#L856)).
- **`auth=fail` short-circuit** skips the LLM entirely (no Anthropic spend on spoofs) and routes to review ([email_processing_service.py:156-162](../../backend/app/services/email_processing_service.py#L156)).
- **Bleach** HTML sanitization + table→Markdown before store; **attachment whitelist + size caps**; `openpyxl(keep_vba=False)`.
- **Detail/link endpoints** use `assert_same_tenant` (404, not 403) + cross-tenant probe detection.
- **IMAP password encrypted at rest** (`_decrypt_password`).
- **Catalog resolver + the 2026-06-01 spare-parts zero-tolerance hardening** sit downstream and are well-tested.

---

## 5. Remediation plan (executed in the same change set)

| # | Fix | Findings closed |
|---|---|---|
| R1 | **Extract one shared ingestion routine** (`email_ingestion_service.ingest_fetched_email`) used by BOTH the manual `/poll` and the scheduler, so the two paths can't drift. The scheduler resolves the owning user/tenant from a persisted `email_owner_user_id` setting (NULL fallback = single-tenant). | E1, E6, E7 |
| R2 | **Wire `scan_attachments` into the shared routine.** Infected → `review_status=pending_review` + `parse_skipped_reason="av_infected"` + the infected attachment's text is dropped (not fed to the LLM). Per-attachment `av_status` is stored inside `attachments_json` (no migration). Default `_NoopScanner` ⇒ no behavioural change unless ops sets `AV_SCAN_BACKEND`. | E2 |
| R3 | `scoped_for_user(stmt, current_user, column=EmailRequest.tenant_id)` on `list_emails` (count + page queries). | E3 |
| R4 | Tenant-scope the thread-members query. | E4 |
| R5 | Document the global-mailbox limitation; defer the per-tenant-mailbox redesign. | E5 (documented) |

**Test-first:** each fix lands with a failing test that encodes the invariant (scheduled-poll row carries auth+tenant+attachments; infected attachment routes to review; manager list is tenant-scoped; thread query is tenant-scoped), then the fix makes it pass.

**Files of record:** `app/tasks/scheduler.py`, `app/api/v1/emails.py`, `app/api/v1/settings.py`, `app/services/email_av_scanner.py`, `app/services/email_processing_service.py`, `app/models/email_request.py`, `app/models/setting.py`; companion: `docs/audits/2026-06-01-spare-parts-extraction-audit.md`.
