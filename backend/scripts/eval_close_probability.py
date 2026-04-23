"""Offline calibration/evaluation for heuristic close probability (Sprint 5.6).

Runs against the DB and computes calibration buckets and simple precision metrics
using historical closed deals (closed_won / closed_lost).
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@dataclass(frozen=True)
class BucketRow:
    bucket: str
    n: int
    avg_pred: float
    actual_rate: float


def _bucket_label(p: float, width: float) -> str:
    lo = int((p // width) * (width * 100))
    hi = int(min(100, lo + int(width * 100)))
    return f"{lo:02d}-{hi:02d}%"


async def _run(db: AsyncSession, bucket_width: float, limit: int | None) -> int:
    from app.models.opportunity import Opportunity
    from app.services.predictive_scoring_service import predict_close_probability

    q = select(Opportunity).where(
        and_(
            Opportunity.status == "closed",
            Opportunity.stage.in_(["closed_won", "closed_lost"]),
        )
    )
    if limit:
        q = q.limit(limit)

    opps = (await db.execute(q)).scalars().all()
    if not opps:
        print("No closed opportunities found.")
        return 0

    rows = []
    brier_sum = 0.0
    abs_cal_err_sum = 0.0

    buckets: dict[str, list[tuple[float, int]]] = {}
    for opp in opps:
        pred = await predict_close_probability(db, opp.id)
        p = float(pred.get("close_probability") or 0.0)
        y = 1 if opp.stage == "closed_won" else 0
        brier_sum += (p - y) ** 2

        label = _bucket_label(p, bucket_width)
        buckets.setdefault(label, []).append((p, y))

    for label, pairs in sorted(buckets.items()):
        n = len(pairs)
        avg_pred = sum(p for p, _ in pairs) / n
        actual = sum(y for _, y in pairs) / n
        abs_cal_err_sum += abs(avg_pred - actual) * n
        rows.append(BucketRow(bucket=label, n=n, avg_pred=avg_pred, actual_rate=actual))

    n_total = len(opps)
    brier = brier_sum / n_total
    ece = abs_cal_err_sum / n_total  # expected calibration error (L1)

    # Basic "precision" style metric: for p >= 0.7 how often won?
    hi = [(p, y) for pairs in buckets.values() for (p, y) in pairs if p >= 0.7]
    hi_prec = (sum(y for _, y in hi) / len(hi)) if hi else 0.0

    print("== Close Probability Offline Evaluation ==")
    print(f"timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"deals: {n_total}")
    print(f"bucket_width: {bucket_width}")
    print(f"brier_score: {brier:.4f} (lower is better)")
    print(f"ece_l1: {ece:.4f} (lower is better)")
    print(f"precision@0.70: {hi_prec:.3f} (won-rate among p>=0.70, n={len(hi)})")
    print()
    print("bucket,n,avg_pred,actual_rate")
    for r in rows:
        print(f"{r.bucket},{r.n},{r.avg_pred:.3f},{r.actual_rate:.3f}")

    return 0


async def _amain() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", dest="db_url", required=True, help="SQLAlchemy DB URL")
    parser.add_argument("--bucket-width", type=float, default=0.1, help="Bucket width in [0,1], e.g. 0.1")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of deals (0 = no limit)")
    args = parser.parse_args()

    engine = create_async_engine(args.db_url, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with Session() as db:
            return await _run(db, bucket_width=max(0.01, min(0.5, args.bucket_width)), limit=args.limit or None)
    finally:
        await engine.dispose()


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()

