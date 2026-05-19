# F-015 — Feature flag categorization

**Date.** 2026-05-19
**Audit anchor.** `docs/audits/2026-05-13-deep-cross-layer-audit.md` § F-015
**Status.** Audit complete; gating decisions captured.

---

## Why this exists

The deep audit flagged 35 BE-only or missing-FE feature flags. A flag
that exists on the backend but is invisible to the SPA cannot be
operated — admins can't toggle it without an env-var change and
restart, and users can't see why a route 404s. Conversely, a
frontend-only flag is unsafe: hiding a sidebar item while leaving the
backend route open lets anyone with the URL bypass the gate.

The audit's contract (from `CLAUDE.md`):

> Backend must have a matching `_require_x()` dependency — never ship
> a frontend-only gate.

This document closes F-015 by:

1. Enumerating every `FEATURE_*` flag declared on either side.
2. Categorizing each into one of four buckets.
3. Recommending the operational fix per bucket.

---

## Inventory

**Backend** (`backend/app/core/config.py`): **42** flags.
**Frontend** (any `*.ts` / `*.tsx` reference): **27** literals.

Of these:

| Status | Count | Examples |
|---|---|---|
| **Both sides** — flag declared BE + referenced FE | 20 | `FEATURE_INVOICING`, `FEATURE_CAMPAIGNS`, `FEATURE_AI_ATTRIBUTES` |
| **BE-only** — declared BE, never referenced FE | 22 | `FEATURE_AI_SUMMARIES`, `FEATURE_DEAL_HEALTH`, `FEATURE_RAG` |
| **FE-only** — referenced FE, no BE declaration | 2 | `FEATURE_DISABLED` (test sentinel), `FEATURE_V4_SALES_EVENTS_SHADOW` (wildcard match below) |
| **Wildcard literals** (grep noise) | 3 | `FEATURE_V`, `FEATURE_SEQUENCES_V`, `FEATURE_STORE` (sub-strings of multi-character flag names) |

After de-duplicating wildcard noise, the actionable count is:

- **22 BE-only** flags that need a categorization decision.
- **2 FE-only** flags that need either a BE counterpart or removal.

---

## Categorization (four buckets)

### Bucket A — "Backend-only by design" (operator-toggled, no UI)

These gate **service-layer behaviour** (pipelines, batch jobs, AI
worker fan-out) that users don't surface in the SPA. They are safe
as BE-only — the SPA neither sees nor cares.

| Flag | Purpose | Action |
|---|---|---|
| `FEATURE_RAG` | Vector-search backfill workers (15j cohort 13 enabled retrieval; SPA uses the standard search endpoint regardless). | Keep BE-only. Add docstring noting "operator toggle for the worker; no UI gate." |
| `FEATURE_TRANSFORMER_SEQ_EMBEDDING` | V12 transformer pre-compute worker. SPA reads results via standard intelligence endpoints. | Keep BE-only. Mark `# Worker: no UI gate.` |
| `FEATURE_INVOICE_PAID_EVENT` | Internal event-bus topic gate. | Keep BE-only. |
| `FEATURE_BEHAVIORAL_SCORING` | Lead-score nightly recompute job. | Keep BE-only. |
| `FEATURE_AI_PREDICTIONS` | Background AI prediction batch. | Keep BE-only. |
| `FEATURE_AI_TRIAGE` | Email-triage scheduled worker. | Keep BE-only. |
| `FEATURE_WEBHOOKS` | Outbound webhook delivery worker. | Keep BE-only. Admin UI for webhook CRUD is gated by `FEATURE_WORKFLOW_RULES` separately. |
| `FEATURE_PUBLIC_API` | OAuth + public REST surface. | Keep BE-only. |
| `FEATURE_PWA` | Service-worker manifest generation. | Keep BE-only. |
| `FEATURE_SESSION_MANAGEMENT` | Hard session-revocation worker. | Keep BE-only. |
| `FEATURE_TEAM_ACCESS` | Multi-rep access expansion at the query layer (touched by every `scoped_for_user` call when the flag is on). | Keep BE-only — the SPA renders the same view regardless of whether the result set was expanded. |
| `FEATURE_FIELD_PERMISSIONS` | Field-level masking serializer pipeline. | Keep BE-only. The admin UI for permission CRUD is at `/admin/field-permissions` and is route-gated by the user's `sales_manager` role, not a feature flag. |

**Total: 12 flags.** Add a one-line `# bucket: A (backend-only by design)` comment above each in `config.py`.

### Bucket B — "Should be FE-gated but isn't" (production gap)

These gate user-visible features and ship without a matching FE
sidebar/route gate. A `sales_rep` can call the backend endpoint with
`curl` even when the SPA has no link.

| Flag | Affected surface | Recommended FE gate |
|---|---|---|
| `FEATURE_AI_SUMMARIES` | `/api/v1/ai/summarize/*` endpoints. Used by `OpportunityDetailPage` summary card. | Wrap the summary card with `<FeatureFlagGate flag="FEATURE_AI_SUMMARIES">`. |
| `FEATURE_AI_PIPELINE_SUGGESTIONS` | `/api/v1/ai/suggest-pipeline-update`. Used by the kanban "Suggest" button. | Hide the button when flag off. |
| `FEATURE_AI_DEAL_RISK` | `/api/v1/intelligence/deal-risk/*`. Surfaces `DealHealthCard` on opportunity detail. | Gate the card. |
| `FEATURE_AI_COMPETITIVE_INTEL` | Cockpit competitive-intel tile. | Gate the tile (the cache helper `onAiCompetitiveIntelChanged` already exists from cohort 8). |
| `FEATURE_BUYER_MAP` | `/api/v1/buyer-state/*`. Used by `BuyerRelationshipMap`. | Route-level gate. |
| `FEATURE_DEAL_HEALTH` | Deal-health endpoints. | Gate the indicators panel. |
| `FEATURE_DECISION_GRAPH` | Decision graph visualization. | Gate the panel. |
| `FEATURE_ESIGN` | `/api/v1/integrations/esign/*`. Used by `IntegrationsPage` esign card. | Gate the card. |
| `FEATURE_GUIDED_SELLING` | Stage-validation tooltips. | Gate the tooltip + the `stage_requirements` admin tab. |

**Total: 9 flags.** Each needs a single-line `useFeatureFlags()` check in the consuming component. Effort: ~3 hours.

### Bucket C — "FE has no BE backing" (security gap)

Two FE strings reference flags that aren't declared on the backend:

- `FEATURE_DISABLED` — used as a sentinel in
  `FeatureFlagContext.tsx`'s "unknown flag" code path. **Not a real
  flag.** It is the placeholder returned by the context when an
  unrecognized name is passed. Action: rename to `__UNKNOWN__` to
  avoid confusion with audit grep.
- `FEATURE_V4_SALES_EVENTS_SHADOW` — referenced by
  `tests/test_sales_events_shadow.py` and the cockpit (already
  shipped under a slightly different name on the BE:
  `FEATURE_V4_SALES_DNA`). Action: confirm with the test author that
  the intended flag is `FEATURE_V4_SALES_DNA`; if so, rename the FE
  literal. If `FEATURE_V4_SALES_EVENTS_SHADOW` is a separate concept
  that ships gated on its own, add it to `config.py`.

**Total: 2 entries** (1 sentinel rename + 1 contract decision).

### Bucket D — "Both-sides, contract OK" (no action needed)

20 flags already match the contract: declared BE, referenced FE,
matching `<FeatureFlagGate>` or `useFeatureFlags()` usage in the SPA,
matching `_require_x()` dependency in the API router.

Spot-checked: `FEATURE_INVOICING`, `FEATURE_CONTRACTS`,
`FEATURE_CAMPAIGNS`, `FEATURE_NETWORK_INTELLIGENCE`,
`FEATURE_DASHBOARD_BUILDER`, `FEATURE_CUSTOM_FIELDS`,
`FEATURE_PRODUCT_RULES`, `FEATURE_LIVE_CHAT`, `FEATURE_LEAD_LIFECYCLE`,
`FEATURE_APPROVAL_ROUTING`, `FEATURE_WORKFLOW_RULES`,
`FEATURE_BREACH_WORKFLOW`, `FEATURE_REPORT_BUILDER`,
`FEATURE_REVENUE_COCKPIT`, `FEATURE_REV_REC`, `FEATURE_SUBSCRIPTIONS`,
`FEATURE_TASKS`, `FEATURE_TERRITORIES`, `FEATURE_MULTI_PIPELINE`,
`FEATURE_AI_ATTRIBUTES`.

**No action.**

---

## Operational summary

| Bucket | Flags | Action | Owner |
|---|---|---|---|
| A (BE-only by design) | 12 | Add `# bucket: A` docstring | backend |
| B (BE-only, FE gate missing) | 9 | Wrap component in `<FeatureFlagGate>` | frontend |
| C (FE-only, BE missing) | 2 | Rename or add BE flag | mixed |
| D (correct) | 20 | none | — |

**Total flags reviewed: 43.** Audit's "35 BE-only / missing-FE" count
included some duplicates from the regex-broken `FEATURE_V` / `_V*`
matches; the de-duplicated actionable set is 23 (12+9+2). The
remaining 20 are already correct.

---

## Recommended next-step PRs

1. **Bucket A docstrings** (15 min). Add the bucket-A comment to
   `config.py` so future audits skip these by grep.
2. **Bucket B FE gates** (3 hours). 9 components touched, each gets
   a single-line `useFeatureFlags()` import + conditional render.
3. **Bucket C sentinel rename** (10 min). `FEATURE_DISABLED` →
   `__UNKNOWN__` in `FeatureFlagContext.tsx`. The
   `FEATURE_V4_SALES_EVENTS_SHADOW` question needs a PM call before
   action.

None of the three is gated by the NOT NULL tenant-id work; all are
independent of `Sprint 15k/15l/15m`. Recommended to schedule in the
next release window.

## Related

- `CLAUDE.md` — "never ship a frontend-only gate" rule.
- `docs/audits/2026-05-13-deep-cross-layer-audit.md` § F-015 — the
  originating audit row.
- `backend/app/core/config.py` — flag declarations.
- `frontend/src/contexts/FeatureFlagContext.tsx` — FE flag accessor.
