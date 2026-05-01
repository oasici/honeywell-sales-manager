FROM python:3.11-slim

# System dependencies for WeasyPrint
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libcairo2 \
    libgirepository1.0-dev \
    gir1.2-pango-1.0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-rag.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Bake the RAG dependency (fastembed, ~5 MB wheel + ~120 MB
# quantized model on first use) at build time. Switched from a
# runtime install to build-time install on 2026-05-03 because the
# previous start.sh background install raced against Render's
# startup probe and left _embedding_model stuck at not_loaded
# (round-3 audit follow-up).
RUN pip install --no-cache-dir -r requirements-rag.txt

COPY . .

RUN mkdir -p data/quotes data/uploads data/models data/cache

# Make the start script executable BEFORE switching user so the
# permission carries through to runtime.
RUN chmod +x /app/scripts/start.sh

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# All startup logic lives in scripts/start.sh:
#   - applies Alembic migrations
#   - backgrounds the optional RAG-deps pip install (so gunicorn can
#     bind the port immediately and Render's startup probe passes)
#   - launches gunicorn
#
# Splitting the script out keeps the Dockerfile readable and makes the
# bootstrap reproducible from a shell when debugging locally.
CMD ["/app/scripts/start.sh"]
