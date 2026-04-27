# V8 — Sequence Text Embedding + Multi-Tenant CRM + Seed

**Status**: 2026-04-27 — sprint plan
**Predecessor**: `docs/v7-intelligence-final-plan.md`

V7 closed the framework spec to ~99%. The last 1% + a major DX gap
("UI surfaces are empty without demo data") motivate V8:

1. Bring the LCS-based sequence similarity up to a **transformer-style
   text embedding** without adding heavy ML dependencies.
2. Push the **multi-tenant boundary down to CRM core tables** (users,
   customers, opportunities, quotes, leads).
3. Generate **comprehensive seed data** so every dashboard, list, and
   analytics surface has realistic content end-to-end.

---

## Sprint K — Sequence text embedding (V7 LCS → V8 token-bigram cosine)

**Why**: a real transformer (sentence-transformers) needs torch
(~700MB), too heavy for our deploy target. We achieve "transformer-
shape" semantics — bag of tokens with bigram features, L2-normalised
cosine — without the model weights. Interface stays drop-in
compatible with a future swap to a real embedder.

### New table — `opportunity_text_embeddings`

Migration `20260427_v8_text_embedding.py` adds:

- `opportunity_id` (PK, FK)
- `embedding_json` (TEXT, JSON-encoded float[])
- `dim INTEGER NOT NULL`
- `version VARCHAR(40) NOT NULL` (e.g. `v8-bigram-bow-256`)
- `vocab_hash VARCHAR(40) NOT NULL` — short hash so we know when
  the vocabulary drifted
- `generated_at TIMESTAMPTZ`

### New module — `app/services/text_embedder.py`

Pure functions:

- `tokenize_for_embedding(events, ctx)` → list[str] of joined
  unigrams + bigrams over the V6 sequence tokens (e.g.
  `["meeting", "quote_sent", "meeting->quote_sent", ...]`).
- `embed_tokens(tokens, dim=256)` → fixed-length L2-normalised
  vector via deterministic feature hashing.
- `cosine(a, b)` already exists in deal_similarity.

### Wiring

Similarity score becomes a **3-component blend**:

```
final = 0.5·cosine_struct + 0.2·LCS-ratio + 0.3·cosine_text
```

The blend stays drop-in: when text embedding row missing, we fall
back to V7 (cosine + LCS only).

### Tests

- Tokenization deterministic for same input
- Vector length == dim
- Vector L2-normalised (norm ≈ 1)
- Cosine of identical sequences = 1
- Cosine of disjoint sequences ≈ 0

---

## Sprint L — True multi-tenant CRM tables

**Why**: V7 added `tenant_id` to 8 V5/V6 *analytics* tables. CRM core
(users, customers, opportunities, quotes, leads) was deferred. V8
brings those in scope so analytics inherit tenancy honestly.

### Migration `20260427_v8_crm_tenant_id.py`

Adds **NULLABLE** `tenant_id INTEGER` to:

- `users`
- `customers`
- `opportunities`
- `quotes`
- `leads`

Plus an index on each (so tenant filter is fast).

NULL = "default tenant" — single-tenant deployments keep working
without touching anything. Multi-tenant deployments populate via
the bootstrap script + a default-tenant resolver.

### New helper — `app/services/tenant_context.scoped_for_user(user)`

Resolves the current user's `tenant_id` and returns a SQLAlchemy
filter. Endpoints can plug it in front of every list-endpoint
SELECT.

### Default tenant bootstrap

`scripts/bootstrap_default_tenant.py` (idempotent):
1. Insert tenant `default` if missing.
2. Backfill all NULL `tenant_id` rows to that tenant's id.
3. Print summary.

---

## Sprint M — Comprehensive demo seed

`scripts/seed_demo_data.py` populates the database with realistic
content covering **every major UI surface**. Idempotent — re-running
upserts by stable natural keys.

### Coverage matrix

| Entity | Count | Notes |
|---|---|---|
| Tenants | 2 | default + acme-eu |
| Users | 12 | 2 admins + 3 managers + 7 reps across tenants |
| Customers | 30 | mix of industries + size bands |
| Contacts | 80 | 2-4 per customer with seniority + DM flag |
| Opportunities | 80 | spread across stages: prospecting/qualified/proposal/negotiation/closed_won/closed_lost |
| Tasks | 60 | linked to opps with various statuses |
| Quotes + items | 60 | with discounts in 0-25% range |
| SpareParts | 40 | with PriceEntries |
| ActivityLogs | 600 | emails, meetings, calls, notes spread over 90 days |
| RevenueSignals | 200 | mix of severity + types |
| CompetitorMentions | 80 | tied to opps |
| Stakeholders | 200 | + StakeholderRoles for decision-gap engine |
| Objections + actions | 120 | for V5 objection intelligence |
| OpportunityEvent | 400 | for V5 event timeline |
| SalesEventShadow | 600 | shadow-synced from above |
| Leads | 40 | various statuses |
| Pipelines + StageConfigs | 3 + 18 | one per region |
| Playbooks + steps | 6 + 24 | mix of manual + DNA-promoted |
| EmailTemplates | 8 | |
| Campaigns + members | 4 + 100 | |
| Contracts + amendments | 20 + 5 | |
| DealRooms + docs | 10 + 30 | |
| MeetingLinks + bookings | 4 + 25 | |
| Subscriptions + revenue schedules | 12 + 36 | recurring revenue surface |
| Forecast + snapshots | 5 + 20 | |
| Sequences + enrollments + step runs | 4 + 60 + 180 | |
| ChatSessions + messages + auto rules | 8 + 50 + 4 | |
| ReportTemplates + folders + dashboards | 12 + 4 + 5 | |
| SavedViews + comments + notifications | 20 + 30 + 50 | |
| ApiKeys + webhooks + workflow rules | 4 + 6 + 8 | |
| BuyerStateHistory | inferred from OFD | |
| DecisionGap | computed by service | |
| OpportunityFeaturesDaily | computed by builder | 30-day backfill |
| SegmentBenchmarksDaily | computed by builder | |
| DNA patterns + recommendations | computed by miner | |
| Embeddings + similarity links | computed by service | |
| Replay deltas | computed by service | |

**Total rows**: ~3500+ across ~40 entity types.

### Execution

```bash
$ python -m scripts.seed_demo_data --apply
```

Steps:

1. Bootstrap tenants (default + acme-eu).
2. Insert users + customers + contacts.
3. Build opportunity dataset with stage spread + outcomes.
4. Generate ActivityLog history with proper temporal ordering.
5. Insert quotes/items, signals, competitor mentions, objections.
6. Run feature store builder for last 30 days (creates daily OFD/AFD/RFD).
7. Run V4/V5/V6/V7 nightly batch once → DNA, embeddings, replay
   deltas, anomalies, federated benchmarks.
8. Bootstrap default tenant + backfill.
9. Verify summary.

### Tests

- `tests/test_seed_demo_data.py` smoke-tests key counts after run.

---

## Validation gate

- pytest backend (≥ 661 + ~25 new V8 tests ≈ 685)
- frontend tsc + vitest + production build
- Seed script runs to completion locally on a fresh SQLite DB
- All migrations idempotent
- No breaking changes — every new column NULLABLE, every new
  service module additive

---

## After V8

Framework coverage ≈ 100% within the single-product scope. UI
demos populated end-to-end. Future V9+ candidates (out of scope
for this push):

- Real ML embedder (sentence-transformers / OpenAI embeddings)
  swapped behind the existing `embed_tokens` interface
- Multi-tenant CRM with row-level security via Postgres RLS
- Causal uplift A/B (requires control-group sample size we don't have
  yet)
