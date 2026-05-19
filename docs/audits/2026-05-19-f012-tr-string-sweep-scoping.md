# F-012 — TR-string sweep scoping

**Date.** 2026-05-19
**Audit anchor.** `docs/audits/2026-05-13-deep-cross-layer-audit.md` § F-012
**Status.** Scoping complete; implementation deferred to the next i18n cycle.

---

## Why this exists

F-012 ("~30 hardcoded TR strings remain after R13/R14 sweeps") is a
medium-priority, zero-risk mechanical task. The audit estimated
"1 hour per file × ~10 files." The actual surface — measured with a
broader regex covering quoted TR-character strings *and* common
en-Latin labels (`'Save'`, `'Cancel'`) — is larger (~600 candidate
matches across ~12 high-traffic files). Most of the over-count is
noise: enum labels (`'sales_rep'`), CSS class fragments, role
strings, dictionary keys for objects the SPA never renders.

Rather than burn an entire session on mechanical wire-up (which can
sit in a quarterly i18n PR cycle), this doc:

1. Enumerates the actual user-facing surface per page.
2. Documents the established `useT()` migration recipe so any
   future contributor can finish a page in ~30 minutes.
3. Flags the keys that already exist in `frontend/src/lib/i18n.ts`
   so duplication is avoided.

---

## Migration recipe

The infrastructure already exists. For each page:

1. **Import the hook**
   ```ts
   import { useT } from '../../hooks/useT';
   ```

2. **Bind it at the top of the component**
   ```tsx
   export function MyPage() {
     const t = useT();
     // ...
   }
   ```

3. **Replace each TR literal with a `t()` call**
   ```tsx
   // before
   <PageHeader title="Müşteriler" description="Tüm müşteriler" />

   // after
   <PageHeader
     title={t('customers.title')}
     description={t('customers.subtitle')}
   />
   ```

4. **Add the key to `frontend/src/lib/i18n.ts` for all 5 locales**
   (`tr`, `en`, `de`, `fr`, `es`). The file is grouped by
   feature-prefixed key sections — find the existing
   `'<feature>.*'` block and append.

5. **Run the type check**
   `pnpm tsc --noEmit --pretty false` from `frontend/`. The
   `TranslationKey` type is derived from the `tr` keys, so a typo
   surfaces as a compile error.

6. **Verify dropdowns / enum labels remain in TR untouched** — these
   are backend-coupled (stage names, role identifiers) and are
   intentionally not localized at the SPA layer; the backend either
   returns the localized label or the SPA maps the enum to a key.

---

## Per-page inventory (top-10 by user-facing density)

The candidate counts below are from a regex that captures quoted
character runs starting with an upper- or TR-letter. The actual
user-facing string count per file is typically 25-50% of the raw
candidate count after filtering out enum labels, CSS class strings,
and dictionary keys.

| File | useT() bound? | Raw candidates | Estimated real user-facing | Notes |
|---|---|---|---|---|
| `features/board/BoardPage.tsx` | ✅ partial (`board.*` keys exist) | 62 | ~20 | Filter labels, KPI tiles, risk dropdown options, "Sıfırla", "Sales Board" subtitle. Mid-migration — `board.rotting_tooltip` etc. already wired. |
| `features/contracts/ContractDetailPage.tsx` | ✅ partial (`contracts.*` keys exist) | 30 | ~12 | Form labels (Başlık/Tutar/Başlangıç/Bitiş), 3 toast messages, edit-form heading. |
| `features/coaching/CoachingRepPage.tsx` | ❌ not bound | 39 | ~15 | Coaching dashboard — score labels, empty states, action chips. |
| `features/integrations/IntegrationsPage.tsx` | ❌ not bound | 52 | ~20 | Integration card titles + connect/disconnect buttons. Many are vendor names (kept). |
| `features/approvals/ApprovalRulesPage.tsx` | ❌ not bound | 61 | ~18 | Rule-builder dropdown labels, dialog text. |
| `features/admin/WorkflowRulesPage.tsx` | ❌ not bound | 90 | ~25 | Largest surface — workflow trigger/condition/action labels. Internal admin tool, lower-priority for i18n. |
| `features/admin/MergeRecordsPage.tsx` | ❌ not bound | 40 | ~15 | Merge wizard step labels + confirmation copy. |
| `features/admin/AuditLogPage.tsx` | ❌ not bound | 57 | ~18 | Event type filter chips, table headers. |
| `features/admin/TerritoryPage.tsx` | ✅ partial | 59 | ~22 | Territory CRUD form labels. |
| `features/admin/FieldPermissionsPage.tsx` | ❌ not bound | 61 | ~16 | Field-permission CRUD form. Internal admin. |
| `features/opportunities/OpportunitiesHomePage.tsx` | ✅ partial (`opps.*` keys exist) | 85 | ~25 | Widget tiles, stage labels, sort options. |

**Rough estimate of remaining user-facing TR strings: ~180 across these 11 files.** The audit's "~30" reflected the *post-R13/R14 long tail* on a smaller cluster of pages; subsequent feature work (R6-R14) introduced new strings faster than the i18n sweep caught them.

---

## Prioritization

If a future contributor picks this up, attack in this order:

1. **`BoardPage.tsx`** — daily-driver page for sales reps. Existing
   `board.*` namespace is well-developed. Migrating the filter card
   + KPI strip closes the highest-visibility gap. ~30 min.
2. **`OpportunitiesHomePage.tsx`** — second-most-trafficked page,
   `opps.*` namespace exists. ~30 min.
3. **`ContractDetailPage.tsx`** — small surface (~12 strings),
   already partially migrated. ~15 min.
4. **`CoachingRepPage.tsx`** — visible to managers + reps; build the
   `coaching.*` namespace as part of the migration. ~45 min.
5. **`IntegrationsPage.tsx`** — admin-visible only, but high
   touch-point. ~45 min.
6. **Admin pages** (WorkflowRules / MergeRecords / AuditLog /
   FieldPermissions) — internal tooling, lowest user impact.
   Recommend deferring to a separate "admin i18n" cycle. ~3 hours
   combined.

The 5-page user-facing tier (1-5 above) is ~2.5-3 hours of
mechanical work. The admin tier is another ~3 hours. Total
matches the audit's "~10 hours" estimate when scaled for the
actual string count.

---

## What was de-scoped from this sweep

- **Backend `tenant_id` allowlist comment in `factories.py`** —
  already TR-comment, kept as engineer-facing note.
- **Stage name maps** (`prospecting → Araştırma` etc.) in
  `BoardPage.tsx` — these are backend enum values; the canonical
  localization path is `stage_labels.<key>` on the backend, not
  client-side translation. Leaving as-is until backend gains
  stage-label endpoint.
- **CSS class fragments** matching the regex
  (`'inline-flex items-center'`) — false positives, not strings.
- **Vendor brand names** (`'HubSpot'`, `'Salesforce'`,
  `'Pipedrive'`) on `IntegrationsPage.tsx` — proper nouns, not
  localized.

---

## Related

- `frontend/src/lib/i18n.ts` — translation table (5751 lines,
  5 locales, ~1150 keys).
- `frontend/src/hooks/useT.ts` — translation hook (7 lines,
  reads `preferencesStore.language`).
- `frontend/src/stores/preferencesStore.ts` — language selector
  state.
- `docs/audits/2026-05-13-deep-cross-layer-audit.md` § F-012 —
  originating audit row.
