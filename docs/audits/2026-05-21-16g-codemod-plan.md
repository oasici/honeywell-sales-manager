# Sprint 16g — `api-types.gen.ts` Codemod Plan

**Date.** 2026-05-21 · **Status.** Pre-step done; codemod itself is the
next sprint.

The Round-15 audit's N15-ARCH-1 finding identified 7 verified-divergent
CRM interfaces in `frontend/src/lib/types.ts` that should be aliased to
the generated `api-types.gen.ts` `*Response` schemas. Doing so requires
a pre-step (add the missing FE-only fields to backend response schemas
so the regenerated types include them) followed by the actual codemod.

## Pre-step status — DONE (this commit)

1. ✅ Refreshed `docs/openapi.json` and `frontend/src/lib/api-types.gen.ts`
   from current backend. Snapshot grew from 32 987 → 38 727 lines and
   from 212 → 545 component schemas, reflecting the Round-15 typing
   sweep (113 → 515 typed endpoints, +137 new schema classes across
   17+ new schema files).

2. ✅ Added these computed fields to backend Response schemas so the
   generated TypeScript includes them:

   | Schema | Field | Where it's read in the SPA |
   |---|---|---|
   | `CustomerResponse` | `pinned` | `CustomerListPage`, `CustomerDetailPage` |
   | `OpportunityResponse` | `last_activity_at` | `BoardPage`, `OpportunitiesHomePage` |
   | `OpportunityResponse` | `open_tasks_count` | `BoardPage`, `OpportunityDetailPage` |
   | `OpportunityResponse` | `open_quotes_count` | `BoardPage`, `OpportunityDetailPage` |
   | `LeadResponse` | `full_name` | `LeadDetailPage`, `LeadListPage` (column key) |
   | `LeadResponse` | `owner_name` | `LeadDetailPage`, `LeadListPage` |
   | (already present) | `rotting_days` | already on `OpportunityResponse` |
   | (already present) | `quote_count`, `total_quote_value` | already on `CustomerResponse` |

3. ✅ Verified the new fields land in `api-types.gen.ts`:
   ```
   $ grep -nE "OpportunityResponse:|last_activity_at|open_tasks_count" \
       frontend/src/lib/api-types.gen.ts | head
   14413: OpportunityResponse: {
   14455:    last_activity_at?: string | null;
   14457:    open_tasks_count?: number | null;
   14459:    open_quotes_count?: number | null;
   ```

## Codemod itself — TODO (Round-16 cohort)

Replace each of these 7 manual interfaces in `frontend/src/lib/types.ts`
with a type alias:

```typescript
// Before:
export interface Customer {
  id: number;
  name: string;
  // … 25+ fields with various nullability semantics
}

// After:
import type { components } from './api-types.gen';
export type Customer = components['schemas']['CustomerResponse'];
```

### Files to migrate

| Manual interface | lib/types.ts line | Generated equivalent |
|---|---|---|
| `Customer` | ~42 | `components['schemas']['CustomerResponse']` |
| `Opportunity` | ~542 | `components['schemas']['OpportunityResponse']` |
| `Lead` | ~2037 | `components['schemas']['LeadResponse']` |
| `Quote` | ~363 | `components['schemas']['QuoteResponse']` |
| `Contract` | ~1977 | `components['schemas']['ContractResponse']` |
| `User` | ~25 | `components['schemas']['UserResponse']` |
| local `User` in `features/admin/UserManagementPage.tsx:27` | — | same as above (drop local) |

### Migration order (least → most risky)

1. **`User`** in `UserManagementPage.tsx` — local interface, single
   consumer. Drop it and import the shared one.
2. **`Lead`** — smaller surface, most fields already optional in
   manual + generated.
3. **`Contract`** — embedded `customer` summary needs a generated
   nested type alias for cleanliness.
4. **`Quote`** — has `QuoteStatus` literal union in manual; generated
   uses bare `string`. Either narrow generated or widen manual.
5. **`Subscription`** — has many enum-shaped fields; verify literal
   unions.
6. **`Opportunity`** — has the most call sites; verify each render
   path doesn't assume non-nullable fields the schema marks Optional.
7. **`Customer`** — last; biggest blast radius (used by every CRM
   surface).

### Per-call-site verification

For each migrated type, run:

```bash
cd frontend && npx tsc --noEmit --pretty false
```

After each step. Strict-mode TS will surface any consumer that
assumed a non-nullable value where the schema declares Optional
(which is the most common breakage when moving from manual to
generated).

### Expected post-codemod state

- `lib/types.ts` shrinks by ~600 LOC (the 7 interfaces).
- Type drift between backend and SPA collapses: a future field
  rename on the backend automatically propagates to the SPA via
  the regenerated file.
- The `R14-CACHE-1` ESLint rule can be extended to forbid manual
  `interface Customer | Opportunity | Lead | Quote | Contract | User`
  declarations outside `lib/types.ts`.

### Risk

LOW for the first 3 (User, Lead, Contract); MEDIUM for the last 4
(Quote, Subscription, Opportunity, Customer) because they touch
many components that may have undocumented nullability assumptions.
The codemod's TS errors will surface them all; addressing them is
mechanical but tedious (10-30 errors per interface based on a sample).

### Estimated effort

- Pre-step (this commit): done.
- Codemod + per-call-site cleanup: 1-2 dev-days as documented in the
  Round-15 audit §12 Sprint 16g estimate.

---

## Related

- `docs/audits/2026-05-20-cross-layer-audit-round15.md` § N15-ARCH-1
- `frontend/src/lib/api-types.gen.ts` (38 727 lines, 545 schemas)
- `scripts/generate-api-types.sh` — regeneration entry point
- `frontend/package.json::gen:api-types:check` — CI drift gate
