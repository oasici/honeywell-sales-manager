# Honeywell Sales Suite — Production Hardening Design v2

> **Date:** 2026-05-26. **Auditor stance:** adversarial.
> **Inputs:** `MASTER_TEST_COVERAGE.md`, Round-19 audit (16:53 session), shipped commits up to `f414ae9`.
> **Authority:** This document defines the next 6-12 months of hardening work. Every finding has a buildable solution; no hand-waving allowed.
>
> **What this is NOT:** a repeat of the v1 audit. v1 catalogued *what's broken*. v2 catalogues *what's not finished after Round-19* and **prescribes the exact engineering work to finish it**.
>
> Findings are renumbered **D-001 to D-NNN** (D = "design v2") to avoid collision with the original F-NNN findings that are now shipped.

---

## Index of Findings

| ID | Finding | Phase | Severity |
|---|---|---|---|
| D-001 | RLS rollout for top-5 sensitive tables | 5 | Critical (defence-in-depth) |
| D-002 | KMS migration path (per-tenant DEK swap) | 5 | Critical (security maturity) |
| D-003 | Mobile responsive critical paths | 3 | High (UX) |
| D-004 | AI Tasks model + auto-dismiss runtime | 3 | High |
| D-005 | Coaching Hooks model + AI watermark runtime | 3 | High (defamation risk) |
| D-006 | Per-account rate limit (login) — not IP-only | 2 | High (security) |
| D-007 | JWT rotation on every login (anti-fixation) | 2 | High |
| D-008 | Tenant config: `at_risk_threshold` field | 3 | Medium |
| D-009 | OCC across remaining 7 entities | 3 | Medium |
| D-010 | Server-side query log to detect cross-tenant probe | 2 | High (security) |
| D-011 | Quote total computed server-side; UI value rejected | 3 | Medium |
| D-012 | Approval-decision DB UNIQUE(request,decider) wired into endpoint | 3 | High |
| D-013 | Workflow-rule save-time cycle blocker | 3 | High |
| D-014 | Sign-OTP send_email backend (SMTP wire) | 2 | Critical |
| D-015 | KVKK subject-notification email on export-done | 2 | High (legal) |
| D-016 | KVKK export worker (actual data collection) | 3 | Critical (legal) |
| D-017 | Per-tenant DEK rotation script | 5 | Medium |
| D-018 | Field-permission middleware on every serialiser | 2 | Critical |
| D-019 | DLQ for failed background jobs | 4 | High |
| D-020 | Soft-delete migration sweep on remaining 6 entities | 3 | High |
| D-021 | Audit log partitioning + 7-year archival | 4 | Medium |
| D-022 | Notification preferences UI + critical-alert override | 3 | Medium |
| D-023 | Session table for "active sessions" management | 2 | Medium |
| D-024 | Sequence template editor enforces unsubscribe placement | 3 | Low |
| D-025 | Multi-pipeline support (per-tenant stage configs) | 5 | Medium |
| D-026 | Plan model + plan-feature map (Subscriptions) | 5 | High |
| D-027 | TSA-signed timestamp on contracts | 5 | Critical (legal) |
| D-028 | Email-pipeline retry on transient AI/Vision failure | 3 | Medium |
| D-029 | Approval delegation expiry sweep | 3 | Medium |
| D-030 | "Trash" view per entity + bulk restore | 3 | Low |
| D-031 | Bulk-import for leads + opportunities | 4 | Medium |
| D-032 | Webhook outbound — Phase 5 launch | 4 | Medium |
| D-033 | Customer Health: zero-data bias correction | 3 | Medium |
| D-034 | Forecast cron at tenant-local time, not UTC | 3 | Low |
| D-035 | Reports Builder: streaming output for > 10K rows | 4 | Medium |
| D-036 | Audit log explorer UI (currently table only) | 3 | Low |
| D-037 | E2E test runner harness (Playwright) | 3 | High |
| D-038 | Chaos test harness (kill-on-demand) | 5 | Medium |
| D-039 | Backup + DR runbook (RTO ≤ 4h, RPO ≤ 1h) | 5 | Critical |
| D-040 | DAST + SAST in CI gates | 2 | High |

---

## D-001 · PostgreSQL RLS Rollout for Top-5 Sensitive Tables

### Problem Summary
At 20-30 user pilot scale `assert_same_tenant` is sufficient defence — but the moment the first paying enterprise customer signs, defence-in-depth becomes non-negotiable. Round-19 explicitly deferred RLS because of overhead + middleware risk. We need a *bounded* rollout (5 tables, not all 60).

### Root Cause
ORM-layer tenant scoping is "trust every author of every endpoint to remember the helper." One missed call = leak. RLS makes it a DB-level invariant.

### Real Production Risk
- Cross-tenant data leak via any missed `assert_same_tenant`.
- SOC 2 CC6.1 ("logical separation") audit fail without RLS.
- Customer churn + KVKK exposure on any leak.

### Exact Fix Recommendation

**Tables in scope (initial rollout):** `customers`, `quotes`, `invoices`, `contracts`, `opportunities`.

**Backend Fix:**
```python
# app/core/database.py — middleware wraps every request session
@app.middleware("http")
async def inject_tenant_setting(request: Request, call_next):
    user = await _maybe_get_user(request)
    if user and user.tenant_id is not None:
        # SET LOCAL only — auto-reverts on session close
        async with engine.begin() as conn:
            await conn.execute(
                text("SET LOCAL app.current_tenant_id = :tid"),
                {"tid": user.tenant_id},
            )
    return await call_next(request)
```

**Database Fix:**
```sql
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON customers
  FOR ALL TO app_role
  USING (tenant_id = current_setting('app.current_tenant_id', true)::bigint);

-- Repeat for quotes, invoices, contracts, opportunities.

-- App user gets restricted permissions:
CREATE ROLE app_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON customers TO app_role;
-- Migration runs as superuser; runtime app uses app_role.
```

**Security Fix:**
- Background jobs use a separate ``bg_role`` that has `BYPASSRLS` on a per-tenant `SET ROLE bg_role` block so retention sweeps work across tenants.
- Audit log writer uses `audit_writer` role — also RLS-bypass but write-only.

**Scalability Fix:**
- RLS adds 3-5ms per query. Acceptable at any scale we're forecasting through 2027.
- Indexes already include `tenant_id` as the leading column on these 5 tables.

**UX Improvement:** N/A (invisible to users; silent strengthening).

**Monitoring:**
- `pg_stat_statements` shows query plans; verify RLS predicates push down into index scans.
- Alert: any 5xx that contains `app.current_tenant_id is null` → middleware bug.

**Test Coverage:**
- Integration: SET app.current_tenant_id=1, SELECT * FROM customers WHERE id IN (foreign rows) → 0 rows.
- Negative: drop the middleware → tests must fail (proves RLS is enforced).
- Performance: p99 latency before/after on 10K-customer dataset → < 5ms regression.

**UAT Scenario:**

| Step | Action | Test Data | Expected Result |
|---|---|---|---|
| 1 | Tenant A user logs in | — | SET LOCAL fired |
| 2 | Query customers via API | — | Only Tenant A rows |
| 3 | DB query log inspection | — | Plan shows RLS filter applied at index scan |
| 4 | Misconfigure middleware (test only) | — | All requests 503 (fails closed) |
| 5 | Tenant B login | — | Different SET LOCAL; isolated |
| 6 | Audit log writer (separate role) | — | Sees all tenants (BYPASSRLS) |

**Severity:** Critical. **Complexity:** L (5-7 dev-weeks). **Priority:** P1 (when first paying enterprise signs).

---

## D-002 · KMS Migration (Replace Single Master Fernet)

### Problem Summary
F-001 shipped per-tenant DEK isolation using a single Fernet KEK in env. A leaked env still exposes every wrapped DEK. Production-grade requires KMS (AWS KMS, Vault Transit, GCP KMS).

### Root Cause
KMS adds operational complexity + cost. Round-19 deferred it because 20-30 user pilot doesn't justify it.

### Real Production Risk
- Operator with prod env access can decrypt every DEK and therefore every IMAP password.
- SOC 2 CC6.3 requires "least privilege" — env-var KEK fails this.
- Enterprise procurement will reject single-KEK design at deal-review stage.

### Exact Fix Recommendation

**Backend Fix:**
The Phase 4 F-001 module isolated the swap point. Replace the body of `crypto_v2._get_kek` / `_wrap_dek` / `_unwrap_dek`:

```python
# app/core/crypto_v2.py — KMS-backed version
import boto3
_kms = boto3.client("kms", region_name=settings.AWS_REGION)

def _wrap_dek(plain_dek: bytes) -> bytes:
    resp = _kms.encrypt(
        KeyId=settings.KMS_KEY_ARN,
        Plaintext=plain_dek,
        EncryptionContext={"tenant_id": "system"},
    )
    return resp["CiphertextBlob"]

def _unwrap_dek(wrapped: bytes) -> bytes:
    resp = _kms.decrypt(
        CiphertextBlob=wrapped,
        EncryptionContext={"tenant_id": "system"},
    )
    return resp["Plaintext"]
```

**Migration plan:**
1. Provision KMS key in AWS (eu-central-1 for Turkish data residency).
2. Grant `kms:Encrypt` + `kms:Decrypt` to Render service IAM role only.
3. Deploy KMS-aware crypto module with feature flag `USE_KMS=false`.
4. Run rotation: for each tenant_dek row, unwrap with old KEK, re-wrap with KMS.
5. Flip `USE_KMS=true`. Verify metrics.
6. Remove env-var KEK from secrets.

**Security Fix:**
- KMS key policy: only `arn:aws:iam::ACCOUNT:role/honeywell-render-prod` allowed.
- All KMS calls audit-logged to CloudTrail.
- Quarterly key rotation: `aws kms enable-key-rotation`.

**Scalability Fix:**
- DEK cache (already implemented) keeps KMS calls to ~1 per tenant per 5 min.
- KMS regional throughput: 5500 req/sec — never hit at 20-30 users.

**Monitoring:**
- Metric: `kms_decrypt_duration_seconds_p99` — alert > 500ms.
- Metric: `kms_decrypt_errors_total` — alert > 0.
- CloudWatch alarm on KMS spend > $5/month.

**Severity:** Critical (security maturity). **Complexity:** M (2-3 weeks including AWS account setup). **Priority:** P2.

---

## D-003 · Mobile Responsive Critical Paths

### Problem Summary
F-022 deferred. Sales reps on the road need mobile access for at least: Cockpit view, customer detail (read), approve a pending request, sign quote-recall, KVKK request file. Currently the app is desktop-first; mobile is broken.

### Root Cause
No design pass for mobile flows. Tailwind CSS-first design but components don't break responsively.

### Real Production Risk
- Field-rep complaints; productivity loss.
- Manager approvals delayed because manager is between meetings on a phone.

### Exact Fix Recommendation

**Critical paths to make mobile-first (320-428px width):**

| Path | Current State | Target |
|---|---|---|
| Login | Works | Already mobile-ready |
| Cockpit | Cards overlap | Single column; cards stack; lazy-load below fold |
| Customer list | Table breaks | Card-view at < 768px; priority columns only (name + tier + health) |
| Customer detail | OK | Sticky header; collapsible sections |
| Approval queue | OK | Decision buttons sticky-bottom; one-tap Approve/Reject |
| Quote PDF view | OK | Mobile PDF viewer; share via OS dialog |
| e-Sign | OK (public) | Already works |

**Frontend Fix:**
```tsx
// Customer list — switch table for cards at < md
{isMobile ? (
  <div className="grid gap-3">
    {customers.map((c) => <CustomerCard key={c.id} customer={c} />)}
  </div>
) : (
  <CustomerDataTable rows={customers} />
)}
```

Add `useMediaQuery` hook reading `(min-width: 768px)`.

**UX Improvement:**
- Touch targets ≥ 44×44px enforced (already CLAUDE.md rule).
- Bottom-action-bar pattern for primary CTAs on detail pages.
- Swipe-down to refresh customer list.
- Bottom-sheet modal pattern (replaces center-aligned desktop modal).

**Accessibility:**
- All buttons keyboard-reachable (Tab order top-down).
- aria-current="page" on active sidebar item.
- VoiceOver tested on iOS Safari.

**Test Coverage:**
- E2E: Playwright with viewport 375×667 (iPhone SE).
- Visual regression: Chromatic snapshots for Cockpit / Customer list / Approval at 320 / 375 / 768.
- Manual: 1 hour test session on real iPhone + Android device.

**UAT Scenario:**

| Step | Action | Test Data | Expected Result |
|---|---|---|---|
| 1 | Open app on iPhone 12 (390px) | — | Login works |
| 2 | Cockpit | — | Cards stack vertically, no horizontal scroll |
| 3 | Customer list | search Demir | Card-view, tap navigates |
| 4 | Open approval | — | "Onayla" + "Reddet" sticky bottom |
| 5 | Approve | — | Confirms in single tap |
| 6 | Rotate to landscape | — | Layout adapts; sidebar collapses to hamburger |

**Severity:** High (field rep blocker). **Complexity:** M (3-4 weeks design + impl). **Priority:** P2.

---

## D-004 · AI Tasks Model + Auto-Dismiss Runtime

### Problem Summary
F-030 schema-staged: `ai_tasks.dismissed_at` + `stale_dismissed` columns exist via migration, but **the model class doesn't exist** so the cron can't run. Cockpit "Bugünün Görevleri" card is empty/broken.

### Root Cause
AI Tasks was sketched in CLAUDE.md but never implemented as a model.

### Real Production Risk
- Cockpit shows a card that never has data → user confusion.
- Sales managers can't see their AI-generated next-actions.

### Exact Fix Recommendation

**Backend Fix:**

```python
# app/models/ai_task.py — NEW
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

class AiTask(Base):
    __tablename__ = "ai_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    assigned_to: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True
    )
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

**Cron addition (extending scheduler.py):**

```python
async def r19_ai_task_aging_task():
    """F-030 — auto-dismiss AI tasks > 30d open."""
    from app.core.database import async_session
    from sqlalchemy import text

    async with async_session() as db:
        res = await db.execute(text(
            "UPDATE ai_tasks SET stale_dismissed = true, dismissed_at = now() "
            "WHERE status = 'open' "
            "  AND created_at < now() - interval '30 days' "
            "  AND stale_dismissed = false"
        ))
        await db.commit()
        if res.rowcount:
            logger.info("AI task aging cron dismissed %d stale tasks", res.rowcount)
```

Register hourly:
```python
scheduler.add_job(
    lambda: asyncio.ensure_future(_tracked("ai_task_aging", r19_ai_task_aging_task)),
    "interval", hours=1, id="ai_task_aging", replace_existing=True,
)
```

**API Endpoints:**
```
GET    /ai/tasks                  — own open + in_progress
POST   /ai/tasks/{id}/start       — status=in_progress
POST   /ai/tasks/{id}/complete    — status=completed
POST   /ai/tasks/{id}/dismiss     — manual dismiss (with reason)
```

**Test Coverage:**
- Unit: Create task 35d old → cron marks it stale_dismissed.
- Unit: Recent task untouched.
- Permission: Other user can't see / modify my task.

**Severity:** High. **Complexity:** S (1 week). **Priority:** P2.

---

## D-005 · Coaching Hooks Model + AI Watermark Runtime

### Problem Summary
F-025 schema-staged but no model. Manager UX shows AI-generated coaching tips as if human-written — defamation risk if AI hallucinates ("competitor X is bankrupt").

### Root Cause
Same as D-004 — schema landed early; logic deferred.

### Exact Fix Recommendation

**Backend Fix:**

```python
# app/models/coaching_hook.py — NEW
class CoachingHook(Base):
    __tablename__ = "coaching_hooks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    rep_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    coach_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    opportunity_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("opportunities.id"), nullable=True)
    transcript_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("transcripts.id"), nullable=True)
    suggestion_text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    # F-025 watermark fields — already in migration
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    manager_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    manager_reviewed_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    manager_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|reviewed|sent|archived
```

**Critical business rule:**
```python
def is_publishable(hook: CoachingHook) -> bool:
    if not hook.ai_generated:
        return True  # human-authored, no review gate
    if hook.ai_confidence is None or hook.ai_confidence < 0.7:
        return False  # low confidence → manager review required
    return hook.manager_reviewed is True
```

**API:**
```
POST   /coaching/hooks/{id}/publish
  → enforces is_publishable; refuses with 422 if ai_generated + not reviewed.
```

**Frontend Fix:**
Coaching panel renders AI tips with a clear visual treatment:
```tsx
{hook.ai_generated && !hook.manager_reviewed && (
  <Badge variant="warning">🤖 AI önerisi — yönetici incelemesi gerekli</Badge>
)}
{hook.ai_generated && hook.manager_reviewed && (
  <Badge variant="info">🤖 AI önerisi (incelendi)</Badge>
)}
```

Publish button is disabled until `manager_reviewed=true`.

**Audit Logging:**
- Every publish event records: `ai_generated`, `ai_confidence`, `reviewed_by`, `edited_text != null`.

**Test Coverage:**
- Unit: AI hook with confidence 0.6 → cannot publish.
- Unit: Same with manager_reviewed=true → can publish.
- E2E: Manager edits AI suggestion before publishing → audit log captures original + edit.

**Severity:** High (defamation risk). **Complexity:** S (1 week). **Priority:** P2.

---

## D-006 · Per-Account Login Rate Limit (Not IP-Only)

### Problem Summary
Round-19 TC-AUTH-002 flagged: 5 wrong attempts → 15-min lockout, but only by IP. An attacker rotating IPs (cheap) defeats the limit.

### Root Cause
Rate limiter implemented on a deque of timestamps keyed by IP. Pre-Round-19 design choice.

### Real Production Risk
- Credential stuffing succeeds against any account with a guessable password.
- Compliance frameworks (NIST 800-63B) require per-account counter.

### Exact Fix Recommendation

**Backend Fix:**

```python
# app/services/login_rate_limiter.py — NEW
from collections import defaultdict
from datetime import datetime, timedelta, timezone

_FAILED_ATTEMPTS: defaultdict[str, list[datetime]] = defaultdict(list)
_LOCKOUT_UNTIL: dict[str, datetime] = {}

MAX_ATTEMPTS = 5
WINDOW = timedelta(minutes=15)
LOCKOUT = timedelta(minutes=15)


def record_failure(email: str) -> None:
    now = datetime.now(timezone.utc)
    _FAILED_ATTEMPTS[email] = [
        t for t in _FAILED_ATTEMPTS[email]
        if t > now - WINDOW
    ]
    _FAILED_ATTEMPTS[email].append(now)
    if len(_FAILED_ATTEMPTS[email]) >= MAX_ATTEMPTS:
        _LOCKOUT_UNTIL[email] = now + LOCKOUT


def is_locked(email: str) -> bool:
    until = _LOCKOUT_UNTIL.get(email)
    if until is None:
        return False
    if datetime.now(timezone.utc) >= until:
        _LOCKOUT_UNTIL.pop(email, None)
        _FAILED_ATTEMPTS.pop(email, None)
        return False
    return True


def record_success(email: str) -> None:
    _FAILED_ATTEMPTS.pop(email, None)
    _LOCKOUT_UNTIL.pop(email, None)
```

Wire into `/auth/login`:
```python
if is_locked(payload.email):
    raise HTTPException(429, detail="account_locked_try_again_later")
user = await authenticate(payload.email, payload.password)
if user is None:
    record_failure(payload.email)
    raise HTTPException(401, detail="invalid_credentials")
record_success(payload.email)
```

**Database Fix (for persistence across restarts):**

```sql
CREATE TABLE login_lockouts (
  email_lower VARCHAR(320) PRIMARY KEY,
  failed_count INTEGER NOT NULL DEFAULT 0,
  last_failure_at TIMESTAMPTZ NOT NULL,
  locked_until TIMESTAMPTZ
);
```

In-memory accelerator + PG fallback so a restart doesn't clear lockouts.

**Security Fix:**
- On 3 failures: send email to user "Suspicious login attempts."
- On 5 failures: lock + send email; admin alerted if 10 lockouts/hour platform-wide.

**Notification:**
- User receives "Hesabınız 15 dakika kilitlendi — siz değilseniz şifrenizi değiştirin" with reset link.

**Test Coverage:**
- Distributed IP attack: 5 wrong attempts from 5 different IPs → still locked (per-account).
- Correct password after lockout → 429.
- After 15 min → 200.

**Severity:** High. **Complexity:** S (3 days). **Priority:** P1.

---

## D-007 · JWT Rotation on Every Login (Anti-Fixation)

### Problem Summary
TC-AUTH-007: A pre-issued cookie could survive a login. Server doesn't rotate session ID on login.

### Root Cause
Stateless JWT design; no "session" concept.

### Exact Fix Recommendation

**Backend Fix:**
On every login, regardless of incoming state:
1. Generate fresh JTI for access + refresh tokens.
2. If incoming Authorization or cookie carries a JTI, add it to the blocklist.
3. Issue new cookies; client uses them.

```python
@router.post("/auth/login")
async def login(payload, request, response, db):
    user = await authenticate(...)
    # Anti-fixation: kill any pre-existing session this request carried.
    old_jti = _extract_jti_from_request(request)
    if old_jti:
        await revoke_jti_persistent(db, jti=old_jti, exp_ts=..., reason="pre_login_rotate")
    # Issue fresh tokens with new JTIs (already done; just confirm).
    access = create_access_token({"sub": str(user.id)})
    ...
```

**Test:** TC-AUTH-007 verifies.

**Severity:** High. **Complexity:** S (2 days). **Priority:** P1.

---

## D-008 · Tenant Config — `at_risk_threshold` Field

### Problem Summary
TC-COCKPIT-004 calls for per-tenant At-Risk threshold; currently hardcoded `< 40`.

### Exact Fix Recommendation

**Database Fix:** Add column to `tenant_settings`:
```sql
ALTER TABLE tenant_settings
  ADD COLUMN IF NOT EXISTS at_risk_threshold INTEGER NOT NULL DEFAULT 40
  CHECK (at_risk_threshold BETWEEN 0 AND 100);
```

**Backend:** Read in Cockpit `/cockpit/at-risk-customers` endpoint:
```python
cfg = await get_tenant_settings(db, current_user.tenant_id)
threshold = cfg.at_risk_threshold
rows = await db.execute(
    select(Customer).where(
        Customer.tenant_id == current_user.tenant_id,
        Customer.health_score < threshold,
        Customer.deleted_at.is_(None),
    )
)
```

**Frontend:** Tenant Settings page exposes the slider 0-100.

**Severity:** Medium. **Complexity:** S (1 day). **Priority:** P3.

---

## D-009 · OCC Across Remaining 7 Entities

### Problem Summary
Phase 7 added `row_version` to customers, opportunities, contracts. Still need it on: invoices, subscriptions, campaigns, leads, email_request (parsed_data edits), workflow_rules, approval_rules.

### Exact Fix Recommendation

**Migration `20260710_phase8_occ_complete`:**
```sql
ALTER TABLE invoices         ADD COLUMN IF NOT EXISTS row_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE subscriptions    ADD COLUMN IF NOT EXISTS row_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE campaigns        ADD COLUMN IF NOT EXISTS row_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE leads            ADD COLUMN IF NOT EXISTS row_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE email_requests   ADD COLUMN IF NOT EXISTS row_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE workflow_rules   ADD COLUMN IF NOT EXISTS row_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE approval_rules   ADD COLUMN IF NOT EXISTS row_version INTEGER NOT NULL DEFAULT 1;
```

**Model updates:** Same pattern as Phase 7.

**Endpoint updates:**
Every PUT/PATCH on these entities now requires `row_version` field in the body. Missing → 422 `row_version_required`.

**Frontend:**
Forms capture `row_version` on load, submit on save, surface 409 → "Bu kayıt başka biri tarafından değiştirildi" modal with three-way diff.

**Severity:** Medium. **Complexity:** M (1-2 weeks). **Priority:** P3.

---

## D-010 · Server-Side Cross-Tenant Probe Detection

### Problem Summary
F-020 constant-time 404 closes the timing channel but doesn't *alert* on probe attempts. An attacker scanning every ID for cross-tenant existence is a security event we should know about.

### Exact Fix Recommendation

**Backend Fix:**

```python
# app/services/tenant_context.py — extend existing helper
async def record_cross_tenant_attempt(
    db, *,
    user_id: int, user_tenant: int,
    attempted_entity: str, attempted_id: int,
):
    await db.execute(text(
        "INSERT INTO cross_tenant_attempts "
        "(user_id, user_tenant, attempted_entity, attempted_id, attempted_at) "
        "VALUES (:uid, :tid, :ent, :eid, now())"
    ), {...})

# Call from load_with_tenant_check when obj is None due to tenant filter
```

**DB:** New table:
```sql
CREATE TABLE cross_tenant_attempts (
  id BIGSERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL,
  user_tenant INTEGER NOT NULL,
  attempted_entity VARCHAR(40) NOT NULL,
  attempted_id BIGINT NOT NULL,
  attempted_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_cta_user_time ON cross_tenant_attempts (user_id, attempted_at DESC);
```

**Monitoring:**
- Alert: > 10 attempts/hour from one user → operations on-call paged.
- Daily report: top 10 probing users.

**Severity:** High. **Complexity:** S (1 week). **Priority:** P1.

---

## D-011 · Quote Total Computed Server-Side

### Problem Summary
TC-QUOTE-001: quote total is auto-calculated server-side per the test, but the current API accepts client-provided `total` field. A malicious client can submit `total=0`.

### Exact Fix Recommendation

**Backend Fix:**

```python
# app/schemas/quote.py
class QuoteCreate(BaseModel):
    customer_id: int
    opportunity_id: int | None = None
    lines: list[QuoteLineCreate]
    # NOTE: no `total`, `vat`, `subtotal` fields here.
    #       Server computes from lines.

# app/api/v1/quotes.py
async def create_quote(payload, ...):
    subtotal = sum(Decimal(l.unit_price) * l.quantity * (1 - Decimal(l.discount_pct)/100) for l in payload.lines)
    vat = subtotal * Decimal("0.18")
    total = subtotal + vat
    # Save with computed values, ignore any client claim.
```

**API:** Any incoming `total` / `vat` / `subtotal` keys are silently dropped (or 422 if strict).

**Test:** Submit `{"total": 1}` → server computes correct total + ignores.

**Severity:** Medium. **Complexity:** S (2 days). **Priority:** P2.

---

## D-012 · Approval-Decision UNIQUE Constraint Wired into Endpoint

### Problem Summary
F-018 added `UNIQUE(request_id, decider_id)` on `approval_decisions`. The endpoint must translate IntegrityError → 409 with a friendly message, not 500.

### Exact Fix Recommendation

**Backend Fix:**

```python
@router.post("/approvals/{request_id}/decide")
async def decide(request_id, payload, current_user, db):
    from sqlalchemy.exc import IntegrityError
    try:
        await db.execute(text(
            "INSERT INTO approval_decisions (request_id, decider_id, outcome, comment) "
            "VALUES (:r, :u, :o, :c)"
        ), {...})
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, detail={"code": "already_decided"})
    # Aggregate state via compute_quorum_state
    ...
```

**Test:** Same approver clicks Approve twice in 100ms → first wins, second gets 409.

**Severity:** High. **Complexity:** S (3 days). **Priority:** P2.

---

## D-013 · Workflow-Rule Save-Time Cycle Blocker

### Problem Summary
F-015 service exists; not wired into the rule-save endpoint.

### Exact Fix Recommendation

**Backend Fix:**

```python
@router.post("/admin/workflow-rules")
async def create_rule(payload, ...):
    from app.services.workflow_cycle_detector import detect_static_cycles
    all_rules = await db.scalars(select(WorkflowRule).where(WorkflowRule.tenant_id == ...))
    candidate = WorkflowRule(...)  # not yet persisted
    cycles = detect_static_cycles([*all_rules, candidate])
    if cycles:
        raise HTTPException(422, detail={
            "code": "cycle_detected",
            "cycles": [list(c) for c in cycles],
        })
    db.add(candidate)
    ...
```

**Test:** Save rule A→B→C→A → 422 with cycle list.

**Severity:** High. **Complexity:** S (3 days). **Priority:** P2.

---

## D-014 · Sign-OTP SMTP Wire

### Problem Summary
F-006 endpoint exists but `_send_otp_email` only logs at DEBUG; no real SMTP send. e-Sign is unusable in production until this wires.

### Exact Fix Recommendation

**Backend Fix:**

```python
# app/api/v1/sign_otp.py — replace stub
async def _send_otp_email(to: str, subject: str, body: str) -> None:
    from app.services.smtp_service import send_email_sync  # existing module
    await asyncio.to_thread(send_email_sync, to, subject, body)
```

If `app.services.smtp_service` doesn't exist (it's also from CLAUDE.md's "Integrations" surface), build a thin wrapper around `aiosmtplib` reading tenant SMTP creds from settings table.

**Security:**
- SMTP creds Fernet-encrypted (now per-tenant DEK).
- Send failures logged + retry up to 3× exponential.

**Test:**
- Issue token + send-otp → mock SMTP receives email with subject "Elektronik imza doğrulama kodu"; body contains 6-digit code.

**Severity:** Critical (legal blocker for e-Sign). **Complexity:** S (1 week). **Priority:** P1.

---

## D-015 · KVKK Subject Notification on Export Done

### Problem Summary
TC-KVKK-003: subject should receive notification when their data is exported. Currently silent.

### Exact Fix Recommendation

**Backend Fix:**

```python
# app/services/kvkk_two_person.py — extend mark_done
async def mark_done(db, request_id, *, artifact_url):
    ...
    # F-015 — send notification to the subject
    row = (await db.execute(text(
        "SELECT subject_lookup, subject_kind FROM kvkk_export_requests WHERE id = :id"
    ), {"id": request_id})).first()
    if row and row.subject_kind == "email":
        from app.services.smtp_service import send_email_sync
        send_email_sync(
            row.subject_lookup,
            "Verileriniz dışa aktarıldı",
            f"KVKK Madde 11 kapsamındaki talebiniz {datetime.now()} tarihinde işlenmiştir. "
            f"Export #{request_id}. Sorular için: support@firma.com"
        )
```

**Severity:** High (legal). **Complexity:** S (2 days). **Priority:** P1.

---

## D-016 · KVKK Export Worker (Data Collection)

### Problem Summary
F-023 has the state-machine endpoints but **no actual worker** that collects the subject's data into a ZIP. After approve+execute the request sits at `executing` forever.

### Exact Fix Recommendation

**Background worker:**

```python
# app/services/kvkk_export_worker.py — NEW
async def run_export(db, request_id: int) -> None:
    """Collect subject data across all tables, build ZIP, upload."""
    req = await _fetch(db, request_id)
    subject = req.subject_lookup
    bundle = {}

    # 1. Customer record + KVKK consent log
    bundle["customer.json"] = await _customer_for_subject(db, subject)
    # 2. Opportunities + Quotes + Invoices + Contracts touching this subject
    bundle["opportunities.json"] = await _opps_for_subject(db, subject)
    bundle["quotes.json"] = await _quotes_for_subject(db, subject)
    bundle["invoices.json"] = await _invoices_for_subject(db, subject)
    bundle["contracts.json"] = await _contracts_for_subject(db, subject)
    # 3. Inbound + outbound emails
    bundle["emails.json"] = await _emails_for_subject(db, subject)
    # 4. Audit log entries WHERE target is this subject
    bundle["audit_log.json"] = await _audit_for_subject(db, subject)
    # IMPORTANT: exclude internal coaching notes about the subject
    # (defamation / KVKK scope question) — TC-KVKK-005 requirement.

    # Build ZIP
    import io, zipfile, json
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in bundle.items():
            z.writestr(name, json.dumps(data, ensure_ascii=False, indent=2, default=str))

    # Upload (S3 or local /var/lib/kvkk-exports)
    artifact_url = await _upload(buf.getvalue(), request_id)
    await mark_done(db, request_id, artifact_url=artifact_url)
    # Subject notification fires from inside mark_done (see D-015).
```

**Trigger:**
The `/kvkk-export/requests/{id}/execute` endpoint already calls `mark_executing`. Append:
```python
asyncio.create_task(run_export(db, request_id))
```

For a robust production version, use a job queue (Arq/RQ) — but at 20-30 user scale, in-process `create_task` is acceptable.

**Test:**
- Create + approve + execute → after ~5s, status = done, artifact_url populated, ZIP downloadable.

**Severity:** Critical (KVKK Article 11 obligation). **Complexity:** M (2 weeks). **Priority:** P1.

---

## D-017 · Per-Tenant DEK Rotation Script

### Problem Summary
F-001 has `rotate_tenant_dek()` for the DEK itself but no script that *also re-encrypts* every persisted ciphertext under the new DEK. Rotation today leaves old ciphertext unreadable.

### Exact Fix Recommendation

**Script:** `backend/scripts/rotate_tenant_data_keys.py`

```python
"""Rotate per-tenant DEK + re-encrypt every ciphertext row.

Usage:
  python scripts/rotate_tenant_data_keys.py --tenant 42 --dry-run
  python scripts/rotate_tenant_data_keys.py --tenant 42 --apply
  python scripts/rotate_tenant_data_keys.py --tenant all --apply

The columns to re-encrypt are registered in the
``_ENCRYPTED_COLUMNS`` map below. Adding a new ciphertext column to
the codebase MUST come with a corresponding entry here, else the
new column is left in old-key ciphertext after rotation.
"""

_ENCRYPTED_COLUMNS = {
    "settings": ("email_password",),
    "email_credentials": ("password_encrypted",),
    # Add as ciphertext columns proliferate.
}

async def rotate_tenant(db, tenant_id, *, apply: bool) -> dict:
    from app.core.crypto_v2 import decrypt_for_tenant, encrypt_for_tenant, rotate_tenant_dek

    # 1. Decrypt every row with the OLD DEK (use cached DEK now).
    rows_to_rewrap = []
    for table, cols in _ENCRYPTED_COLUMNS.items():
        for col in cols:
            rows = await db.execute(text(
                f"SELECT id, {col} FROM {table} WHERE tenant_id = :tid AND {col} IS NOT NULL"
            ), {"tid": tenant_id})
            for r in rows:
                plain = await decrypt_for_tenant(db, tenant_id, bytes(r[1]))
                rows_to_rewrap.append((table, col, r[0], plain))

    if not apply:
        return {"would_rotate": len(rows_to_rewrap)}

    # 2. Rotate the DEK itself.
    await rotate_tenant_dek(db, tenant_id)
    # Cache is invalidated; next encrypt_for_tenant uses new DEK.

    # 3. Re-encrypt each row.
    for table, col, row_id, plain in rows_to_rewrap:
        new_ct = await encrypt_for_tenant(db, tenant_id, plain)
        await db.execute(text(
            f"UPDATE {table} SET {col} = :ct WHERE id = :id"
        ), {"ct": new_ct, "id": row_id})

    await db.commit()
    return {"rotated": len(rows_to_rewrap)}
```

**Operational pattern:**
1. Run nightly during low traffic.
2. Per-tenant transactional — partial failure rolls back that tenant only.
3. Audit log every rotation.

**Severity:** Medium. **Complexity:** S (1 week). **Priority:** P3.

---

## D-018 · Field-Permission Middleware on Every Serialiser

### Problem Summary
CLAUDE.md says masking is applied at the end of every serialiser for `customer/quote/opportunity/lead/email/contract/invoice/subscription/campaign` (9 entities). Need to verify and lock down via a decorator.

### Exact Fix Recommendation

**Backend Fix:**

```python
# app/services/field_permission_service.py — extend
from functools import wraps

def apply_request_perms_to_response(entity_type: str):
    """Decorator. Wraps endpoint; applies masking to its return value."""
    def deco(fn):
        @wraps(fn)
        async def wrap(*args, **kwargs):
            result = await fn(*args, **kwargs)
            return apply_request_perms(result, entity_type)
        return wrap
    return deco
```

Audit every endpoint that returns one of the 9 entity types; add the decorator. Lint rule: any endpoint returning `CustomerOut` without the decorator fails CI.

**Test:**
- Sales rep GETs customer; phone masked.
- Manager GETs same; phone full.
- Negative: directly call serialiser without decorator → unmasked output proves masking applied at endpoint layer.

**Severity:** Critical. **Complexity:** M (audit + retrofit = 1-2 weeks). **Priority:** P1.

---

## D-019 · DLQ for Failed Background Jobs

### Problem Summary
The scheduler runs jobs with `_tracked()` which counts failures but doesn't preserve the failed payload. Failed retention sweeps, failed health recomputes, failed KVKK exports vanish silently.

### Exact Fix Recommendation

**DB:**
```sql
CREATE TABLE background_job_dlq (
  id BIGSERIAL PRIMARY KEY,
  job_name VARCHAR(60) NOT NULL,
  payload JSONB NOT NULL,
  error TEXT NOT NULL,
  failed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  retry_count INTEGER NOT NULL DEFAULT 0,
  resolved_at TIMESTAMPTZ,
  resolved_by INTEGER REFERENCES users(id)
);
CREATE INDEX ix_dlq_unresolved ON background_job_dlq (job_name, failed_at)
  WHERE resolved_at IS NULL;
```

**Backend Fix:**

```python
# app/tasks/scheduler.py — extend _tracked()
async def _tracked(name: str, fn) -> None:
    try:
        await fn()
        ...
    except Exception as exc:
        # Existing: counter + log
        # NEW: DLQ insert
        from app.core.database import async_session
        async with async_session() as db:
            await db.execute(text(
                "INSERT INTO background_job_dlq (job_name, payload, error) "
                "VALUES (:n, :p, :e)"
            ), {"n": name, "p": "{}", "e": str(exc)[:5000]})
            await db.commit()
```

**Admin Endpoint:**
```
GET    /admin/dlq          — list unresolved
POST   /admin/dlq/{id}/retry
POST   /admin/dlq/{id}/resolve   — manual mark resolved with note
```

**Monitoring:**
- Dashboard: DLQ count by job. Alert > 10 unresolved.

**Severity:** High. **Complexity:** S (1 week). **Priority:** P2.

---

## D-020 · Soft-Delete Migration on Remaining 6 Entities

### Problem Summary
F-007 migration added tombstone columns to 7 tables. Customer model in code got the columns; the other 6 (leads, opportunities, quotes, contracts, invoices, email_requests) still need model updates and endpoint logic to use them.

### Exact Fix Recommendation

For each of the 6:
1. Add `deleted_at`, `deleted_by`, `delete_reason` columns to the SQLAlchemy model (same as Customer).
2. Update DELETE endpoint to call `mark_deleted(row, actor_id, reason)`.
3. Update LIST endpoint to `WHERE deleted_at IS NULL` (active_filter helper).
4. Update DETAIL endpoint to 404 on deleted rows.

Lint rule: any new model with PII / financial data MUST have tombstone columns.

**Severity:** High. **Complexity:** M (one-week sprint, 6 entities). **Priority:** P2.

---

## D-021 · Audit Log Partitioning + 7-Year Archival

### Problem Summary
KVKK requires audit retention long enough to demonstrate compliance — typically 7 years. At 20-30 users, audit_log grows ~10K rows/day → 25M rows in 7 years. Single table = slow queries.

### Exact Fix Recommendation

**DB:**
```sql
-- Convert audit_log to a partitioned table.
ALTER TABLE audit_log RENAME TO audit_log_old;
CREATE TABLE audit_log (...) PARTITION BY RANGE (created_at);
CREATE TABLE audit_log_2026_q3 PARTITION OF audit_log FOR VALUES FROM ('2026-07-01') TO ('2026-10-01');
-- pg_partman manages quarterly partitions automatically.
INSERT INTO audit_log SELECT * FROM audit_log_old;
DROP TABLE audit_log_old;
```

**Archival cron (monthly):**
- Partitions > 12 months old → `pg_dump` to S3 with object-lock for 7 years.
- Detached from main DB after dump.
- Restore procedure documented.

**Severity:** Medium (compliance preparedness). **Complexity:** M (2 weeks incl. archive infra). **Priority:** P3.

---

## D-022 · Notification Preferences UI + Critical-Alert Override

### Problem Summary
Settings → Bildirim Tercihleri page exists but tests (TC-NOTIF-001) require per-event-type preferences AND critical-channel non-disable enforcement.

### Exact Fix Recommendation

**DB:**
```sql
CREATE TABLE notification_preferences (
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
  event_type VARCHAR(60),
  channel VARCHAR(20),         -- in_app | email | sms
  enabled BOOLEAN NOT NULL DEFAULT true,
  PRIMARY KEY (user_id, event_type, channel)
);
```

**Backend Fix:**

```python
_CRITICAL_EVENTS = {"security.breach", "user.locked", "kvkk.export_done"}

def should_deliver(user_id, event_type, channel) -> bool:
    if event_type in _CRITICAL_EVENTS:
        return True  # cannot be disabled
    pref = ...lookup...
    return pref.enabled if pref else True  # default opt-in
```

**Severity:** Medium. **Complexity:** S (1 week). **Priority:** P3.

---

## D-023 · Active Sessions Table

### Problem Summary
TC-AUTH-004 ("Logout everywhere") needs a table to know what to revoke. Currently JTIs are only tracked when explicitly logged out.

### Exact Fix Recommendation

**DB:**
```sql
CREATE TABLE active_sessions (
  jti UUID PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  ip INET,
  ua TEXT,
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_active_sessions_user ON active_sessions (user_id);
```

**Backend:**
- On login: INSERT row with JTI.
- On every authenticated request: UPDATE last_seen_at.
- On logout: DELETE row + add to blocklist.
- Logout-everywhere: SELECT every JTI for user, batch-revoke.

**Endpoint:**
```
GET    /auth/sessions       — list my active sessions
DELETE /auth/sessions/{jti} — revoke one
DELETE /auth/sessions/all   — logout everywhere
```

**Severity:** Medium. **Complexity:** S (1 week). **Priority:** P2.

---

## D-024 · Sequence Editor Enforces Unsubscribe Placement

### Problem Summary
F-024 validates the token exists. It does not validate the token is in a *visible* part of the email (footer). A clever sequence author could put `{{unsubscribe_link}}` inside an HTML comment.

### Exact Fix Recommendation

**Backend Fix:**

```python
# app/services/sequence_unsubscribe.py — extend
import re
_TOKEN_IN_COMMENT_RE = re.compile(r"<!--[^>]*\{\{\s*unsubscribe_link\s*\}\}[^>]*-->", re.IGNORECASE | re.DOTALL)

def validate_sequence_body(body: str) -> None:
    if _TOKEN_IN_COMMENT_RE.search(body):
        raise SequenceValidationError("unsubscribe_in_comment_not_allowed")
    # ... existing checks
```

**Test:** Token inside `<!-- ... -->` → 422.

**Severity:** Low. **Complexity:** S (1 day). **Priority:** P4.

---

## D-025 · Multi-Pipeline Support

### Problem Summary
`OpportunityStage` enum is hardcoded. CLAUDE.md mentions `/settings/pipelines` with `FEATURE_MULTI_PIPELINE` flag but the data model doesn't support custom pipelines.

### Exact Fix Recommendation

**DB:**
```sql
CREATE TABLE pipelines (
  id BIGSERIAL PRIMARY KEY,
  tenant_id INTEGER NOT NULL,
  name VARCHAR(100) NOT NULL,
  is_default BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE pipeline_stages (
  id BIGSERIAL PRIMARY KEY,
  pipeline_id BIGINT REFERENCES pipelines(id),
  order_index INTEGER NOT NULL,
  name VARCHAR(60) NOT NULL,
  default_probability NUMERIC(4,3),
  is_won_terminal BOOLEAN NOT NULL DEFAULT false,
  is_lost_terminal BOOLEAN NOT NULL DEFAULT false
);
ALTER TABLE opportunities ADD COLUMN pipeline_id BIGINT REFERENCES pipelines(id);
```

**Migration plan:**
1. Create default pipeline per tenant from existing `OpportunityStage` enum.
2. Backfill `opportunities.pipeline_id` from default.
3. Forecast service aggregates per-pipeline; UI shows pipeline selector.

**Severity:** Medium. **Complexity:** L (4-5 weeks). **Priority:** P4.

---

## D-026 · Plan Model + Subscription Mapping

### Problem Summary
Subscriptions feature references "Plan seç (Standard/Premium/Enterprise [VARSAYIM])" — no actual plan model exists. Subscription state machine relies on undefined contract.

### Exact Fix Recommendation

**DB:**
```sql
CREATE TABLE subscription_plans (
  id BIGSERIAL PRIMARY KEY,
  tenant_id INTEGER NOT NULL,
  code VARCHAR(40) NOT NULL,
  display_name VARCHAR(120) NOT NULL,
  billing_cycle VARCHAR(20) NOT NULL,        -- monthly | annually
  base_price NUMERIC(18,2) NOT NULL,
  currency VARCHAR(3) NOT NULL,
  feature_flags JSONB NOT NULL DEFAULT '{}',  -- per-plan feature toggles
  active BOOLEAN NOT NULL DEFAULT true,
  UNIQUE (tenant_id, code)
);

ALTER TABLE subscriptions
  ADD COLUMN plan_id BIGINT REFERENCES subscription_plans(id);
```

**Cancellation policy enum (Subscription model):**
```python
class CancellationPolicy(str, Enum):
    immediate_refund = "immediate_refund"
    end_of_period = "end_of_period"
    no_refund = "no_refund"
```

Sub model exposes `cancel(policy: CancellationPolicy)` method enforcing the path.

**Severity:** High. **Complexity:** L (3-4 weeks). **Priority:** P3.

---

## D-027 · TSA-Signed Timestamp on Contracts

### Problem Summary
TC-CONTRACT-007 + audit — contract signing currently captures `signed_at` from the server clock. Not legally admissible in many jurisdictions without RFC 3161 TSA timestamp.

### Exact Fix Recommendation

**Backend:**

```python
# app/services/tsa_client.py — NEW
def tsa_sign(payload_hash: bytes) -> bytes:
    """Submit hash to a Trusted Time Authority, return signed timestamp.

    Free TSAs (EU eIDAS):
      - http://timestamp.digicert.com  (commercial fallback)
      - http://tsa.cesnet.cz/tss/server (free, qualified for eIDAS)
    """
    import requests
    # Build RFC 3161 request:
    # asn1 TimeStampReq { version, messageImprint(SHA-256, hash), reqPolicy?, nonce, certReq=true }
    ...
```

In `sign_otp.consume_for_signing` after recording, compute SHA-256 of (contract_id, payload_hash, signer_email, signed_at) and submit to TSA. Store returned token in `sign_otp_tokens.tsa_token`.

**DB:**
```sql
ALTER TABLE sign_otp_tokens ADD COLUMN tsa_token BYTEA;
```

**Verification endpoint:**
```
GET /contracts/{id}/verify-signature
  → returns parsed TSA token + signer email + signed_at; checks TSA signature offline.
```

**Severity:** Critical (legal validity for high-value contracts). **Complexity:** M (2-3 weeks incl. TSA vendor). **Priority:** P3.

---

## D-028 · Email-Pipeline Retry on Transient AI Failure

### Problem Summary
TC-EMAIL-014 expects circuit breaker; the current breaker is on the Anthropic client. There's no retry budget on the email-processing pipeline as a whole — a transient breaker-open lands the email in error state forever.

### Exact Fix Recommendation

**Backend Fix:**

Add a "retry until cooldown" pattern to `EmailProcessingService.process_email`:

```python
async def process_email(self, email_id):
    email = await self._get_or_raise(email_id)
    for attempt in range(3):
        try:
            return await self._do_process(email)
        except CircuitBreakerOpenError:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            # Final fallback: regex parse, mark needs_ai_retry.
            email.parse_skipped_reason = "ai_unavailable_pending_retry"
            await self._regex_fallback_only(email)
            return email
```

**Cron:** Hourly sweep of `parse_skipped_reason='ai_unavailable_pending_retry'` retries Claude when breaker is closed.

**Severity:** Medium. **Complexity:** S (1 week). **Priority:** P3.

---

## D-029 · Approval Delegation Expiry Sweep

### Problem Summary
F-018 schema added `approval_rules.delegate_to` and `delegate_until`. No cron to revert delegation when `delegate_until < now()`.

### Exact Fix Recommendation

**Cron:**
```python
async def r19_delegation_expiry_task():
    from sqlalchemy import text
    from app.core.database import async_session
    async with async_session() as db:
        await db.execute(text(
            "UPDATE approval_rules SET delegate_to = NULL, delegate_until = NULL "
            "WHERE delegate_until IS NOT NULL AND delegate_until < now()"
        ))
        await db.commit()
```

Register hourly in scheduler.

**Severity:** Medium. **Complexity:** S (1 day). **Priority:** P3.

---

## D-030 · "Trash" View per Entity + Bulk Restore

### Problem Summary
F-007 endpoint exists for single-entity restore but no UI surface and no bulk operation.

### Exact Fix Recommendation

**Frontend:** New page `/admin/trash` with tabs per entity, multi-select + "Restore" / "Hard delete" actions (latter Operations-only).

**Backend:** Existing `/trash/{entity}` + `/trash/{entity}/{id}/restore` endpoints. Add:
```
POST /trash/{entity}/bulk-restore   body: {ids: [int]}
```

**Test:** Multi-select 10 → restore → all back to active.

**Severity:** Low. **Complexity:** S (1 week). **Priority:** P4.

---

## D-031 · Bulk Import — Leads + Opportunities

### Problem Summary
F-021 covers customers + parts. Leads and opportunities also have onboarding-time bulk-import needs.

### Exact Fix Recommendation

Mirror the customers/parts pattern in `app/services/bulk_import.py`:
- `import_leads(db, csv_text, tenant_id, actor_id)` — natural key: (tenant_id, email_lower)
- `import_opportunities(db, csv_text, tenant_id, actor_id)` — natural key: (tenant_id, external_id) (require external_id column for opps)

**Severity:** Medium. **Complexity:** S (1 week). **Priority:** P3.

---

## D-032 · Outbound Webhooks

### Problem Summary
Inbound integrations are wired (IMAP, Twilio receive, etc.). Outbound webhooks (notifying customer's CRM when a quote is sent, etc.) are absent.

### Exact Fix Recommendation

**DB:**
```sql
CREATE TABLE webhook_endpoints (
  id BIGSERIAL PRIMARY KEY,
  tenant_id INTEGER NOT NULL,
  url VARCHAR(500) NOT NULL,
  secret_hash VARCHAR(128) NOT NULL,
  events VARCHAR(60)[] NOT NULL,    -- ['quote.sent', 'contract.signed', ...]
  active BOOLEAN NOT NULL DEFAULT true
);
CREATE TABLE webhook_deliveries (
  id BIGSERIAL PRIMARY KEY,
  endpoint_id BIGINT NOT NULL REFERENCES webhook_endpoints(id),
  event_type VARCHAR(60) NOT NULL,
  payload JSONB NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_attempt_at TIMESTAMPTZ,
  response_status INTEGER,
  next_retry_at TIMESTAMPTZ
);
```

**Service:** `webhook_dispatcher.send(endpoint, event_type, payload)` signs body with HMAC-SHA256 of endpoint secret, includes `X-Webhook-Timestamp` + `X-Webhook-Signature` headers, retries 6× with exp backoff.

**Severity:** Medium (partner integration enabler). **Complexity:** M (2 weeks). **Priority:** P4.

---

## D-033 · Customer Health Zero-Data Bias Correction

### Problem Summary
TC-HEALTH-001 — new customer with no data scores 0 on each component → at-risk by definition. False positive.

### Exact Fix Recommendation

**Backend Fix:**

```python
# app/services/customer_health_service.py — adjust scoring
def compute_health_score(customer, today):
    score, signal_count = _compute_components(customer, today)
    if signal_count == 0:
        # No data — return 50 (neutral) with confidence=0.
        # UI shows "no data yet" badge instead of "at-risk".
        return HealthScore(value=50, confidence=0.0, components={})
    return HealthScore(value=score, confidence=signal_count/6, ...)
```

**Frontend:** Cockpit At-Risk card excludes customers with `confidence < 0.3`.

**Severity:** Medium. **Complexity:** S (3 days). **Priority:** P3.

---

## D-034 · Forecast Cron at Tenant-Local Time

### Problem Summary
Forecast cron runs at 04:00 UTC = 07:00 IST. By the time a Turkish tenant logs in at 09:00, the forecast is already "today's" — but actually it's based on yesterday's data because the cron ran at 04:00 UTC = 06:00 IST (before Turkey wakes up).

### Exact Fix Recommendation

**Tenant settings:**
```sql
ALTER TABLE tenant_settings ADD COLUMN forecast_cron_hour INTEGER NOT NULL DEFAULT 4;
ALTER TABLE tenant_settings ADD COLUMN forecast_cron_tz VARCHAR(40) NOT NULL DEFAULT 'UTC';
```

**Cron:** Switch from `interval` to a tenant-loop:
```python
async def forecast_cron():
    async with async_session() as db:
        tenants = await db.scalars(select(Tenant))
        for tenant in tenants:
            cfg = await get_tenant_settings(db, tenant.id)
            now_local = datetime.now(ZoneInfo(cfg.forecast_cron_tz))
            if now_local.hour == cfg.forecast_cron_hour and now_local.minute < 15:
                await rebuild_forecast(db, tenant.id)
```

Scheduled at `*/15` minutes (every 15 min). Each tenant's match window triggers once per day.

**Severity:** Low. **Complexity:** S (3 days). **Priority:** P4.

---

## D-035 · Reports Builder Streaming for > 10K Rows

### Problem Summary
TC-REP-004 — 50K row report should stream. Currently `export_csv` buffers all rows in StringIO.

### Exact Fix Recommendation

**Backend:**
```python
from fastapi.responses import StreamingResponse

async def export_csv_stream(template_id, current_user):
    async def generate():
        yield ",".join(columns) + "\n"
        async for row in execute_report_streaming(template_id, current_user):
            yield ",".join(sanitize_csv_row(row)) + "\n"
    return StreamingResponse(generate(), media_type="text/csv", headers={...})
```

`execute_report_streaming` uses SQLAlchemy `stream_results=True`.

**Severity:** Medium. **Complexity:** S (1 week). **Priority:** P3.

---

## D-036 · Audit Log Explorer UI

### Problem Summary
TC-AUDIT-003 — search performance OK, but UX surface (`/audit`) is just a table. Saved filters, exports, and event-type breakdowns are needed for compliance use.

### Exact Fix Recommendation

**Frontend:** New `AuditExplorer.tsx`:
- Sidebar with saved filters (per-user).
- Timeline view of activity.
- Per-user activity heatmap.
- Export filtered set to CSV (with the formula-sanitiser).

**Severity:** Low. **Complexity:** M (2 weeks). **Priority:** P4.

---

## D-037 · E2E Test Harness (Playwright)

### Problem Summary
`MASTER_TEST_COVERAGE.md` defines many "automation type: E2E" tests; no Playwright runner.

### Exact Fix Recommendation

**Setup:**
```
frontend/e2e/
  fixtures/        — test users, seeded DB state
  pages/           — page object models
  tests/
    auth.spec.ts
    customer-create.spec.ts
    quote-flow.spec.ts
    sign-otp.spec.ts
    kvkk-two-person.spec.ts
  playwright.config.ts
```

CI: Run on every PR against staging snapshot. Tier 1 = critical paths only (< 10 min); Tier 2 = full regression nightly.

**Severity:** High. **Complexity:** L (4-5 weeks). **Priority:** P2.

---

## D-038 · Chaos Test Harness

### Problem Summary
Documentation defines chaos drills; no automation.

### Exact Fix Recommendation

**Setup:** `chaos/` directory with scripts:
- `kill-pg-mid-write.sh` — toxiproxy disconnect PG for 5s during a quote-send burst.
- `claude-500-storm.sh` — mock all Anthropic calls to return 500 for 60s.
- `imap-partition.sh` — drop IMAP connection during fetch.

Wrap each in `chaos/run.sh <drill>` so the on-call game-day runs from one command.

**Severity:** Medium. **Complexity:** M (3 weeks). **Priority:** P4.

---

## D-039 · Backup + DR Runbook (RTO ≤ 4h, RPO ≤ 1h)

### Problem Summary
No documented DR plan.

### Exact Fix Recommendation

**Plan:**
- **RPO = 1 hour:** Continuous WAL streaming to S3 (pgBackRest).
- **RTO = 4 hours:** Standby PG instance in second region (read-replica via streaming replication). Promote on disaster.
- **Backups:** Nightly full + hourly incremental, encrypted with KMS, 30-day hot retention + 7-year cold (KVKK).
- **Restore drill:** Quarterly, against a staging environment.

**Doc:** `docs/runbooks/DISASTER_RECOVERY.md` with step-by-step.

**Severity:** Critical. **Complexity:** L (3-4 weeks setup + ongoing). **Priority:** P2.

---

## D-040 · DAST + SAST in CI Gates

### Problem Summary
Code review is human-only. No automated security scanning blocks merge.

### Exact Fix Recommendation

**CI additions:**
1. **Semgrep** (SAST): Run on every PR. Block merge on HIGH+ findings.
2. **Bandit** (Python-specific): Same.
3. **OWASP ZAP baseline** (DAST): Nightly against staging. Block deploy on HIGH+ findings.
4. **TruffleHog / GitGuardian**: Secret scanning on every push.
5. **pip-audit + npm-audit**: Block merge on CVSS ≥ 7.

**GitHub Actions workflow:**
```yaml
- name: Semgrep
  run: semgrep --config=auto --error
- name: Bandit
  run: bandit -r backend/app
- name: pip-audit
  run: pip-audit --strict
- name: ZAP baseline (nightly)
  if: github.event_name == 'schedule'
  uses: zaproxy/action-baseline@v0.10.0
  with: { target: 'https://honeywell-backend.onrender.com' }
```

**Severity:** High. **Complexity:** S (1-2 weeks setup). **Priority:** P1.

---

# Recommended Engineering Roadmap

> Estimates: **S** ≤ 1 dev-week, **M** 2-4, **L** 5-10, **XL** 10+.

## Phase 1 — Immediate Production Blockers (4-6 weeks)

Items that must land before opening pilot to paying customers.

| ID | Finding | Complexity | Risk Reduction | Priority |
|---|---|---|---|---|
| D-014 | Sign-OTP SMTP wire | S | 🔴 Critical | P1 |
| D-016 | KVKK export worker | M | 🔴 Critical | P1 |
| D-015 | KVKK subject notification | S | 🔴 High | P1 |
| D-018 | Field-permission middleware | M | 🔴 Critical | P1 |
| D-006 | Per-account login rate limit | S | 🔴 High | P1 |
| D-007 | JWT rotate on login | S | 🟠 High | P1 |
| D-040 | DAST/SAST in CI | S | 🟠 High | P1 |
| D-010 | Cross-tenant probe detection | S | 🟠 High | P1 |

**Outcome:** Legal compliance + security gate complete. No latent critical-tier risk.

---

## Phase 2 — Security & Data Integrity (6-8 weeks)

| ID | Finding | Complexity | Risk Reduction | Priority |
|---|---|---|---|---|
| D-001 | RLS rollout (5 tables) | L | 🔴 Critical | P2 |
| D-002 | KMS migration | M | 🔴 Critical | P2 |
| D-019 | DLQ for bg jobs | S | 🟠 High | P2 |
| D-023 | Active sessions table | S | 🟠 Medium | P2 |
| D-020 | Soft-delete on 6 entities | M | 🟠 High | P2 |
| D-039 | Backup + DR runbook | L | 🔴 Critical | P2 |
| D-037 | Playwright E2E harness | L | 🟠 High | P2 |
| D-009 | OCC on remaining 7 entities | M | 🟠 Medium | P2 |
| D-013 | Workflow save-time cycle blocker | S | 🟠 High | P2 |
| D-012 | Approval-decision IntegrityError → 409 | S | 🟠 High | P2 |
| D-011 | Quote total server-side | S | 🟡 Medium | P2 |

**Outcome:** Defence-in-depth security; SOC 2 Type II ready; data integrity guaranteed.

---

## Phase 3 — UX & Workflow Stabilization (6-8 weeks)

| ID | Finding | Complexity | Risk Reduction | Priority |
|---|---|---|---|---|
| D-003 | Mobile responsive | M | 🟠 High (UX) | P2 |
| D-004 | AI Tasks model + cron | S | 🟠 High | P2 |
| D-005 | Coaching Hooks model + watermark | S | 🟠 High (legal) | P2 |
| D-022 | Notification preferences | S | 🟡 Medium | P3 |
| D-033 | Health zero-data bias | S | 🟡 Medium | P3 |
| D-028 | Email pipeline retry on AI fail | S | 🟡 Medium | P3 |
| D-029 | Approval delegation expiry sweep | S | 🟡 Medium | P3 |
| D-030 | Trash view + bulk restore | S | 🟡 Low | P4 |
| D-034 | Forecast cron tenant-local | S | 🟡 Low | P4 |
| D-031 | Bulk import leads + opps | S | 🟡 Medium | P3 |
| D-024 | Sequence unsubscribe placement | S | 🟡 Low | P4 |
| D-008 | Per-tenant at_risk_threshold | S | 🟡 Medium | P3 |

**Outcome:** Field reps productive on mobile; AI surfaces watermarked; flows resilient.

---

## Phase 4 — Scalability & Reliability (8-12 weeks)

| ID | Finding | Complexity | Risk Reduction | Priority |
|---|---|---|---|---|
| D-021 | Audit log partitioning | M | 🟡 Medium | P3 |
| D-035 | Reports streaming | S | 🟡 Medium | P3 |
| D-032 | Outbound webhooks | M | 🟡 Medium | P4 |
| D-036 | Audit log explorer UI | M | 🟡 Low | P4 |
| D-038 | Chaos test harness | M | 🟡 Medium | P4 |
| D-019 | DLQ admin endpoints | S | 🟠 (continued from P2) | P3 |

**Outcome:** 100K-customer / 10K-user readiness; observability complete.

---

## Phase 5 — Enterprise Hardening (continuous)

| ID | Finding | Complexity | Risk Reduction | Priority |
|---|---|---|---|---|
| D-017 | Per-tenant DEK rotation script | S | 🟡 Medium | P3 |
| D-025 | Multi-pipeline support | L | 🟡 Medium | P4 |
| D-026 | Plan model + subscription mapping | L | 🟠 High | P3 |
| D-027 | TSA-signed timestamps | M | 🔴 Critical (legal QES) | P3 |

**Outcome:** Customer-controlled pipelines; subscription product GA; eIDAS-grade signatures.

---

## Phase Summary

| Phase | Duration | Effort (dev-weeks) | Outcome |
|---|---|---|---|
| 1 | 4-6 weeks | ~10 | Compliance + critical security; pilot-ready for paying customers |
| 2 | 6-8 weeks | ~30 | SOC 2 Type II ready; DR runbook |
| 3 | 6-8 weeks | ~25 | Mobile + AI surfaces complete |
| 4 | 8-12 weeks | ~25 | 10K-user ready |
| 5 | Continuous | ~30+ | Enterprise GA features |

**Total to full enterprise readiness:** ~12 months of focused engineering (3-4 backend, 1-2 frontend, 1 SRE).

**Phase 1 alone** is one quarter of work and is the **minimum gate before opening to paying customers**.

---

## Cross-Cutting Engineering Standards

These apply to every Phase:

### Lint Rules (enforced in CI)
- Any endpoint returning a maskable entity type must use `@apply_request_perms_to_response`.
- Any model added to `app/models/` must register with `Base.metadata` (i.e. imported in `__init__.py`).
- Any model touching PII must include the F-007 tombstone columns.
- Any new ciphertext column must register in `_ENCRYPTED_COLUMNS` for D-017 rotation.
- Any new endpoint must call `assert_same_tenant` or `load_with_tenant_check` for entity ID lookups.

### Audit Logging Discipline
Every privileged write (anything that mutates a customer-visible entity) must include exactly one `audit_log.append(...)` call with: `actor_id, tenant_id, action, entity_type, entity_id, before_state, after_state, request_id`. Lint enforces.

### Observability Discipline
Every new background job registers with `_tracked()` (existing pattern). Every async function that hits an external service (Anthropic, SMTP, KMS, S3) instruments `time.monotonic()` + Prometheus histogram. Lint enforces.

### Test Pyramid Per PR
- Unit tests: cover every new pure function.
- Integration test: cover the happy path of every new endpoint.
- Permission test: cover every new authorisation rule.
- Cross-tenant test: any new endpoint that takes an entity ID.
- Audit assertion: any new privileged write.

### Migration Discipline
Every schema-altering migration:
- Idempotent (`IF NOT EXISTS` / `IF EXISTS`).
- Reversible (working `downgrade()`).
- Tested against a copy of prod data before deploy.
- Migrations touching large tables (> 1M rows) use the "add nullable → backfill → enforce NOT NULL" pattern to avoid table-rewrite locks.

---

**End of hardening design v2.** Forty findings, every one with a buildable spec. Adoption is straightforward: pick a phase, work through its IDs in priority order, update the status table in `2026-05-26-enterprise-hardening-plan.md`, retire the corresponding `TC-*` cases from "pending" to "covered" as you go.
