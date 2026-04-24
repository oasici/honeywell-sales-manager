# Service Level Objectives — Honeywell Sales Suite

**Status:** v1 — published 2026-04-24
**Owner:** Engineering (solo)
**Review cadence:** Monthly, first Monday. Post review note in `docs/runbooks/`.

This document is the commitment we make to ourselves (and, eventually,
customers) about how reliable the product is. It exists to keep two
failure modes out of the backlog:

1. **Silent degradation** — "it still loads but the dashboard is slow"
   going unnoticed until a customer calls.
2. **Feature sprint paralysis** — "we can't ship anything, there's
   always a bug" without a numeric threshold to enforce a freeze.

The first is covered by **SLIs + alerts**. The second is covered by
**error budgets + freeze policy**.

---

## SLIs (what we measure)

All SLIs are measured against production only. Sandbox is explicitly
excluded — staging breakage is expected during iteration.

| SLI | Definition | Source |
|-----|------------|--------|
| **Availability** | % of `/api/health` probes in a 30-day window returning HTTP 200 | BetterStack synthetic monitor, 60s interval |
| **API latency (p95)** | p95 of `duration_ms` across `/api/v1/*` paths, excluding `/api/health` | Structured access logs in Render, parsed by log aggregator |
| **API error rate** | % of `/api/v1/*` responses with `status_code >= 500` | Structured access logs |
| **Login success rate** | % of `POST /api/v1/auth/login` responses returning 200, excluding 401 (wrong-password is not a failure) | Structured access logs |
| **Critical flow success** | Synthetic E2E (Playwright) that logs in → opens dashboard → creates a quote, passes or fails per run | Nightly GitHub Actions scheduled run |

---

## SLO targets (30-day window)

| SLI | Target | Error budget | Budget consumed at... |
|-----|--------|--------------|------------------------|
| Availability | **99.5%** | 3h 36m/month of downtime | 1h 48m = 50% consumed |
| API p95 latency | **< 500ms** | 5% of 5-minute windows may violate | 72 bad windows / 30d |
| API error rate | **< 1%** | N/A — any sustained breach pages | — |
| Login success rate | **> 95%** (exc. 401) | 5% operational failures | — |
| Critical flow success | **100% nightly** | 0 consecutive failures tolerated | 2 consecutive = page |

Targets are deliberately conservative for a v1 product. We'll tighten
them after the first quarter of real production traffic.

---

## Error budget policy

Error budget is how much bad customer experience we're willing to
"spend" in a 30-day window. The policy exists so reliability and
feature velocity stay in a healthy tension.

| Budget consumed | Action |
|-----------------|--------|
| 0–50% | Ship normally. No changes to cadence. |
| 50–75% | **Warning** — review the last week of incidents in the Monday retro. Slow down risky deploys (migrations, auth changes). |
| 75–100% | **Merge freeze on non-critical work.** Only security fixes, incident response, and SLO-restoring work merge to main. Feature PRs wait. |
| Exceeded | **Post-mortem required** before the freeze lifts. Document in `docs/runbooks/`. Next month's budget starts from 0, not the carryover. |

The freeze is social, not automated — there's no CI gate. The SLO doc
is the shared reference; anyone can point at it to push back on a
"just this one feature" exception request.

---

## Alert policy

Alerts live in **BetterStack** (uptime + synthetic) and **Sentry**
(error rate, latency tails, specific error groups). Both page the
same channel (Slack `#alerts` + email fallback).

| Alert | Severity | Condition | Response SLA |
|-------|----------|-----------|--------------|
| `/api/health` down | P1 | 3 consecutive failures (3 min) | Acknowledge within 15min |
| Synthetic E2E login fails | P1 | 2 consecutive nightly runs | Acknowledge before next business day |
| 5xx rate > 5% for 5min | P1 | Sentry or log aggregator | Acknowledge within 15min |
| p99 latency > 2s for 10min | P2 | Sentry performance | Acknowledge within 1 hour |
| New Sentry issue, level=error | P3 | First seen in last 15 min | Review within next business day |
| Sentry issue frequency spike (>10/min) | P1 | Sentry alert rule | Acknowledge within 15min |

**No P0.** Anything truly customer-stopping gets reclassified as P1
and paged. The point of the tier system is to prevent alert fatigue,
not to mask real incidents.

Any alert that fires more than 3 times without actionable outcome
(flapping, false-positive) must be either tuned or removed. Silent
alerts erode trust in the system.

---

## Why these specific thresholds

- **99.5% uptime** = what Render's own SLA promises. Going higher
  without multi-region infra is dishonest.
- **p95 < 500ms** = B2B SaaS baseline; users will complain at 1s+.
  p99 is more volatile, less actionable — hence we SLO on p95 and
  only alert on p99.
- **1% error rate** = one busted request in a hundred. Beyond this
  the dashboard starts feeling broken, not flaky.
- **95% login success** deliberately excludes 401s. Wrong-password is
  a normal outcome, not a service failure; counting it would train us
  to ignore the metric.

---

## Out of scope for v1 SLOs

Documenting these so we don't forget they exist when scale demands
them:

- Per-tenant SLOs (only relevant at multi-tenant enterprise stage)
- Regional availability zones (we're single-region on Render)
- Database availability as a separate SLI (piggybacks on /api/health)
- Claude API degradation (covered by circuit breaker in PR-1, not
  a direct SLI because it's a best-effort feature)
