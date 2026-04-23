from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


_FALLBACK_STAGE_PROBABILITIES: dict[str, float] = {
    "prospecting": 0.10,
    "qualified": 0.25,
    "proposal": 0.50,
    "negotiation": 0.70,
    "closed_won": 1.00,
    "closed_lost": 0.00,
}


async def get_stage_probabilities(db: AsyncSession) -> dict[str, float]:
    """Single source of truth for stage probabilities (0..1)."""
    try:
        # Reuse existing StageConfig loader + cache (used by ForecastService).
        from app.services.forecast_service import _get_stage_probabilities

        probs = await _get_stage_probabilities(db)
        return probs or dict(_FALLBACK_STAGE_PROBABILITIES)
    except Exception:
        return dict(_FALLBACK_STAGE_PROBABILITIES)


async def get_stage_probability(db: AsyncSession, stage: str) -> float:
    probs = await get_stage_probabilities(db)
    return float(probs.get(stage, _FALLBACK_STAGE_PROBABILITIES.get(stage, 0.25)))


async def get_stage_probability_pct(db: AsyncSession, stage: str) -> int:
    p = await get_stage_probability(db, stage)
    return int(round(max(0.0, min(1.0, p)) * 100))

