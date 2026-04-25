# Coverage Gate Runbook

CI fails the `backend-test` job when `pytest --cov-fail-under=45` reports
total coverage below 45%. The floor lives in `.github/workflows/ci.yml`,
not in `pytest.ini` — that's deliberate: enforcing it in pytest.ini would
slow every local test run by ~30s. Locally, run `pytest --cov=app` only
when you care.

## Why 45%

Baseline at the time the gate landed was ~46.77%. The 2-point buffer
absorbs noise from single-test additions/removals between PRs. Without
the buffer, an unrelated PR that legitimately removes a stale test
flips the build red.

## When CI is red on coverage

The `term-missing:skip-covered` report in the build log lists the
files that still have uncovered lines. Three resolution paths:

1. **Coverage dropped because a PR added code without tests** — add
   tests that exercise the new code paths. Re-run `pytest --cov=app`
   locally to confirm before pushing.
2. **Coverage dropped because a PR removed tests** — was the test
   wrong, or were we counting on it? If the test was redundant,
   confirm coverage stayed flat before merging. If it was load-bearing,
   restore it.
3. **Coverage drifted from 47% to ~45% over many small PRs** — schedule
   a coverage sprint. Don't lower the floor; ratchet it up after.

## Ratchet up

When the suite legitimately moves above 50% and stays there for a
sprint, raise `--cov-fail-under` accordingly. Process:

1. Check the last 30 days of CI runs — confirm the new floor is steady.
2. Open a PR that bumps the threshold, runs the full suite, and
   updates this runbook.
3. Don't bundle threshold changes with feature work. The bump is its
   own commit so a future regression can revert it cleanly.

## Local one-liner

```bash
cd backend
pytest tests/ --cov=app --cov-report=term-missing:skip-covered \
              --cov-fail-under=45 -q
```

To find untested files quickly:

```bash
pytest --cov=app --cov-report=term --no-header -q 2>&1 \
  | awk '$NF == "0%" { print $1 }'
```

## Frontend

Frontend coverage is currently measured by vitest only on imported
modules (~57% of touched files). A real coverage gate would require
configuring `coverage.all: true` in `vitest.config.ts` and seeding
tests for untested route components. Until that work is scoped, the
frontend gate is the green test count itself: `npm test` must pass.
