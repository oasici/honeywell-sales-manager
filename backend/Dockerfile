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

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data/quotes data/uploads data/models data/cache

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Multi-worker via gunicorn + uvicorn workers.
#
# Apply Alembic migrations before forking workers. Render free-tier doesn't
# support preDeployCommand, so this is the cleanest place to keep schema in
# lockstep with code on every deploy. ``alembic upgrade head`` is a no-op
# when the DB is already at head, so a redeploy without schema changes
# costs ~1s. Failures (DB unreachable, conflicting revision) abort the
# container start instead of letting the API serve against a stale schema.
# WEB_CONCURRENCY controls worker count (default 4).
CMD ["sh", "-c", "alembic upgrade head && gunicorn app.main:app -w ${WEB_CONCURRENCY:-4} -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --timeout 120 --graceful-timeout 30 --access-logfile -"]
