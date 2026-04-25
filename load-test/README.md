# Load Tests

[k6](https://k6.io)-based load tests for the Honeywell Sales Suite
backend. Four scenarios in increasing intensity:

| Script | Scenario | Use |
|--------|----------|-----|
| `smoke.js` | 1 VU × 1 min | Sanity check — does the deployment respond at all? |
| `baseline.js` | 50 VUs × 10 min | Typical production load. Sets the perf baseline. |
| `stress.js` | 100 → 500 VU ramp | Find the breaking point. |
| `soak.js` | 30 VUs × 2 hr | Memory leaks, connection pool exhaustion, slow drift. |

User journeys live under `scenarios/` and are imported by the four
top-level scripts so the same flow is exercised across all intensities.

## Prerequisites

- [k6](https://grafana.com/docs/k6/latest/get-started/installation/)
  installed locally, OR use the Docker entrypoint below.
- A test user account on the target backend with login credentials.
  The smoke job uses a dedicated `loadtest@example.com` user.

## Running locally

```bash
# Install k6 (macOS)
brew install k6

# Smoke against staging
BASE_URL=https://honeywell-backend-staging.onrender.com \
TEST_USER_EMAIL=loadtest@example.com \
TEST_USER_PASSWORD=*** \
k6 run smoke.js

# Baseline against staging
BASE_URL=... TEST_USER_EMAIL=... TEST_USER_PASSWORD=... \
k6 run baseline.js
```

## Running with Docker (no local k6 install)

```bash
docker run --rm -i \
  -e BASE_URL=https://staging.example.com \
  -e TEST_USER_EMAIL=loadtest@example.com \
  -e TEST_USER_PASSWORD=*** \
  -v "$(pwd):/scripts" \
  grafana/k6 run /scripts/baseline.js
```

## Thresholds

Each script defines its own SLO thresholds in `options.thresholds`. A
threshold breach exits the script non-zero so CI can fail the build:

| Threshold | Target | Why |
|-----------|--------|-----|
| `http_req_duration p(95)` | < 500ms (baseline) | SLO target from `docs/SLO.md` |
| `http_req_failed rate` | < 1% | Same SLO |
| `checks rate` | > 99% | Smoke can't tolerate ANY auth/login flake |

## Never run against production

The k6 scripts can hammer a backend hard enough to cause a real outage.
Each script aborts when `BASE_URL` matches the production hostname —
search for `assertNotProd` in any scenario file to see the guard.

## CI

The workflow at `.github/workflows/load-test.yml` runs `baseline.js`
weekly against the staging deployment and uploads the JSON summary as
an artifact. A regression alert (p95 > baseline + 20%) opens a GitHub
issue automatically.

## What's NOT covered

- AI endpoints — they're rate-limited per-user (PR-1.2) and call Claude
  with real cost. Load-testing them costs money and trips the breaker
  on the first failed call.
- File upload endpoints — would need a synthetic PDF fixture.
- Webhook delivery — outbound, can't measure with a load generator.
