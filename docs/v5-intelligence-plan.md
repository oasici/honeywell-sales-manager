# V5 — Intelligence Platform Build Plan

Status: **In progress** (started 2026-04-27)
Target: Close the gap between the V5 intelligence framework
(Operational + Learning + Network) and the current production codebase.
Today's match: **~50%**. After this plan: **~85%**.

This document is the source of truth for what we're shipping. Each
section maps to one module in the V5 framework, with concrete
schema/service/endpoint/cron deliverables.

---

## Build order (8 alembic migrations + 5 services + endpoints + tests)

### 1 · Foundation features (`20260427_v5_foundation`)

Tables: `account_features_daily`, `rep_features_daily`, `contacts`.

The two daily-snapshot tables fill the gap left by `OpportunityFeaturesDaily`
— we have per-deal features but no per-account or per-rep equivalents.
The new `contacts` table separates buyer-side individuals from `customers`
(which today conflates company + person). Existing customer rows stay
as the company anchor; contacts hang off them.

- `account_features_daily` (PK: account_id + snapshot_date)
  - open_opportunity_count, total_open_pipeline, avg_deal_health,
    avg_momentum, stakeholder_coverage_avg, buyer_engagement_score,
    objection_density_30d, last_touch_days, expansion_signal_score
- `rep_features_daily` (PK: rep_id + snapshot_date)
  - avg_followup_hours, stakeholder_coverage_rate, objection_recovery_rate,
    sequence_adherence_rate, stage_slippage_rate, win_rate_adj,
    discount_dependence
- `contacts`
  - id, account_id (= customer_id), name, title, department,
    seniority_score (0..100), is_decision_maker, linkedin_url

Builders run in `v4_learning_nightly` after `OpportunityFeaturesDaily`.

### 2 · Objection Intelligence (`20260427_v5_objection_intel`)

Tables: `objections`, `objection_resolution_actions`, `objection_patterns`.

- `objections` — id, opportunity_id, event_id, objection_type
  (price/timing/security/integration/authority/priority/procurement/
  competition), severity (low/med/high), resolved_flag, resolved_at, ttr_hours
- `objection_resolution_actions` — id, objection_id, action_type
  (roi_note/revised_quote/payment_term/stakeholder_add/technical_call),
  action_ts, payload_json
- `objection_patterns` — id, segment_key, objection_type,
  recommended_resolution_json, success_rate, sample_size

Service: `objection_intelligence_service.py`
- `detect_objections(event_text, opportunity_id)` — rule + keyword MVP
  (LLM upgrade is a follow-up; current `conversation_insights_service`
  already has detection logic we lift here)
- `mine_resolution_patterns(segment_key)` — group by objection_type,
  compute success_rate from won-vs-lost, materialize `objection_patterns`
- `suggest_resolution(objection_id)` — return top action_type for
  that segment+type pair

Endpoints (admin/manager scope):
- `GET /objections?opportunity_id=...`
- `POST /objections/{id}/resolve` (records resolution_action)
- `GET /objections/patterns?segment_key=...`

### 3 · Timing Engine (`20260427_v5_timing_engine`)

Table: `recommended_action_windows`.

- id, opportunity_id, action_type
  (followup_after_quote/respond_to_objection/meeting_summary/etc),
  window_start, window_end, recommended_at, expected_uplift,
  reason_codes_json, status (pending/done/expired)

Service: `timing_engine_service.py`
- `compute_ideal_gap(action_type, segment_key)` — median gap
  observed in won deals over the last 90d, persisted in
  `segment_benchmarks_daily` extension
- `urgency(opp_id, action_type)` —
  `α(actual_gap − ideal_gap) + β(stalling_risk) + γ(momentum_drop)`
- `materialize_windows(opp_id)` — emit ranked windows

Endpoints:
- `GET /timing/windows?opportunity_id=...`
- `POST /timing/windows/{id}/dismiss`

Cron: `nightly` after `OpportunityFeaturesDaily`.

### 4 · Sales DNA segment-level mining (`20260427_v5_dna_patterns`)

Tables: `dna_patterns`, `dna_recommendations`.

- `dna_patterns` — id, segment_key, pattern_name, pattern_type
  (winning_sequence/loss_sequence/timing_pattern), sequence_template_json,
  support_count, win_rate, baseline_win_rate, lift_vs_baseline,
  confidence_score, last_trained_at
- `dna_recommendations` — id, segment_key, stage_scope,
  recommendation_json, source_pattern_id, created_at

Service: `sales_dna_pattern_miner.py`
- Tokenize won/lost deal sequences from `v4_sales_events_shadow`
- Frequent pattern mining (Apriori-lite — 2/3-grams over normalized
  tokens like `buyer_replied_within_48h`, `meeting_before_quote`,
  `discount_under_15`)
- Lift scoring + confidence floor → publish `dna_patterns`
- Materialize recommendations from top-N patterns per segment

Endpoints:
- `GET /sales-dna/patterns?segment_key=...`
- `GET /sales-dna/recommendations?opportunity_id=...` (resolves
  segment_key from opp metadata, returns matching patterns)

Cron: `weekly` (heavy compute).

### 5 · Network expansion (`20260427_v5_network_expansion`)

Tables: `network_patterns`, `network_anomalies`.

- `network_patterns` — id, segment_key, pattern_type, pattern_json,
  performance_metric, sample_size, confidence_score
- `network_anomalies` — id, segment_key, detected_at, metric_name,
  expected_value, actual_value, severity, explanation_json

New: `BenchmarkGapService` — deal-level gap scoring against
`segment_benchmarks_daily`:
- `benchmark_gap(opp_id) → Σ wᵢ · (actualᵢ − bmᵢ) / bmᵢ`
- Metrics: stakeholder_count, follow-up speed, objection recovery
  speed, meeting density, discount %.

`network_anomalies` z-score detector runs nightly:
- `z = (actual − rolling_mean_28d) / rolling_std_28d`
- Trigger when `|z| ≥ 2`, severity by magnitude.

Endpoints:
- `GET /network/benchmark-gap?opportunity_id=...`
- `GET /network/anomalies?segment_key=...&since=...`

### 6 · Playbook expansion (`20260427_v5_playbook_expansion`)

Tables: `playbook_steps`, `playbook_adherence`, `playbook_performance`.

- Existing `Playbook.steps_json` blob backfills into structured
  `playbook_steps` rows (one per step). New writes use both for
  backwards compat.
- `playbook_adherence` — opportunity_id, playbook_id, step_id,
  eligible_at, completed_at, status (pending/done/skipped)
- `playbook_performance` — playbook_id, period_start, period_end,
  usage_count, completion_rate, won_rate, lift_vs_control

Service hooks already exist in `coaching_service._playbook_adherence`
(in-memory). We persist them, plus add lift_vs_control rollup.

Endpoints:
- `GET /playbooks/{id}/adherence?opportunity_id=...`
- `GET /playbooks/{id}/performance?period=30d`

Cron: `daily` rollup.

### 7 · Deal similarity (`20260427_v5_similarity`)

Tables: `opportunity_embeddings`, `deal_similarity_links`.

- `opportunity_embeddings` — opportunity_id, embedding_vector
  (Vector(384), via existing pgvector / Qdrant pipeline),
  version, generated_at
- `deal_similarity_links` — opportunity_id, similar_opportunity_id,
  similarity_score, similarity_reason_json, created_at

Service: `deal_similarity_service.py`
- Build feature vector: stage path, amount band, industry, product
  family, stakeholder map shape, objection histogram, buyer state
  trajectory, momentum trajectory.
- Cosine similarity (structured features, no LLM yet).
- Top-K linking with score ≥ 0.6.

Endpoint:
- `GET /opportunities/{id}/similar?k=5`

Cron: `daily` (only re-compute opps with material updates).

### 8 · Rep DNA clustering (`20260427_v5_rep_dna`)

Table: `rep_dna_profiles`.

- rep_id, profile_json (cluster_label: fast_closer/relationship_builder/
  discount_dependent/late_escalator), strengths_json, gaps_json,
  generated_at

Service: `rep_dna_profiler.py`
- Pull `rep_features_daily` over last 90d.
- K-means lite (4 fixed clusters from prototypes; assign nearest).
- Strengths = top 2 features above segment median; gaps = bottom 2.

Endpoint:
- `GET /rep/{rep_id}/dna`

Cron: `weekly`.

---

## Federated benchmarks (deferred)

Multi-tenant aggregation needs auth + privacy review (k-anonymity floor
via sample_size, suppression of narrow segments). Schema sketch only:
`federated_benchmarks(benchmark_key, snapshot_date, metric_name,
metric_value, sample_bucket, privacy_level)`. Out of scope for V5.

---

## Cron / batch wiring

Existing `v4_learning_nightly` runs at 02:00 UTC. We extend it to:

1. `OpportunityFeaturesDaily` (existing)
2. `account_features_daily` (new)
3. `rep_features_daily` (new)
4. `objection_intelligence_service.refresh_patterns()` (new)
5. `timing_engine_service.materialize_windows_all()` (new)
6. `BenchmarkGapService.score_open_opportunities()` (new)
7. `network_anomaly_detector.scan_segments()` (new)
8. `playbook_performance_rollup` (new)

`weekly` cron (Sundays 03:00 UTC):
1. `sales_dna_pattern_miner.mine_all_segments()`
2. `rep_dna_profiler.regenerate_all()`
3. `deal_similarity_service.refresh_links()` (full sweep — daily does deltas)

---

## Explainability contract

Every new service returns the standard envelope (existing pattern):

```json
{
  "value": "<primary_value>",
  "confidence": 0.0..1.0,
  "drivers": [{"label": "...", "impact": -1.0..1.0}],
  "benchmark_context": {"segment_median_X": ..., "current_X": ...},
  "recommended_actions": ["..."]
}
```

This format is already in use by `decision_gap_service`,
`customer_health_service`. Reuse directly.

---

## Test strategy

- Unit tests per service module (existing pattern: `tests/test_*.py`).
- Integration test per endpoint covering empty / typical / edge cases.
- Migration smoke test (`alembic upgrade head` + `downgrade base`).
- Total new test target: ~60 cases.

Quality gates (must stay green): `pytest`, `tsc`, `npm test`, `npm run build`.

---

## Out of scope (V6)

- LLM-driven pattern naming / semantic deal similarity
- Causal uplift modeling for playbook recommendations
- Sequence-aware deep learning ranker
- Drift detection on segment patterns
- Real federated multi-tenant pipelines
