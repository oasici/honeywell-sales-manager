# Business Continuity Plan (BCP)

> Last reviewed: 2026-04-27
> Next tabletop: 2026-07-15

## Objectives

- **RTO** (Recovery Time Objective): 4 hours for a full-region outage.
- **RPO** (Recovery Point Objective): 1 hour (Render automated backups every hour).

## Roles

| Role | Primary | Backup |
|------|---------|--------|
| Incident Commander | Platform lead | Engineering manager |
| Communications | Product manager | CS lead |
| Engineering | On-call SRE | Platform engineer |
| Customer-facing | CS lead | Account manager |

## Failure Modes + Runbooks

| Failure | Detection | Runbook | RTO |
|---------|-----------|---------|-----|
| Backend 5xx spike | Sentry alert | `RUNBOOKS/backend-5xx.md` | 30 min |
| DB unreachable | Render status + /health | `RUNBOOKS/db-recovery.md` | 1 h |
| Claude API outage | Claude 5xx rate > 10% | `RUNBOOKS/ai-degraded.md` | Feature-flag fallback to rule-based path |
| Qdrant outage | vector search 5xx | `RUNBOOKS/vector-degraded.md` | FEATURE_RAG off; ILIKE fallback |
| ERP partner down | connector 5xx | `RUNBOOKS/erp-outage.md` | Queue sync jobs; resume on recovery |
| Full region outage | Render status page | `RUNBOOKS/region-failover.md` | 4 h |
| Security incident | Sentry / user report | `RUNBOOKS/incident-response.md` | 1 h triage |

## Testing Cadence

- **Backup restore test**: quarterly, documented in
  `docs/RUNBOOKS/dr-test-log.md`.
- **Tabletop exercise**: semi-annual with full staff.
- **Chaos drill**: DB failover once per year.
