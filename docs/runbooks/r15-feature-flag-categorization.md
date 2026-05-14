# Round-15 F-015 — Feature flag categorization runbook

## Context

55 backend `FEATURE_*` flags exist in `backend/app/core/config.py`. Only
20 have a corresponding `<FeatureFlagGate flag="...">` wrap in the SPA
router. The other 35 are either:

- **BE-only** — gates an API behaviour, background job, or shadow
  pipeline that has no SPA surface. No FE counterpart needed.
- **FE+BE** — gates a SPA route or panel; SPA needs `<FeatureFlagGate>`.
- **Dead** — neither side uses it meaningfully; can be removed.

This runbook categorizes all 35 BE-only flags so the engineering team
knows which ones need FE work and which can stay.

## Categorization

### BE-only (no SPA surface needed) — 23 flags

These flags gate background pipelines, shadow tables, or internal
APIs that the SPA never reaches. The backend already enforces
404/403 on the gated endpoints, so the SPA can't accidentally call
them. **No action.**

| Flag | What it gates | Why BE-only |
|---|---|---|
| `FEATURE_AI_COMPETITIVE_INTEL` | AI pipeline writing `competitor_mentions` rows | Output rendered via existing panels; flag only gates the inference job |
| `FEATURE_AI_PREDICTIONS` | Backend ML inference for churn prediction | Output flows through normal customer endpoints |
| `FEATURE_AI_SUMMARIES` | AI summary pre-computation cron | Lazy compute also lives behind FEATURE_AI_DEAL_RISK; SPA-facing endpoint exists |
| `FEATURE_AI_TRIAGE` | Incoming email auto-categorization | Pure backend; SPA reads the resulting category |
| `FEATURE_BEHAVIORAL_SCORING` | Lead scoring weights pipeline | Output is lead.score; SPA renders unconditionally |
| `FEATURE_INVOICE_PAID_EVENT` | Event-bus emitter for invoice.paid | No SPA surface — downstream consumers (cron, webhooks) only |
| `FEATURE_PUBLIC_API` | External tenant API key access | SPA isn't a public API consumer |
| `FEATURE_TRANSFORMER_SEQ_EMBEDDING` | Shadow embedding pipeline | Writes `opportunity_transformer_seq_embeddings`; SPA doesn't read |
| `FEATURE_V4_ADDITIVE_READMODEL` | V4 read-model background materializer | Output surfaced via existing endpoints |
| `FEATURE_V4_DEAL_REPLAY` | Backend snapshot job | Surfaced via `/opportunities/{id}/replay` already gated FE-side via panel visibility |
| `FEATURE_V4_FEATURE_STORE` | Daily feature-store write job | Output table read by other features |
| `FEATURE_V4_SALES_DNA` | DNA mining cron | Output read by sales_dna panel via existing gate |
| `FEATURE_V4_SALES_EVENTS_SHADOW` | Shadow write to event log | Internal; no SPA |
| `FEATURE_V5_INTELLIGENCE` | V5 pipeline materializer | Existing FE consumes V5 outputs through endpoints; no separate gate needed |
| `FEATURE_V6_REALTIME` | Pre-SSE polling vs SSE selector | SPA already uses SSE for cockpit (R11) |
| `FEATURE_V7_LLM_OBJECTION` | LLM-based objection detection | Outputs surfaced via Objections panel |
| `FEATURE_V9_CRM_SYNC` | Salesforce / HubSpot sync background job | Admin sync surface gated separately |
| `FEATURE_V9_NL_SEARCH` | NL search backend | SPA gates the search bar via separate route flag |
| `FEATURE_SESSION_MANAGEMENT` | Admin session-revoke API | Admin tool; route already gated by role |
| `FEATURE_WEBHOOKS` | Webhook delivery pipeline | SPA admin page exists but visibility gated by role |
| `FEATURE_TEAM_ACCESS` | AccountTeam membership enforcement | Backend authz; no separate FE toggle |
| `FEATURE_FIELD_PERMISSIONS` | apply_request_perms field masking | Backend authz; SPA sees masked values transparently |
| `FEATURE_RAG` | RAG retrieval pipeline | Output surfaced via AI summary endpoints |

### FE+BE (needs FE gate) — 9 flags

These flags gate SPA panels / routes that today **render
unconditionally** — the backend returns empty or 404, but the SPA
shows a "no data" card with no indication the feature is disabled.
A `<FeatureFlagGate>` wrap makes this explicit.

| Flag | What to gate | FE location |
|---|---|---|
| `FEATURE_AI_DEAL_RISK` | AI Risk Card on OpportunityDetailPage | `frontend/src/features/board/OpportunityDetailPage.tsx` lines around `<Card title={t('opp_detail.ai_risk_title')}>` |
| `FEATURE_AI_PIPELINE_SUGGESTIONS` | Pipeline Suggestion panel | `frontend/src/features/ai/AiInsightsPage.tsx::PipelineTab` |
| `FEATURE_BUYER_MAP` | Buyer State Timeline + Decision Graph | `frontend/src/features/board/OpportunityDetailPage.tsx` around `buyerStateTimeline` |
| `FEATURE_DEAL_HEALTH` | Health badge on customer/board cards | `frontend/src/features/customers/HealthScoreCard.tsx` |
| `FEATURE_DECISION_GRAPH` | Decision Graph card | `frontend/src/features/board/OpportunityDetailPage.tsx` |
| `FEATURE_GUIDED_SELLING` | Stage Requirements / Selling Guide panel | `frontend/src/features/board/OpportunityDetailPage.tsx` |
| `FEATURE_ESIGN` | E-sign request button on Quote page | `frontend/src/features/quotes/QuoteDetailPage.tsx` |
| `FEATURE_PWA` | Install-app button | `frontend/src/app/App.tsx` (currently always-visible) |
| `FEATURE_SEQUENCES_V2` | V2 sequence enrollment UI | `frontend/src/features/board/OpportunityDetailPage.tsx` |
| `FEATURE_V10_PARTS_INTEL` | Parts Intel dashboard route | Already routed; just needs wrap |
| `FEATURE_V2_BOARD` | V2 board vs legacy board switch | Migration completed; can be removed |
| `FEATURE_V9_CALENDAR_OAUTH` | Calendar settings panel | `frontend/src/features/settings/SettingsPage.tsx` |

### Recommended deletions — 3 flags

| Flag | Reason |
|---|---|
| `FEATURE_V2_BOARD` | Migration completed in R7; legacy board removed. Flag has no effect. |
| `FEATURE_V4_SALES_EVENTS_SHADOW` | Shadow table populated; observation period over. Promote to default-on or delete. |
| `FEATURE_V5_INTELLIGENCE` | Subsumed by per-feature flags (FEATURE_DECISION_GRAPH etc.). Coarse flag has no remaining effect. |

## Migration path

1. **Add 9 `<FeatureFlagGate>` wraps** (one PR per flag or one batched PR).
2. **Remove 3 dead flags** in one cleanup PR — search call sites with
   `grep -r "FEATURE_V2_BOARD\|FEATURE_V4_SALES_EVENTS_SHADOW\|FEATURE_V5_INTELLIGENCE"`,
   ensure all gates are coalesced, then delete from `config.py`.
3. **Document the BE-only category** in `config.py` with a per-flag
   docstring explaining why the SPA doesn't reference it.

## Test gate (after migration)

A future test should pin the BE-only allowlist so a regression
(adding a flag without categorizing it) trips CI:

```python
# backend/tests/test_round15_feature_flag_audit.py
BE_ONLY_FLAGS = {
    "FEATURE_AI_COMPETITIVE_INTEL", "FEATURE_AI_PREDICTIONS",
    # ... 23 flags
}
FE_GATED_FLAGS = {
    "FEATURE_AI_DEAL_RISK", "FEATURE_AI_PIPELINE_SUGGESTIONS",
    # ... 9 flags after migration completes
}


def test_no_uncategorized_feature_flags() -> None:
    declared = _collect_declared_flags()
    uncategorized = declared - BE_ONLY_FLAGS - FE_GATED_FLAGS
    assert not uncategorized, (
        f"Uncategorized flags: {uncategorized}. "
        "Update docs/runbooks/r15-feature-flag-categorization.md "
        "and the allowlist before merge."
    )
```

## Effort

- BE-only category: zero work — table is the deliverable.
- FE+BE: 9 flags × ~1 hour each = 1 day.
- Deletions: ½ day with thorough grep + dev smoke.

**Total: 1.5 days** to close F-015 fully.

## Status

- This commit: runbook published, no code changes yet.
- Follow-up PRs: per the migration path above.
