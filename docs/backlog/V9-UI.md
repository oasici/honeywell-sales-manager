# V9 Gap Closure — Frontend Backlog

## Status

V9 endpoints exist on the backend at `app/api/v1/v9_gap_closure.py` covering:

- **CRM sync** (Sprint K) — `FEATURE_V9_CRM_SYNC`
  - `GET /v9/crm-connections`
  - `POST /v9/crm-connections`
  - `POST /v9/crm-connections/{id}/sync`
- **Calendar OAuth** (Sprint L) — `FEATURE_V9_CALENDAR_OAUTH`
  - `GET /v9/calendar/connections`
  - `POST /v9/calendar/oauth/start`
  - `GET /v9/calendar/meetings`
- **Board WIP** — `FEATURE_V9_BOARD` (planned)
- **NL search** (Sprint N) — `FEATURE_V9_NL_SEARCH`
  - `POST /v9/search/nl`

**The 2026-04-30 data discrepancy audit confirmed zero frontend clients exist for any of these routes.** Flipping the feature flags to `True` in production therefore only exposes endpoints that the UI cannot consume — every navigation produces a 404.

The flags are pinned `False` in `app/core/config.py` until this backlog clears.

## Frontend work required before un-gating

| Flag | Frontend deliverable | Estimated effort |
|---|---|---|
| `FEATURE_V9_CRM_SYNC` | `/admin/integrations/crm` page: list + add CRM connection, manual "Sync now" button, last-sync timestamp + error state | 2 days |
| `FEATURE_V9_CALENDAR_OAUTH` | `/admin/integrations/calendar` page: OAuth consent flow (Google/Outlook), meeting auto-log toggle, history of auto-linked meetings | 2 days |
| `FEATURE_V9_NL_SEARCH` | Global search box upgrade to call `/v9/search/nl` instead of (or alongside) the keyword search; render typed result groups (deal / customer / email / transcript) | 1.5 days |

Each deliverable also needs:

1. A new `v9*Api` block in `frontend/src/lib/api.ts`
2. Typed response interfaces in `frontend/src/lib/types.ts`
3. A route entry in `frontend/src/app/App.tsx` gated on the corresponding flag (see `FeatureFlagContext`, Phase 5 of the audit fix)
4. An entry in the admin sidebar gated on `SALES_MANAGER` role + the flag
5. E2E coverage of the new page (Playwright)

## Acceptance criteria for un-gating a flag

- [ ] `v9*Api` client exports cover every endpoint in the corresponding sprint
- [ ] At least one page renders the data with empty / loading / error states
- [ ] The route is reachable from the admin sidebar
- [ ] `tsc --noEmit` is clean
- [ ] An E2E test confirms the happy path
- [ ] The corresponding section of this doc is removed (the backlog shrinks as flags come online)

## Why we didn't just feature-flag the routes off

The endpoints already check the flags themselves (lines 54–64 of `v9_gap_closure.py`). We could have removed the `_require_v9_*` deps to keep the routes always on, but that would silently break authentication assumptions and confuse anyone reading the router. Leaving the flags in place keeps the router self-documenting.
