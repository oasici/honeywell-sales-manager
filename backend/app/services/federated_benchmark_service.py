"""Federated benchmark service (V6).

Cross-tenant benchmark publishing with built-in privacy guards.
Single-tenant deployments today never call this — but laying the
table + suppression rules now means we won't need a panic-mode
retrofit when we go multi-tenant.

Privacy guards:

- ``MIN_SAMPLE_SIZE`` (default 10) — fewer than N records → suppress.
- ``MIN_TENANT_COUNT`` (default 3) — fewer than M distinct tenants
  contributing → suppress (k-anonymity floor).
- ``suppressed=TRUE`` rows still get written so the dashboard can
  render "n/a — sample too small" without leaking the row count.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v6_federated import FederatedBenchmark

logger = logging.getLogger(__name__)


MIN_SAMPLE_SIZE = 10
MIN_TENANT_COUNT = 3


async def publish_benchmark(
    db: AsyncSession,
    *,
    benchmark_key: str,
    metric_name: str,
    metric_value: float,
    sample_size: int,
    tenant_count: int,
    snapshot_date: date | None = None,
    sample_bucket: str | None = None,
) -> FederatedBenchmark:
    """Idempotent upsert for a federated benchmark row.

    Below-threshold inputs land with ``suppressed=TRUE`` and
    ``metric_value=None`` so the dashboard can show the suppression
    reason instead of leaking the underlying value.
    """
    snap = snapshot_date or datetime.now(timezone.utc).date()

    suppressed = sample_size < MIN_SAMPLE_SIZE or tenant_count < MIN_TENANT_COUNT
    safe_value = None if suppressed else metric_value

    existing = (
        await db.execute(
            select(FederatedBenchmark)
            .where(FederatedBenchmark.benchmark_key == benchmark_key)
            .where(FederatedBenchmark.snapshot_date == snap)
            .where(FederatedBenchmark.metric_name == metric_name)
            .where(FederatedBenchmark.sample_bucket == sample_bucket)
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = FederatedBenchmark(
            benchmark_key=benchmark_key,
            snapshot_date=snap,
            metric_name=metric_name,
            metric_value=safe_value,
            sample_bucket=sample_bucket,
            tenant_count=tenant_count,
            sample_size=sample_size,
            suppressed=suppressed,
        )
        db.add(existing)
    else:
        existing.metric_value = safe_value
        existing.tenant_count = tenant_count
        existing.sample_size = sample_size
        existing.suppressed = suppressed

    await db.flush()
    return existing


async def list_published(
    db: AsyncSession,
    *,
    benchmark_key: str,
    include_suppressed: bool = False,
    limit: int = 50,
) -> list[FederatedBenchmark]:
    stmt = (
        select(FederatedBenchmark)
        .where(FederatedBenchmark.benchmark_key == benchmark_key)
        .order_by(FederatedBenchmark.snapshot_date.desc())
        .limit(limit)
    )
    if not include_suppressed:
        stmt = stmt.where(FederatedBenchmark.suppressed.is_(False))
    return list((await db.execute(stmt)).scalars())
