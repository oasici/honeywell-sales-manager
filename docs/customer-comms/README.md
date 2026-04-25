# Customer Communication Templates

Pre-approved Turkish-language templates for the three communications
that recur most often: incident notification, feature release, and
security disclosure. Use them as a starting point, not boilerplate —
swap concrete details into every `[BRACKETED]` slot before sending.

## When to use which

| Template | Trigger | Audience |
|----------|---------|----------|
| `incident-template.md` | SEV1 outage, customer-visible degradation | All affected users + their account managers |
| `release-template.md` | Significant feature ship (gated behind a flag and now enabling) | All users on the affected plan |
| `security-disclosure.md` | CVE in a dependency, exposed PII, account compromise | All users in scope (legal counsel reviews first) |

## Workflow

1. Copy the template into the body of an email/Slack/in-app banner.
2. Fill every `[BRACKETED]` placeholder. Don't leave any.
3. **Read it back.** If the customer can't tell what to do next from
   the message alone, rewrite.
4. **Get a second pair of eyes.** For SEV1 incidents and security
   disclosures, this is non-negotiable.
5. Log the send in the relevant audit channel (incident postmortem,
   release notes, KVKK officer log).

## Tone

- Direct. Don't bury the lede in apology.
- Concrete. "[DURATION] outage" beats "extended period of difficulty".
- Honest. If we caused it, say so. If we don't know root cause yet,
  say that too — and give a follow-up date.
- No marketing language in incident or security communications.

## Translations

The templates are Turkish-first because the user base is Turkish.
English versions for global escalations should be drafted on demand
and added back here when stable.
