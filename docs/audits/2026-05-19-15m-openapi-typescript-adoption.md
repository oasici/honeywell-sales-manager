# 15m — openapi-typescript adoption plan

**Date.** 2026-05-19
**Audit anchor.** `docs/audits/2026-05-13-deep-cross-layer-audit.md`
§ F-006, F-009, "Adopt openapi-typescript" recommendation
**Status.** ✅ **Closed** as of 2026-05-20. Skeleton landed first (commit
`82a463f`), live adoption completed in 15m-1.5 through 15m-7. Generated
file is now 32,732 lines of TypeScript covering 22 `*Response` schemas;
the CI drift gate is live (no longer dormant). 13 hand-written
interfaces in `frontend/src/lib/types.ts` migrated to typed aliases
over `components['schemas']`; ~250 hand-written lines retired.

---

## Why this exists

The audit (2026-05-13) found ~5 known drift sites between the
backend Pydantic response schemas and the hand-written SPA types in
`frontend/src/lib/types.ts` (2157 lines):

- F-006 — `CustomerResponse` missing 5 KVKK consent fields.
- F-009 — `OpportunityResponse` missing `pipeline_id` / `territory_id`
  round-trip on a handful of endpoints.
- Several `manager_id` / `tenant_id` round-trip omissions caught in
  R5-TS-4/17..20.

Each drift was caught after the fact by review or a runtime cast
(`as unknown as { kvkk_consent: boolean }`). The audit's
recommendation:

> Generate FE types from OpenAPI (`openapi-typescript`) so this can't
> drift again.

This sprint (15m) lands the **infrastructure** — generator script,
CI drift gate, devDep, scoping doc. The actual migration of
`frontend/src/lib/types.ts` consumers is deferred to a follow-up
sprint (15m-2) because it requires per-call-site verification and
spans ~40 feature directories.

---

## What landed in 15m-1 (this sprint)

| Artifact | Purpose |
|---|---|
| `frontend/package.json` — `gen:api-types[:check]` scripts (no devDep) | Generator runs via `npx --yes openapi-typescript@^7`. The package is NOT in `devDependencies` because v7.x pins peer `typescript: ^5.x`, which conflicts with the project's `typescript: ~6.0.3`. Letting npx fetch the generator on demand sidesteps the peer-dep resolver entirely. |
| `frontend/package.json` — `gen:api-types` / `gen:api-types:check` scripts | Local developer affordance + CI hook. |
| `scripts/generate-api-types.sh` | Wrapper that boots FastAPI, dumps `/openapi.json`, runs `openapi-typescript`. Supports `--check` mode for CI. |
| `frontend/src/lib/api-types.gen.ts` | Placeholder. First real `npm run gen:api-types` run overwrites it. |
| `.github/workflows/ci.yml` — drift gate in `frontend-build` | Runs `gen:api-types:check`; auto-skips while placeholder is in place. |
| `.gitignore` — `backend/openapi.gen.json`, `_openapi_dump.db` | Avoids committing the source JSON or the dump-time SQLite file. |
| This doc | Migration plan. |

The drift gate is **dormant** until someone runs `npm run gen:api-types`
locally for the first time. That avoids landing a 4000-line generated
file in this skeleton commit and lets the team review the first
generation as a dedicated PR.

---

## First-run procedure (15m-2 kickoff)

A future engineer enabling the gate should:

```bash
# 1. Bring up the backend env (Postgres optional — the OpenAPI dump
#    only needs the FastAPI app object).
cd backend && pip install -r requirements.txt

# 2. Install frontend deps.
cd ../frontend && npm ci

# 3. Generate.
npm run gen:api-types

# 4. Eyeball the diff. The first generation will be large (~4000-6000
#    lines) — that's expected.
git diff frontend/src/lib/api-types.gen.ts

# 5. Commit and open a PR. Title: "feat(round-15-15m): first run of
#    openapi-typescript — drift gate enabled".
```

After this commit lands, every PR touching backend schemas must also
run `npm run gen:api-types` and commit the result, or CI fails.

---

## Migration order (15m-2 to 15m-N)

The hand-written `frontend/src/lib/types.ts` should migrate
incrementally. Each chunk is independently shippable. Suggested order
(by drift-risk descending):

| Chunk | Domain | Why first |
|---|---|---|
| 15m-2 | `Customer`, `CustomerResponse`, `CustomerHealthReport` | F-006 KVKK gap; highest-traffic entity. |
| 15m-3 | `Opportunity`, `OpportunityResponse`, `OpportunitySignal`, `OpportunityEvent` | F-009 pipeline_id/territory_id gap; central to kanban + cockpit. |
| 15m-4 | `Lead`, `LeadResponse`, lead-conversion DTOs | Round-trip `tenant_id` round-5 finding (R5-TS-4). |
| 15m-5 | Quote / Contract / Invoice / Subscription | Billing surface, field-perm masked. |
| 15m-6 | Campaign / Sequence / Playbook | Engagement surface. |
| 15m-7 | All remaining `*Response` types | Cleanup. |

Each chunk:
1. Imports the relevant `components['schemas']['<Name>']` from
   `api-types.gen.ts` and aliases it (`type Customer = components['schemas']['CustomerResponse']`).
2. Removes the corresponding hand-written interface from
   `types.ts`.
3. Runs `tsc --noEmit --pretty false` and fixes call-site fallout
   (typically property-name drift like
   `customer.created_at` → still works because backend already
   uses snake_case).

Estimated effort: ~1 day per chunk × 6 chunks = 6 dev-days for full
migration. Each chunk is independently safe to revert.

---

## Pitfalls to handle in 15m-2

### Pitfall 1 — `app.openapi()` may pull in a live DB import chain

`backend/app/main.py` imports models at module load (`from app.models
import *`). Some model `__init__` or relationship resolution can
touch a DB connection. The generator script sets:

```bash
DATABASE_URL=sqlite+aiosqlite:///./_openapi_dump.db
```

so the schema dump succeeds without a live Postgres. Verify this
holds for any new model added to `app.models.__init__`.

### Pitfall 2 — Generated names diverge from hand-written names

`openapi-typescript` derives type names from the response schema
title (FastAPI auto-generates `CustomerResponse`, `OpportunityRead`,
etc.). The migration must accept the generated name and update
imports, or add a thin alias layer:

```ts
import type { components } from './api-types.gen';
export type Customer = components['schemas']['CustomerResponse'];
```

The alias layer is recommended — it minimizes churn in the SPA call
sites.

### Pitfall 3 — Field-permission masking

`apply_request_perms` on the backend may mask fields at runtime
(`email → null` for sales_rep). The OpenAPI schema declares the
field as nullable when masking is possible. The SPA already treats
masked fields as nullable; the generated types should align.

If a generated type marks a field as required (non-nullable) but the
backend masks it, the type is wrong — file a backend ticket to add
`| None = None` to the Pydantic field. **The SPA must never paper
over masking with a `!` non-null assertion.**

### Pitfall 4 — Drift gate flake on Render free-tier

The CI gate boots FastAPI to dump the spec. If the boot has any
side effects (e.g. fetching a remote config), it can flake. The
script sets `ENVIRONMENT=development` which already short-circuits
the production-only branches; verify after first integration.

---

## What 15m does NOT do

- Migrate `frontend/src/lib/types.ts` consumers. That's 15m-2..15m-7.
- Add request-side typed API client (e.g. `openapi-fetch`). Today the
  SPA uses `axios` directly; switching to a typed client is a
  separate sprint.
- Cover the websocket / SSE surface — `openapi-typescript` only
  handles HTTP. The notifications SSE design (15n) is a separate
  doc.

---

## Risk

**Low.** The skeleton is dormant; CI gate auto-skips on the
placeholder. The generated file lives in a parallel namespace
(`api-types.gen.ts`) and doesn't interfere with the existing
`types.ts`. Reverting is a single commit.

The risk surface opens in 15m-2 when the first generation lands and
the gate goes live. At that point any backend schema PR that forgets
to run `npm run gen:api-types` fails CI — which is the intended
behavior.

---

## Related

- `docs/audits/2026-05-13-deep-cross-layer-audit.md` — F-006, F-009,
  "Adopt openapi-typescript" recommendation.
- `frontend/src/lib/types.ts` — current hand-written types (2157
  lines).
- `backend/app/main.py:451` — `openapi_url=None if is_production`.
  In production, the SPA cannot fetch /openapi.json; the generator
  is dev-/CI-only.
- `scripts/generate-api-types.sh` — entrypoint.
