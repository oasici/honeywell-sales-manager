# Release Process

This project uses [release-please](https://github.com/googleapis/release-please)
to drive versioning and CHANGELOG maintenance from
[Conventional Commits](https://www.conventionalcommits.org/). The
operator's job during a release is small but real — read this once
before cutting the first tag.

## How it works

1. Every push to `deploy/render-sandbox` (or `main`) triggers
   `.github/workflows/release-please.yml`.
2. release-please scans commits since the last tag.
3. If at least one `feat:` / `fix:` / `perf:` / `security:` commit is
   present, release-please opens (or updates) a PR titled
   `chore(main): release X.Y.Z`.
4. The PR body is the auto-drafted CHANGELOG entry. Review, edit if
   needed, then squash-merge.
5. On merge, release-please tags the squash commit `vX.Y.Z`, creates a
   GitHub Release, and writes the CHANGELOG entry into `CHANGELOG.md`.

## Version-bump rules

Pre-1.0 (current state, manifest at `0.0.0`) follows
`bump-minor-pre-major: true`:

- `feat:` → patch bump (0.0.0 → 0.0.1)
- `fix:` / `perf:` → patch bump
- `feat!:` or `BREAKING CHANGE:` footer → minor bump (0.0.0 → 0.1.0)

After we cut `1.0.0`, the same rules graduate:

- `feat!:` → major (1.x.x → 2.0.0)
- `feat:` → minor
- `fix:` / `perf:` / `security:` → patch

## What goes in the CHANGELOG

Driven by `release-please-config.json` `changelog-sections`:

| Commit type | CHANGELOG section |
|-------------|-------------------|
| `feat`      | Added |
| `fix`       | Fixed |
| `perf`      | Performance |
| `security`  | Security |
| `refactor`  | Changed |
| `docs`      | Documentation |
| `ci` / `chore` / `test` / `build` / `style` | hidden |

Keep `chore` and `test` commits out of the changelog — customers don't
care that we bumped a dev dep or added a test fixture.

## Cutting the first release

The repo currently has `0.0.0` in `.release-please-manifest.json` and
no tags. The first release-please run will:

1. Pick up every conventional-commit since the start of the repo
   history (since there's no `v0.0.0` tag to bound the scan).
2. Open a chunky release PR proposing `0.1.0`.
3. Edit the CHANGELOG body to taste before squash-merging — once tagged,
   the entries are immortal.

> **Read the release PR carefully** the first time. The auto-drafted
> notes will include every prior commit because release-please can't
> see a baseline tag. After v0.1.0 lands, subsequent releases scope
> only to commits after the last tag.

## Manually editing CHANGELOG.md

The Unreleased section in `CHANGELOG.md` accumulates the release-please
entries and any hand-written notes. You can append to the Unreleased
section directly between releases — the merge will be additive.

Don't edit version-anchored sections (e.g. `## [0.1.0] - 2026-XX-XX`).
Once the tag is cut, the entry is immutable; corrections go in the next
release's notes.

## Skipping a release

Land a `chore(release): skip` commit. release-please ignores `chore`
by default so it won't open a release PR for that one push. Useful
when you want to merge a doc-only batch without a version bump.

## Rollback

Tags can be deleted, but the install base may have already pulled. The
better practice:

1. Land a fix forward as `fix(rollback): revert <bad change>`.
2. Let release-please cut the next patch.
3. Add a note to the new version's CHANGELOG entry calling out the
   reversion explicitly.

For real "yank a bad release" scenarios — i.e. the tagged code
introduced data loss or a security hole — coordinate with the on-call
team and the customer comm pipeline; the release-please workflow alone
isn't enough.

## Troubleshooting

- **No release PR opened, but I added `feat:` commits.** Check that
  the workflow ran on `deploy/render-sandbox` — the trigger excludes
  PR branches. release-please also needs ~30s; refresh.
- **PR title is stuck on a stale version.** release-please uses the
  manifest to track state. If `.release-please-manifest.json` got
  out of sync (e.g. after a force-push), update it manually and
  re-run.
- **CHANGELOG includes commits I want hidden.** Add the type to
  `release-please-config.json` `changelog-sections` with
  `"hidden": true` and let the next release sweep.
