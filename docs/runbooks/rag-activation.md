# RAG Activation — Qdrant + Embedding Model

System Health page showing `qdrant: error` / `embedding_model: not_loaded`? That's the default state — both are opt-in. Follow the steps below to bring them online.

## Why they're off by default

| Component | Reason it's off |
|---|---|
| Qdrant | Render does not host Qdrant; you need an external cluster (Qdrant Cloud free tier works fine). The container ships with `QDRANT_URL` empty by default, which makes the client fail every connection. |
| Embedding model | `torch` + `sentence-transformers` add ~500 MB to the image and ~1 GB to resident RAM. We keep them out of the base `requirements.txt` so the app stays installable on Render Free; they install on demand when `INSTALL_RAG_DEPS=1`. |

## Prerequisites

- **Render plan**: Standard (≥1 GB RAM) or higher. Free tier (512 MB) cannot hold the embedding model in memory.
- **Qdrant Cloud account**: free tier is enough for the current dataset (4 K parts + 8 deals + interactions ≈ <50 MB of vectors against a 1 GB quota).

## Step 1 — Create the Qdrant Cloud cluster

1. Sign up at https://cloud.qdrant.io/
2. **Create cluster** → Free tier → pick a region close to Render (Frankfurt for `oregon`/`frankfurt` Render regions, US-East for `ohio`).
3. Wait ~60 s for provisioning. Copy two values from the cluster overview:
   - **Cluster URL** — looks like `https://xxxxx-xxxx.aws.cloud.qdrant.io:6333`
   - **API Key** — under "API Keys" tab → "Create API Key" → save the value (it's shown only once).

## Step 2 — Configure Render env vars

In the Render dashboard for the **honeywell-backend** service → **Environment** tab, set:

| Key | Value | Source |
|---|---|---|
| `QDRANT_URL` | `https://xxxxx-xxxx.aws.cloud.qdrant.io:6333` | Step 1 |
| `QDRANT_API_KEY` | `<api-key-from-step-1>` | Step 1 |
| `FEATURE_RAG` | `true` | toggle the flag |
| `INSTALL_RAG_DEPS` | `1` | enable the runtime install |

Save → Render auto-redeploys.

## Step 3 — Watch the boot logs

The first cold start runs `pip install -r requirements-rag.txt` before launching gunicorn, which downloads ~500 MB of CPU wheels. Expect the first deploy to take **3–5 minutes longer than usual**. Subsequent redeploys are instant because Render preserves the pip cache across builds with the same image hash.

You should see in order:

```
Installing RAG deps…
Successfully installed torch-2.4.1 transformers-4.45.2 sentence-transformers-3.1.1 …
INFO  [alembic.runtime.migration] Will assume transactional DDL.
[…] Starting gunicorn 23.0.0
```

## Step 4 — Verify

1. Hit the System Health page: `https://honeywell-frontend.onrender.com/admin/system-health`
2. Confirm:
   - **Vektör DB (Qdrant)** → `ok` ✓
   - **Gömme Modeli** → `loaded` ✓
3. Test a vector-backed feature (e.g., parts semantic search) to confirm the round-trip works end-to-end.

## Step 5 — Bootstrap the collections

The first time Qdrant comes online, the collections are empty. Trigger an indexing run:

```bash
gh workflow run backfill-text-embeddings.yml \
  --ref deploy/render-sandbox \
  -f confirm=APPLY \
  -f sync_shadow_days=180
```

This populates `opportunity_text_embeddings` (V8 BoW) and `opportunity_transformer_seq_embeddings` (V12 sentence-transformers). Qdrant collections (`deals`, `interactions`, `competitors`) auto-create on first write via `_ensure_collection`.

## Disabling RAG (rollback)

To turn it off:

1. Set `FEATURE_RAG=false` in Render → endpoints gated on `_require_rag` start returning 404
2. Set `INSTALL_RAG_DEPS=0` → next redeploy skips the heavyweight install, container shrinks back
3. Optionally delete the Qdrant Cloud cluster to free the quota

The app remains fully functional without RAG — semantic search degrades to substring matching, deal similarity falls back to V7 (cosine + LCS), and `vector_store` calls are short-circuited at the `_get_client` layer.

## Cost estimate (April 2026)

| Component | Free tier | Production |
|---|---|---|
| Qdrant Cloud | 1 GB / 1 cluster | $25/mo per 1 GB after free tier |
| Render Standard plan | n/a | ~$25/mo (vs. $7 Starter) — required for the RAM bump |
| sentence-transformers model download | one-time | one-time |

For the current data footprint, free tier Qdrant + Standard Render is sufficient. Re-evaluate if the deal corpus grows above ~500 K opportunities.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `qdrant: error` after step 4 | `QDRANT_URL` typo or API key missing | Re-copy from Qdrant Cloud overview; ensure no trailing slash |
| `embedding_model: not_loaded` after step 4 | `INSTALL_RAG_DEPS` not set or set to `"0"` | Re-set to `"1"`, redeploy |
| Container OOMs at boot | Render Free tier (512 MB) | Upgrade to Standard |
| `pip install` step times out | First build only — Render pulls ~500 MB | Re-trigger the deploy; second attempt uses cached wheels |
| `403 Forbidden` from Qdrant | API key not passed | Verify `QDRANT_API_KEY` env var is set; check `_get_client` logs for "auth" warnings |
