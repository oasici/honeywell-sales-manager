"""Agentic SDR API — manual trigger + decision log."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.enums import UserRole
from app.models.user import User
from app.services.agentic_sdr import run_for_opportunity

router = APIRouter(prefix="/agentic", tags=["Agentic SDR"])


def _require_flag() -> None:
    if not settings.FEATURE_AGENTIC_SDR:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agentic SDR disabled"
        )


class TriggerRequest(BaseModel):
    opportunity_id: int
    trigger: str = "manual"
    trigger_payload: dict[str, Any] | None = None


class TriggerResult(BaseModel):
    tool: str
    arguments: dict[str, Any]
    persisted_ids: dict[str, Any]
    trust_audit: dict[str, Any] | None = None


@router.post("/sdr/run", response_model=TriggerResult | None)
async def run_agent(
    body: TriggerRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.SALES_REP, UserRole.OPERATIONS))],
    db: AsyncSession = Depends(get_db),
) -> TriggerResult | None:
    """Manually invoke the agent for an opportunity (dry-run / demo support)."""
    _require_flag()
    decision = await run_for_opportunity(
        db,
        opportunity_id=body.opportunity_id,
        trigger=body.trigger,
        trigger_payload=body.trigger_payload,
    )
    await db.commit()
    if decision is None:
        return None
    return TriggerResult(
        tool=decision.tool,
        arguments=decision.arguments,
        persisted_ids=decision.persisted_ids,
        trust_audit=decision.trust_audit,
    )
