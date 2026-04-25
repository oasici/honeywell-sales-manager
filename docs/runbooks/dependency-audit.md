# Dependency Audit Runbook

CI fails when `pip-audit` reports any vulnerability or `npm audit` reports
HIGH/CRITICAL. Dependabot is wired to open patch PRs for these on a
weekly cadence. This runbook covers the manual triage path when the
queue gets behind.

## CI Gates

- **`backend-security`** — runs `pip-audit -f json`. Fails if vuln_count > 0.
  JSON report is uploaded as the `pip-audit-{sha}` artifact for 30 days.
- **`frontend-security`** — runs `npm audit --audit-level=high --omit=dev`.
  Fails on HIGH or CRITICAL only (moderate findings ride the weekly queue).
  JSON report uploaded as `npm-audit-{sha}` for 30 days.

## When CI is red

1. Download the `pip-audit-{sha}` or `npm-audit-{sha}` artifact from the
   failing run.
2. Open it with `jq`:

   ```bash
   jq '.dependencies[] | select(.vulns | length > 0) | {name, version, vulns}' pip-audit.json
   ```

3. For each finding, check Dependabot's open PRs first — patch likely
   already there, just merge it.
4. If no Dependabot PR, decide:
   - **Patch bump (safe)**: bump the pin in `requirements.txt`, run the
     full test suite, commit on its own branch.
   - **Major bump (risky)**: upgrade in a feature branch, run full
     suite + e2e smoke, plan rollout window. Don't bundle with feature
     work.
   - **No fix available**: add a temporary ignore via `pip-audit
     --ignore-vuln <ID>` in CI with a TODO comment + tracking issue.
     Time-box the ignore.

## Dependabot Config

Lives at [`.github/dependabot.yml`](../../.github/dependabot.yml). Three update streams:

| Ecosystem | Schedule | Notes |
|-----------|----------|-------|
| pip (backend) | Weekly Mon 07:00 | dev-deps grouped (pytest/ruff/black/mypy/pip-audit) |
| npm (frontend) | Weekly Mon 07:00 | react/tanstack, vite, sentry, dev-deps grouped |
| github-actions | Monthly | All actions in /workflows tracked |

Caps each ecosystem at 5 simultaneous open PRs to avoid drowning the
queue. Security advisories ignore the cap and ship immediately as
their own PR.

## Local audit

Same gates run locally:

```bash
# Backend
cd backend && pip-audit -f json -o pip-audit.json
jq '[.dependencies[].vulns[]] | length' pip-audit.json

# Frontend
cd frontend && npm audit --audit-level=high --omit=dev
```

A failing audit before the push saves a CI cycle.

## Ignoring a vulnerability (last resort)

If a CVE has no fix available and we accept the risk for a bounded
window, add to the CI step:

```yaml
- run: pip-audit --strict --ignore-vuln CVE-2026-XXXXX -f json -o pip-audit.json
```

Each ignore needs:
- Owner (a name, not a team)
- Tracking issue with reassessment date
- Mitigation (network policy, input filter, etc.) documented in the
  issue
