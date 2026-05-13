# Round-14 R14-CACHE-1 — cache invalidation migration runbook

## Context

The Round-14 audit observed the SPA has **173 ad-hoc
`queryClient.invalidateQueries({...})` calls in `features/`** versus only
**16 imports of `lib/cacheInvalidation.ts`**. CLAUDE.md mandates the
opposite — cross-feature fan-out belongs in the centralised helper so
mutations that touch multiple surfaces (closing a deal invalidates
kanban + dashboard + reports + cockpit + forecast) stay in sync.

Sprint 14c added **10 new helpers** covering the highest-traffic
cohorts the audit flagged (cockpit, compliance, email templates,
playbooks, webhooks, sequences, territory, approval rules, revenue
schedules, pipeline config). It deliberately did NOT migrate the 173
existing call sites — that's a multi-PR cleanup tracked here.

## Why this is a runbook, not a single PR

Touching 173 call sites in one commit would:
- Explode the diff and overwhelm review.
- Risk regressing 173 surfaces simultaneously if a helper has the wrong
  fan-out set.
- Bundle unrelated refactors that complicate future bisects.

The plan is one entity at a time, each in a small PR that can be
reverted cleanly.

## Migration order

Sequence by impact (call-site count, descending) and risk (mutation
blast radius). Numbers from `grep -rE "invalidateQueries\\(\\{ queryKey:
\\[" frontend/src/features/`:

| Order | Cohort | Helper | Sites | Notes |
|---|---|---|---|---|
| 1 | `cockpit` | `onCockpitSignalChanged` | 10 | Highest traffic; mostly signal resolve / dismiss + cockpit panels. |
| 2 | `compliance` | `onComplianceChanged` | 7 | Compliance dashboard + customer consent toggles. |
| 3 | `subscriptions` | `onSubscriptionChanged` (exists) | 5 | Helper exists, call sites just bypass it. Quick wins. |
| 4 | `playbooks` | `onPlaybookChanged` | 5 | Playbook detail + executions. |
| 5 | `emails` | `onEmailChanged` (exists) | 5 | Helper exists; surface migration. |
| 6 | `ai-tasks` | (no helper yet — add) | 5 | AI task triage; introduce `onAiTaskChanged`. |
| 7 | `pipelines` | `onPipelineConfigChanged` | 4 | Stage-config admin edits. |
| 8 | `dashboards` | (no helper yet) | 4 | Dashboard builder list + execute. Add `onDashboardChanged`. |
| 9 | `approval-rules` | `onApprovalRuleChanged` | 4 | Manager approval rule CRUD. |
| 10 | `webhooks` | `onWebhookChanged` | 3 | Webhook subscription CRUD + test fire. |
| 11 | `territory-detail` / `territories-tree` | `onTerritoryChanged` | 6 | Admin territory CRUD + assignment. |
| 12 | `sequence-enrollments` / `sequence-analytics` | `onSequenceChanged` | 6 | Sequence enrollment flow. |
| 13 | `revenue-schedules` | `onRevenueScheduleChanged` | 3 | Rev-rec entry status. |
| 14 | `email-templates` | `onEmailTemplateChanged` | 3 | Template CRUD. |
| 15 | `campaign-members` | (extend `onCampaignChanged`) | 3 | Already covered; surface migration only. |
| 16 | `ai-attributes` | `onAiAttributeDefinitionChanged` / `onAiAttributeValueChanged` (exist) | 3 | Helper exists. |
| Rest | long tail | various | ~70 | Single-entity helpers exist; mechanical sweep. |

## Per-PR shape

Each migration PR follows this template:

```diff
- onSuccess: () => {
-   queryClient.invalidateQueries({ queryKey: ['cockpit'] });
-   queryClient.invalidateQueries({ queryKey: ['opportunity', oppId] });
-   toast.success(t('cockpit.signal_resolved'));
- },
+ onSuccess: () => {
+   onCockpitSignalChanged(queryClient, oppId);
+   toast.success(t('cockpit.signal_resolved'));
+ },
```

Verify:
- `tsc -b` clean.
- The component still re-renders post-mutation (manual smoke).
- No new `invalidateQueries` calls were left behind in the same file.

## Drift gate (ESLint rule)

Once the count hits zero, land this rule in `frontend/eslint.config.js`:

```js
// In the features/components scope:
'no-restricted-syntax': [
  'error',
  {
    selector: "CallExpression[callee.property.name='invalidateQueries']",
    message:
      "Prefer a helper from lib/cacheInvalidation.ts (e.g. onCustomerChanged, onOpportunityChanged) over raw queryClient.invalidateQueries({...}). Cross-feature fan-out lives in the helper.",
  },
],
```

`lib/cacheInvalidation.ts` itself is the legitimate caller and stays
outside the rule's `files` glob.

Until the rule lands, the Round-14 audit doc and this runbook are the
guardrail. Reviewers should reject new `invalidateQueries` calls in
PRs and request the helper-migration approach.

## Status

- Sprint 14c (this commit): **10 new helpers added**, runbook authored,
  ESLint rule documented but not enabled.
- Sprint 14c follow-ups: 16 small PRs per the migration order above.
- Sprint 14c.final: enable the ESLint rule as `error`.

## Risk

The helper-only approach has one footgun: helpers can grow over time
to fan out to caches that don't exist for every caller, leading to
unnecessary refetches. Counter: each helper's invalidation set should
be reviewed quarterly against the actual cross-feature dependency
graph. The `onRecordsMerged(qc)` helper uses the nuclear option
(`qc.invalidateQueries()`) for the same reason — when the affected
set genuinely is "everything," it's safer than enumerating.
