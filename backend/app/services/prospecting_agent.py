"""Sprint 4 — ProspectingAgent (MVP facade over rule-based scoring).

Exposes a single entrypoint for pipeline prospecting so jobs and APIs can
depend on a stable module name while implementation stays in HighIntentService.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.high_intent_service import HighIntentRow, HighIntentService


class ProspectingAgent:
    """Rule-based high-intent discovery (no LLM required for MVP)."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._engine = HighIntentService(db)

    async def list_high_intent_accounts(self, user: User, *, limit: int = 50) -> list[HighIntentRow]:
        return await self._engine.list_high_intent(user, limit=limit)
