# On-Call Playbook

Single-page cheatsheet for the operator who got paged at 03:00. Every
decision tree is two clicks away — don't read past the section that
matches your alert.

> **Severity ladder.** SEV1 — login down, data loss risk, or 5xx > 5%.
> Page now. SEV2 — critical page broken for some users, slow but
> recovering. Slack #alerts. SEV3 — minor bug with workaround. File
> issue.

## First 5 minutes

1. **Open Sentry** → filter to last 15 min. What's the top issue?
2. **Open BetterStack/UptimeRobot** → which monitor is red?
3. **Open Render dashboard** → backend → Logs → last 5 min.
4. **Health check** — does `curl https://<backend>/api/health` return 200?
   - `database: ok` ✓
   - `redis: ok` ✓ (or `unavailable` if not configured)
   - `circuits.*.state` — if any "open", external API trouble (see below)
5. **Status page note** — even one-liner. "Investigating elevated 5xx,
   ETA 30m". Buys you time + lowers support churn.

## Symptom → first action

| Alert | Probable cause | First action |
|-------|----------------|--------------|
| 5xx rate spike | Recent migration / deploy | Sentry → top issue → revert deploy or fix forward |
| 5xx rate spike, no recent deploy | External API failure | Check `/api/health` → `circuits.*` |
| p95 latency > 1s | DB slow query / N+1 / cron interference | `pg_stat_statements`, see `db-backup-restore.md` |
| Memory > 80% | Leak / PDF queue full / soak symptom | Pod restart + check soak.js results |
| Login 401 spike | Brute force / JWT rotation / DB read failure | Check rate limit log, audit_logs for login events |
| Health `database: error` | DB connection lost | Render dashboard → DB → restart / restore |
| Health `circuits.claude_api: open` | Anthropic API down | Wait for breaker recovery (60s) — graceful degraded mode is in effect |
| Health `redis: error` | Redis down | Check Render dashboard. App degrades gracefully — no immediate action |
| 429 spike | Legitimate traffic burst OR abuse | Check `RATE_LIMIT_AI` / `RATE_LIMIT_LOGIN` log; raise temporarily if legit |

## Rollback

```bash
# Render dashboard → Deploys → "Rollback" the bad commit. Fastest path.
# OR via git:
git revert <commit-sha>
git push origin main
# Render auto-deploys the revert.
```

The rollback unblocks users; the fix can ship after.

## Disable AI urgently

When AI endpoints are causing real pain (cost spike, breaker stuck, bad
output reaching users):

```bash
# Render env var, takes effect on next request:
AI_ENABLED=false
```

All AI endpoints return 503 with a user-facing "AI unavailable" message.
Rule-based fallbacks continue serving the rest of the app.

## Disable a feature flag urgently

Render dashboard → Environment → flip the relevant `FEATURE_*` to
`false` → restart. See `docs/feature-flags.md` for what each flag
controls and what stays working.

## Common commands

```bash
# Tail backend logs
render logs --service honeywell-backend --tail

# Run health check from a shell
curl -s https://honeywell-backend.onrender.com/api/health | jq

# Force-rotate JWT secret (invalidates all sessions — last resort)
# Render dashboard → JWT_SECRET_KEY → regenerate

# Restore from backup (last resort, see runbook)
bash backend/scripts/restore_drill.sh   # tested monthly
```

## Cross-references

- `db-backup-restore.md` — DB outage, PITR, restore steps.
- `release-rollback.md` — full deploy rollback sequence.
- `incident-response.md` — postmortem template + retro process.
- `restore-drill.md` — backup integrity, monthly drill.
- `dependency-audit.md` — CVE in deps, blocked CI.
- `coverage-gate.md` — coverage CI red.
- `game-day-scenarios.md` — controlled chaos drills.
- `security-secrets.md` — rotated secret procedure.

## When you don't know what to do

1. Page another engineer. SEV1 isn't a solo activity.
2. If the system is degraded but stable, do nothing risky. Wait for help.
3. Don't run `git push --force` to main. Don't drop tables. Don't disable
   monitoring "just to silence the alarm".
4. Take notes. The retro depends on remembering what happened in order.

## Postmortem

Within 7 days of any SEV1, owner files a postmortem in
`docs/postmortems/YYYY-MM-DD-{slug}.md`:

```markdown
# Postmortem — <slug>

- **Date:** YYYY-MM-DD
- **Severity:** SEV1
- **Duration:** HH:MM (detection → recovery)
- **Customer impact:** N% of users couldn't <action> for HH:MM
- **Root cause:** <one paragraph>
- **Trigger:** <what kicked it off>
- **Detection:** <how we noticed>
- **Resolution:** <how we fixed>
- **Action items:**
  - [ ] Specific, owned, dated. No "we should consider" language.
```

No blame, no hero stories. The artifact is the action items.
