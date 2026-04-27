# V7 — Intelligence Final Stretch

**Status**: 2026-04-27 — sprint plan
**Predecessor**: `docs/v6-intelligence-depth-plan.md`
**Why now**: V5 + V6 closed ~95% of the framework. The remaining ~5%
is concentrated in *learned* signals (LLM-hybrid detection, Bayesian
smoothing) and *cross-tenant* analytics. V7 closes those.

---

## Sprint G — LLM-hybrid objection detection

**Problem**: keyword-only detection misses paraphrased objections in
emails / call transcripts ("we're concerned about the timing of the
rollout vs. our internal capacity" → no keyword match → false negative).

**Solution**: hybrid pipeline.

1. Keyword pass first (fast, deterministic, free).
2. If keyword pass returns < N objections OR text length > threshold,
   fall back to Claude with a structured prompt asking for the same
   `OBJECTION_TYPES` taxonomy.
3. Result is the union, with `source` field tracking which path
   detected each row.

**New module**: `app/services/objection_llm_detector.py`
- `detect_with_llm(text)` — calls Claude, parses with `llm_json`
  parser, validates against the V5 type taxonomy, returns
  `list[DetectedObjection]`.
- Circuit-breaker aware (reuses `claude_messages_create`).

**Wiring**: `objection_intelligence_service.detect_and_record_hybrid`
calls keyword first, augments with LLM when triggered.

**Flag**: `FEATURE_V7_LLM_OBJECTION` (default off; Claude cost gate).

---

## Sprint H — Bayesian-smoothed uplift on DNA

**Problem**: V5/V6 lift = `local_winrate / baseline`. With a 4-deal
support sample, one extra win swings lift wildly. Small-sample
patterns get over-promoted to playbook drafts.

**Solution**: Beta-prior smoothing.

```
α₀ = baseline_winrate × prior_strength
β₀ = (1 − baseline_winrate) × prior_strength
smoothed_winrate = (won_count + α₀) / (support_count + α₀ + β₀)
smoothed_lift   = smoothed_winrate / baseline_winrate
uplift_score    = smoothed_winrate − baseline_winrate     (additive)
posterior_ci_low / ci_high — 95% CI from Beta posterior
```

`prior_strength` defaults to 10 (≈ "we'd need 10 deals before
trusting the data over the prior"). Patterns whose CI lower bound
sits below baseline get `is_promotable = false`.

**Migration `20260427_v7_dna_uplift.py`**
Adds to `dna_patterns`:
- `smoothed_win_rate DOUBLE PRECISION`
- `uplift_score DOUBLE PRECISION`
- `ci_low DOUBLE PRECISION`
- `ci_high DOUBLE PRECISION`
- `is_promotable BOOLEAN NOT NULL DEFAULT FALSE`

**Wiring**: `dna_pattern_miner.mine_patterns` populates the new
columns. `dna_playbook_promoter.promote_top_patterns` filters on
`is_promotable AND uplift_score > 0` instead of raw lift.

---

## Sprint I — Sequence-aware similarity blend

**Problem**: V6 cosine over 12-dim structured vector treats two deals
as identical when their numeric stats line up — even if their event
sequences are completely different ("meeting → quote → close" vs
"quote → ghost → quote → close" both score the same).

**Solution**: LCS-ratio over the V6 token sequence + blend with
cosine.

```
seq_score = LCS(tokens_a, tokens_b) / max(len(a), len(b))
final     = 0.7 × cosine + 0.3 × seq_score
```

**Migration**: none (we already store tokens implicitly via DNA
miner; sequence component is computed at refresh time).

**Wiring**: `deal_similarity_service.refresh_similarity_links`
computes both, writes blended `similarity_score`, and stores the
breakdown in `similarity_reason_json`.

---

## Sprint J — Tenant boundary (analytics-side)

**Scope decision**: full multi-tenant DB (tenant_id on every CRM
table) is a multi-week migration. V7 lays the *analytics* boundary so
network/DNA/federated outputs can already be tenant-segregated when
the CRM half catches up.

**Migration `20260427_v7_tenant_boundary.py`**
- New table `tenants` (id, name, region, plan_tier, created_at).
- Adds `tenant_id INTEGER NULL` to:
  - `network_segments`
  - `segment_benchmarks_daily`
  - `dna_patterns`
  - `dna_recommendations`
  - `network_anomalies`
  - `network_patterns`
  - `objection_patterns`
  - `federated_benchmarks` (already has `tenant_count`; tenant_id is
    the *source* tenant for the row that *contributed*, NULL after
    aggregation)

All NULL by default — single-tenant deployments keep working
unchanged. Multi-tenant deployments populate via the
`tenant_context_service`.

**New module**: `app/services/tenant_context.py`
- `current_tenant_id()` resolved from request context (FastAPI
  dependency) — returns `None` in single-tenant.
- `scoped(query, tenant_id)` helper that adds the WHERE filter when
  tenant_id is set, no-op when None.
- `Tenant` SQLAlchemy model.

**Federated service update**: `publish_benchmark` requires
`source_tenant_ids: list[int]` so `tenant_count` is always derived
honestly from the input.

---

## Validation gate

- pytest backend (≥ 636 + ~30 new V7 tests ≈ 666)
- frontend tsc + vitest + production build
- All migrations idempotent
- Feature flag `FEATURE_V7_LLM_OBJECTION` gates Claude cost
- No breaking changes — every new column is NULL/0/false default

---

## After V7

Framework coverage ≈ 99%. Remaining 1% is truly out-of-scope for
this product cycle:

- **Causal uplift modeling** for playbook A/B (needs control groups
  large enough that we don't have).
- **Sequence-aware *learned* embeddings** (transformer over tokens) —
  V7 ships LCS-blend, transformer is V8 if ever needed.
- **True multi-tenant CRM tables** — V7 lays the analytics boundary;
  CRM half (opportunities, customers, users tenant_id) is its own
  migration project.
