# V3 Pilot Rollout Playbook

> Audience: platform owner + pilot-customer CS lead.
> Assumption: v3 code is deployed to production; all flags start OFF
> except `FEATURE_AI_TRUST_LAYER` (on-by-default, no-op when no AI calls).

## 0. Prerequisites (do once per environment)

- [ ] `alembic upgrade head` ran successfully on the target DB
  (Render runs this on deploy; verify via `alembic current`).
- [ ] `ENCRYPTION_KEY` is set in prod. Rotation secret
  (`ENCRYPTION_KEY_PREVIOUS`) is documented for later rotations.
- [ ] `DATABASE_URL` points at Postgres, not SQLite.
- [ ] Grafana + Sentry wired (or equivalent log sink).
- [ ] `/api/v1/admin/feature-flags` reachable by a sales_manager account.
- [ ] Rollback switch tested: PATCH `FEATURE_X` → off + DELETE `/admin/feature-flags`.

## 1. Rollout sequence

Run flags in this order — each depends on the previous one being stable
for at least 48 hours:

1. `FEATURE_AI_TRUST_LAYER` (already on; verify logs show `ai_trust.scrubbed`).
2. `FEATURE_FIELD_AUDIT` (silent — adds row inserts only).
3. `FEATURE_ERP_CONNECTOR` + one Paraşüt connection per pilot.
4. `FEATURE_WHATSAPP` (requires Meta Cloud creds).
5. `FEATURE_OPERATIONS` (only for customers using warehouses).
6. `FEATURE_MARKETPLACE` (for ISV partners).
7. `FEATURE_AGENTIC_SDR` (requires ANTHROPIC_API_KEY; gate behind AI QA).

## 2. Per-flag playbook

### 2.1 `FEATURE_ERP_CONNECTOR`

**What it unlocks**: Logo / Paraşüt / SAP B1 sync, invoice push, stock signals.

**Preflight**
- [ ] Partner has shared endpoint + service credentials.
- [ ] Test tenant created with Paraşüt sandbox credentials.
- [ ] `docs/integrations/LOGO-COOKBOOK.md` walked with partner for method names.

**Rollout**
1. Enable the flag via the admin page for the pilot tenant.
2. `POST /erp/connections` → `POST /erp/connections/{id}/test` (expect
   `ok=true`).
3. Full sync: `POST /erp/connections/{id}/sync { "entity": "all", "mode": "full" }`.
4. Watch `erp_sync_jobs` rows — success within 5 minutes for ≤10k records.
5. Verify `customers` / `spare_parts` got populated; mapping rows in
   `erp_entity_mappings`.
6. Turn on cron: set `sync_cron = "0 */2 * * *"`.

**Success metrics (first week)**
- Sync success rate ≥ 99%.
- Conflict ratio < 1% of changed records.
- No auth rejections.

**Rollback**
- Override `FEATURE_ERP_CONNECTOR=false` via admin UI.
- Optional: `DELETE /erp/connections/{id}` to remove the config.
- Domain rows are kept; they simply stop receiving updates.

---

### 2.2 `FEATURE_AI_TRUST_LAYER`

**What it unlocks**: PII masking in every outbound Claude call; audit
record kept with SHA-only metadata.

**Preflight**
- [ ] `ANTHROPIC_API_KEY` set in prod.
- [ ] `tests/test_ai_trust.py` green.

**Rollout**
- Default on. No action needed — inspect a handful of parse logs to
  confirm `ai_trust.scrubbed hits=...` lines appear.

**Rollback**
- Set `FEATURE_AI_TRUST_LAYER=false` (lowers the safety rail; only do this
  if a false-positive is blocking a real workflow).

---

### 2.3 `FEATURE_FIELD_AUDIT`

**What it unlocks**: Field-level change history for every scalar ORM
attribute, with 10-year retention.

**Preflight**
- [ ] Migration `20260424_field_audit_log` applied.
- [ ] `FIELD_AUDIT_RETENTION_DAYS` matches the customer's regulatory
      requirement (default 3650).

**Rollout**
1. Enable flag.
2. Perform a sample Customer update; verify a row landed in
   `field_audit_logs` via the evidence endpoint.
3. Confirm manager-only access: `GET /field-audit/` returns 403 for a
   sales_rep token.

**Success metrics**
- Row-write overhead < 5ms p95 added to update-path requests.
- Storage growth tracked weekly.

**Rollback**
- Set flag off. No schema change needed; history stops growing but
  existing rows remain for compliance.

---

### 2.4 `FEATURE_WHATSAPP`

**Preflight**
- [ ] Meta Cloud API phone number approved.
- [ ] Message templates submitted + approved.
- [ ] `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`,
      `WHATSAPP_VERIFY_TOKEN` set.
- [ ] Public webhook URL (https) reachable for the Meta handshake.

**Rollout**
1. Point Meta webhook at `GET /api/v1/integrations/whatsapp/webhook`
   — expect 200 echoing the challenge.
2. Enable flag.
3. Send one template message via `POST /integrations/whatsapp/send/template`
   to a test phone. Expect a row in `whatsapp_messages` with status=sent.
4. Reply from the handset; confirm inbound row captured.

**Success metrics**
- Inbound → stored latency < 10s p95.
- Outbound send rejection rate < 1%.

**Rollback**
- Flag off. Meta webhook stays configured so re-enabling does not require
  a second handshake.

---

### 2.5 `FEATURE_OPERATIONS`

**Preflight**
- [ ] At least one `warehouse` row created (default seeded by
      `ensure_default_warehouse`).
- [ ] Stock sync from ERP landed initial qty.

**Rollout**
1. Enable flag.
2. Create a test movement via `POST /operations/movements`.
3. Verify `stock_levels.qty` updated and `SparePart.current_stock_qty`
   refreshed.
4. Test BOM: create a parent + 2 children via `POST /operations/bom`, then
   `GET /operations/bom/explode/{parent_id}`.

**Success metrics**
- No negative-stock errors from happy-path workflows.
- Reservation → release cycle balanced (reserved_qty returns to 0).

**Rollback**
- Flag off. Rows remain; on re-enable the system resumes from the last
  state.

---

### 2.6 `FEATURE_MARKETPLACE`

**Preflight**
- [ ] Plugin catalogue row inserted (manually via
      `POST /marketplace/plugins`).
- [ ] HTTPS endpoint available on the ISV side.

**Rollout**
1. Enable flag.
2. ISV installs the plugin via `POST /marketplace/installations`
   (returns one-time `api_token`).
3. ISV subscribes to events (`POST /marketplace/subscriptions`).
4. Trigger a canonical event (stage change) and watch the ISV endpoint
   receive the `X-Marketplace-Signature` payload.

**Success metrics**
- Webhook 2xx rate ≥ 98%.
- Median delivery latency < 3s.

**Rollback**
- Flag off freezes outbound delivery but keeps configuration rows.
- `DELETE /marketplace/installations/{id}` for a destructive rollback.

---

### 2.7 `FEATURE_AGENTIC_SDR`

**Preflight**
- [ ] `ANTHROPIC_API_KEY` set.
- [ ] `FEATURE_AI_TRUST_LAYER=on` (mandatory; agent context has PII).
- [ ] `FEATURE_WORKFLOW_RULES=on` so the agent's outputs land next to the
      existing rule engine.
- [ ] AI QA walkthrough completed (sample 10 opportunities; manager
      reviews the recommended tools).

**Rollout**
1. Enable flag.
2. Manually run `POST /agentic/sdr/run` against a test opportunity;
   inspect the returned tool + rationale.
3. Let the event-bus auto-trigger handle one real high-severity signal;
   verify a Task row shows up with `source="ai"`.

**Success metrics**
- Agent-produced Tasks accepted (status=done) rate ≥ 40% in first week.
- No direct emails sent (always drafts).
- Escalation noise ≤ 2 per manager per day.

**Rollback**
- Flag off. Tasks already created remain; scheduler events stop
  triggering the agent.

---

## 3. Incident response

Single source of truth: admin UI → "Tüm override temizle" button (DELETE
`/admin/feature-flags`). This reverts every flag to its env value,
providing a 5-second full-rollback.

For deeper incidents:

- ERP sync failures > 10/hour → disable `FEATURE_ERP_CONNECTOR`; DB rows
  stay intact.
- AI cost blowout → disable `FEATURE_AI_TRUST_LAYER`? No — disable the
  consuming flag (`FEATURE_AGENTIC_SDR`, `FEATURE_AI_SUMMARIES`, etc).
  Trust layer itself has negligible cost.
- Marketplace plugin misbehaving → disable that plugin's installation via
  DELETE; no global kill needed.

## 4. Observability checklist

Wire these to Grafana before rolling out the matching flag:

- ERP: `erp.sync.failed` count, conflict count, p95 sync duration.
- AI Trust: `ai_trust.scrubbed` hits per model.
- Agentic SDR: agent tool distribution (draft vs task vs escalate vs
  no-action).
- Marketplace: webhook delivery non-2xx count per plugin.
- Operations: reservation / movement error counts.
