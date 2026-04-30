#!/bin/sh
# Container entrypoint.
#
# 1. Apply Alembic migrations (must complete before workers start so the
#    schema is consistent across all of them).
# 2. If FEATURE_RAG is requested via INSTALL_RAG_DEPS=1, kick off the
#    heavyweight pip install in the background so gunicorn can bind
#    the port immediately. Render's startup probe expects the service
#    to be listening within ~90 s; a foreground 3-5 min pip install
#    blew past that limit and the container was killed before
#    gunicorn ever got to start. Backgrounding decouples the two —
#    the API serves normally throughout, RAG-gated endpoints
#    transparently start working once the install completes.
# 3. Launch gunicorn (exec so signal forwarding stays clean for
#    graceful shutdowns).
#
# A marker file at ``$HOME/.rag_deps_installed`` is touched after a
# successful install so subsequent container restarts (e.g. Render
# health-check restart) skip the install entirely.

set -e

RAG_MARKER="${HOME}/.rag_deps_installed"

if [ "${INSTALL_RAG_DEPS:-0}" = "1" ]; then
  if [ -f "${RAG_MARKER}" ]; then
    echo "[start] RAG deps marker found at ${RAG_MARKER} — skipping install"
  else
    echo "[start] Installing RAG deps in background (logs: /tmp/rag-install.log)…"
    (
      pip install --user \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        -r /app/requirements-rag.txt > /tmp/rag-install.log 2>&1 \
        && touch "${RAG_MARKER}" \
        && echo "[start] RAG deps installed; embedding model will load on first use"
    ) &
  fi
else
  echo "[start] INSTALL_RAG_DEPS not set — running without RAG dependencies"
fi

echo "[start] Applying Alembic migrations…"
alembic upgrade head

echo "[start] Launching gunicorn…"
exec gunicorn app.main:app \
  -w "${WEB_CONCURRENCY:-4}" \
  -k uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout 120 \
  --graceful-timeout 30 \
  --access-logfile -
