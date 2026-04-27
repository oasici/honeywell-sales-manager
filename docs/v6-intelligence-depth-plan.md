# V6 — Intelligence Depth & Real-Time

**Status**: 2026-04-27 — sprint plan
**Predecessor**: `docs/v5-intelligence-plan.md`
**Why now**: V5 closed ~82% of the original framework spec. The
remaining ~18% is concentrated in *algorithmic depth* (sequence
tokens, trajectory features, counterfactual reasoning) and
*real-time event hooks*. V6 closes those gaps.

---

## Sprint A — Core depth (sequence tokens + OFD columns)

**Goal**: lift Sales DNA pattern quality and buyer-state precision by
giving downstream miners higher-signal inputs.

### Migration `20260427_v6_core_depth.py`
Add to `opportunity_features_daily`:
- `quote_revision_count_30d INTEGER NOT NULL DEFAULT 0`
- `stage_velocity_days DOUBLE PRECISION NULL`
- `decision_maker_count INTEGER NOT NULL DEFAULT 0`

### New module `app/services/sequence_tokenizer.py`
Reduce a chronological event list to high-level behavioural tokens:
- `buyer_replied_within_48h`
- `meeting_before_quote`
- `decision_maker_added_before_discount`
- `3plus_stakeholders_engaged`
- `discount_under_15`
- `followup_within_24h_after_quote`
- `quote_revised_after_objection`
- `stage_progressed_within_7d`

### Wiring
- `feature_store_builder` populates the 3 new OFD columns.
- `dna_pattern_miner._signature` becomes `tokenize_sequence(events, opp)` —
  pattern lift improves because tokens encode causality, not just type.

### Tests
- 8 token unit tests (one per rule).
- DNA miner regression: same input → richer signature.

---

## Sprint B — Buyer state expansion + real-time recompute hooks

**Goal**: surface 7 buyer states (plan parity) and update them on the
spot when new events land instead of waiting for nightly batch.

### Migration `20260427_v6_buyer_state_expansion.py`
- No schema change; `buyer_state` is freeform `String(30)`. Migration
  logs the new enum so downstream readers can switch.

### Buyer state enum (5 → 7)
- `exploring`, `evaluating`, `negotiating`, `stalling`, `closed` (kept)
- **new**: `aligning`, `procurement`, `ready_to_buy`

Promotion rules added to `_buyer_state_and_drivers`:
- `aligning`: stakeholder count grew + meetings logged + no objections
- `procurement`: legal/procurement/security signals (`OBJECTION_TYPES.security`/`procurement`)
- `ready_to_buy`: contract_sent or accepted_at present + buyer_reply_count_14d ≥ 2

### New module `app/services/event_recompute_hooks.py`
- `recompute_after_activity(db, opportunity_id, *, kinds=("momentum","buyer","gap"))`
- Called from `activity_logger.log_activity` (best-effort; flag-gated by
  `FEATURE_V6_REALTIME`).

### Tests
- 7 buyer-state classification tests.
- Hook fires on `log_activity`, opportunity OFD upserted in same txn.

---

## Sprint C — Deal replay deltas + counterfactual hints

**Goal**: turn snapshot history into a readable narrative — what
happened between snapshots, and what *should have* happened.

### Migration `20260427_v6_replay_deltas.py`
New table `deal_replay_deltas`:
- `id`, `opportunity_id`, `from_ts`, `to_ts`, `change_type`,
  `change_summary TEXT`, `impact_score FLOAT`, `drivers_json TEXT`,
  `counterfactual_hint TEXT NULL`, `created_at`

### New service `app/services/replay_delta_service.py`
- `compute_deltas(db, opportunity_id)` walks
  `deal_replay_snapshots` pairwise and emits delta rows.
- `_counterfactual_hint(prev, curr, events_between)` returns one of:
  - `competitive_response_missing` (competitor mention + no rep action ≥ 5d)
  - `post_quote_followup_gap` (quote_sent + no followup ≥ 72h)
  - `procurement_unengaged` (security/legal signal + procurement role missing)
  - `stakeholder_thinning` (stakeholder count dropped)
  - `discount_spiral` (discount_pct rising across snapshots)

### Endpoint
`GET /api/v1/v6/opportunities/{id}/replay-deltas` (RBAC: opp owner / mgr).

### Tests
- 5 counterfactual hint tests + delta walk integration test.

---

## Sprint D — DNA → Playbook auto-promote

**Goal**: take mined DNA patterns above a confidence threshold and
auto-create playbook drafts; track adherence + measure lift.

### New service `app/services/dna_playbook_promoter.py`
- `promote_top_patterns(db, *, min_lift=1.5, min_support=10)` — for each
  qualifying `DnaPattern`, upsert a `Playbook` + ordered
  `PlaybookStep` rows derived from the sequence tokens.
- `compute_adherence(db, playbook_id, *, window_days=30)` writes a
  `PlaybookPerformance` row.

### Algorithm
- Adherence: `completed_eligible_steps / eligible_steps`
- Lift: `winrate(followers) − winrate(non_followers)`
- Step trigger derived from token: e.g. `followup_within_24h_after_quote`
  → step trigger = `quote_sent`, action = `followup_call`, expected
  window = 24h.

### Endpoint
`POST /api/v1/v6/playbooks/promote-from-dna` (manager only)
`GET  /api/v1/v6/playbooks/{id}/adherence`

### Tests
- Token → playbook step mapping (4 cases).
- Promotion idempotency.

---

## Sprint E — Similarity trajectory features

**Goal**: extend the structured embedding so two deals match when
their *trajectory* is similar, not just their snapshot.

### Embedding upgrade (8 dim → 12 dim, version bump)
New dimensions:
- `stage_velocity_norm` (deals that progress fast cluster together)
- `momentum_trend_norm` (mean Δmomentum over last 14d)
- `buyer_state_changes_norm` (number of distinct buyer_states / 5)
- `objection_density_norm` (objections_30d / 5)

### Wiring
- Bump `EMBEDDING_VERSION` to `v6-trajectory-1`.
- Builder reads from new OFD columns (Sprint A) + `BuyerStateHistory`
  + `Objection`.
- Re-embedding triggered by V5 nightly automatically (since
  `upsert_embedding` is idempotent).

### Tests
- Vector dim assertion (12).
- Trajectory features bounded [0,1].

---

## Sprint F — Federated benchmark stub

**Goal**: lay the table + suppression rules so when we go multi-tenant
we don't have to retrofit privacy.

### Migration `20260427_v6_federated_stub.py`
New table `federated_benchmarks`:
- `id`, `benchmark_key`, `snapshot_date`, `metric_name`, `metric_value`,
  `sample_bucket`, `privacy_level`, `tenant_count INTEGER NOT NULL`,
  `suppressed BOOLEAN NOT NULL DEFAULT FALSE`, `created_at`

### New service `app/services/federated_benchmark_service.py`
- `publish_benchmark(...)` enforces `MIN_SAMPLE_SIZE` (default 10) and
  `MIN_TENANT_COUNT` (default 3); below threshold rows are written
  with `suppressed=TRUE` so the dashboard can show "n/a — sample too
  small" instead of leaking.

### Tests
- Suppression at threshold.
- Pass-through above threshold.

---

## Validation gate

- pytest backend (≥ 613 + 50 new ≈ 663)
- frontend tsc + vitest + production build
- All migrations idempotent (`IF NOT EXISTS` only)
- Feature flag `FEATURE_V6_REALTIME` gates the hook side-effects
- No breaking changes to V5 envelope shape

---

## Out of scope (still)

- True ML-learned token weights (Sprint A keeps rule-based; ML path is V7).
- Full Bayesian uplift modeling for playbooks.
- LLM-hybrid objection detection (V5 keyword detector still authoritative).
- Tenant-segregated database (federated stub assumes shared schema).

These remain on the roadmap but are not blocking the depth gap.
