# Changelog

All notable changes to this project are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The `Unreleased` section accumulates work merged to the deploy branch
since the last tag. The release-please workflow at
`.github/workflows/release-please.yml` opens a release PR that drains
that section into a numbered version when a new release is cut.

## [Unreleased]

### Added — PR-4 Polish
- Comprehensive `.env.example` covering all 110 backend settings and 34
  feature flags, with inline notes on which are REQUIRED. Cross-references
  the auto-generated `docs/feature-flags.md` and the relevant runbooks.
- `docs/feature-flags.md` — auto-generated reference for every
  `FEATURE_*` flag with default, dependencies, consumer features, and
  rollback notes. Generator script at
  `backend/scripts/generate_feature_flags_doc.py`.
- `docs/runbooks/oncall-playbook.md` — single-page operator cheatsheet
  for the engineer paged at 03:00. Includes severity ladder, first-five-
  minutes loop, symptom→action table, and cross-links to the eight
  existing runbooks.
- `docs/customer-comms/` — three Turkish-language templates (incident,
  release, security disclosure) with `[BRACKETED]` slots and per-template
  internal checklists. Security template requires DPO + legal sign-off.

### Added — PR-3 Quality Gates
- k6 load test suite (`load-test/`): smoke / baseline / stress / soak.
  Weekly baseline run on CI against staging via
  `.github/workflows/load-test.yml`.
- Coverage gate at 45% in `backend-test` CI job. Current baseline ~47%.
- Dependabot config (`.github/dependabot.yml`) for pip / npm /
  github-actions with grouped dev-deps and ecosystem bundles.
- `pip-audit` and `npm audit` gates in CI — fail the build on any pip
  vulnerability and on HIGH/CRITICAL npm advisories.
- Game day chaos drill runbook (`docs/runbooks/game-day-scenarios.md`)
  with five staging-only scenarios.

### Added — PR-2 Data Safety
- Monthly DB restore drill GitHub Actions workflow
  (`.github/workflows/restore-drill.yml`) plus the
  `backend/scripts/restore_drill.sh` script. Both refuse to write to any
  URL containing `prod`/`production`.
- KVKK auto-anonymization scheduler task. Gated behind
  `KVKK_AUTO_ANONYMIZE_ENABLED`. Anonymizes EmailRequest PII >2 years
  and dormant Customer PII >3 years. Idempotent, audit-logged.
- Audit endpoint upgrades — `entity_id`, `since`/`until`, `action_prefix`
  filters; CSV export with 10k row cap; `/audit/data-export/{user_id}`
  for KVKK Article 15 right-of-access.
- Admin UI: filter form on `/audit`, new `/kvkk-export` page that lets
  the operator pick a user and download the JSON bundle.

### Added — PR-1 Resilience
- `claude_messages_create` wrapper (`backend/app/core/claude_client.py`)
  routes every Claude API call through `claude_breaker`. 8 service
  files migrated. Breaker fast-fails after 3 consecutive errors with
  30s recovery.
- Circuit breaker state surfaced on `/api/health` under `circuits`.
  Health status flips to `degraded` when any breaker is open.
- AI rate limit (60/min, per-user) and upload rate limit (10/min,
  per-user) sliding-window dependencies, applied to the `/ai` router
  and the four file-upload endpoints.
- Env-driven DB pool tuning (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`,
  `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`).

### Fixed
- `/api/health` was calling `await get_redis()` on a sync function; the
  surrounding `try/except` masked the resulting `TypeError` as
  `redis: error`. The endpoint now reflects real Redis connectivity.

### Security
- `pip-audit` gate is no longer wrapped in `|| true`. Vulnerable backend
  pins now fail CI; Dependabot opens the patch PRs.
- KVKK auto-anonymization is opt-in per environment and writes a
  `kvkk_*_auto_anonymize` audit row per affected entity.
- Restore drill script refuses to wipe any URL whose hostname or path
  contains `prod` / `production` (case-insensitive).

---

## [Pre-PR-1 baseline] - 2026-04-09

### Production Readiness baseline (before this changelog started)
- Sentry backend + frontend integration with PII scrubbing, Sentry tunnel
  endpoint for browser telemetry.
- Structured logging with `request_id` propagation.
- SLO targets and error budget policy published in `docs/SLO.md`.
- v3 platform expansion: opportunities home, territories, integrations,
  competitive intel.
- Cookie-first authentication with async-safe token revocation,
  single-PDF semaphore, render.yaml CORS hardening.
