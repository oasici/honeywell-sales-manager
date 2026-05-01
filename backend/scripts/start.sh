#!/bin/sh
# Container entrypoint.
#
# 1. Apply Alembic migrations (must complete before workers start so the
#    schema is consistent across all of them).
# 2. Launch gunicorn (exec so signal forwarding stays clean for
#    graceful shutdowns).
#
# Note: the previous version of this script kicked off a background
# pip install of torch + sentence-transformers when INSTALL_RAG_DEPS=1.
# That install raced against Render's startup probe and left
# _embedding_model stuck at not_loaded across deploys. The RAG
# dependency is now baked into the Docker image at build time
# (Dockerfile pip install -r requirements-rag.txt + fastembed) so
# this script no longer needs the install dance — the embedding
# model is always importable when the container boots.
#
# WEB_CONCURRENCY=1 in render.yaml pins the worker count to a single
# uvicorn worker so the embedding model fits in Render Free tier's
# 512 MB RAM ceiling. Bump it on Standard plan if traffic warrants.

set -e

echo "[start] Applying Alembic migrations…"
alembic upgrade head

echo "[start] Launching gunicorn…"
exec gunicorn app.main:app \
  -w "${WEB_CONCURRENCY:-1}" \
  -k uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout 120 \
  --graceful-timeout 30 \
  --access-logfile -
