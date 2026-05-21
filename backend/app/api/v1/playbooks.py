"""Playbook API — CRUD + execution management for rule-based automation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.models.playbook import PlaybookExecution
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.playbook_service import PlaybookService
from app.schemas.common import ItemsResponse, MessageResponse, PaginatedResponse
from app.schemas.playbook import PlaybookResponse
from app.schemas.round16_aggregates import PlaybookAnalyticsResponse

router = APIRouter(prefix="/playbooks", tags=["Playbooks"])


def _require_cockpit():
    """Dependency: reject if FEATURE_REVENUE_COCKPIT is off."""
    if not settings.FEATURE_REVENUE_COCKPIT:
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic Schemas ──


class PlaybookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    trigger_conditions_json: str = "[]"
    steps_json: str = "[]"
    category: str = "general"


class PlaybookUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    trigger_conditions_json: str | None = None
    steps_json: str | None = None
    category: str | None = None
    is_active: bool | None = None


# ── Seed playbook templates ──

SEED_TEMPLATES = [
    {
        "name": "Temas Edilmeyen Firsat",
        "description": "5 gundur temas edilmeyen firsatlar icin otomatik gorev olusturur",
        "trigger_conditions_json": '[{"field": "signal_type", "op": "eq", "value": "no_touch"}, {"field": "severity", "op": "gte", "value": "high"}]',
        "steps_json": '[{"step": 1, "action_type": "task", "template": "Musteriyi ara ve durumu ogren", "delay_days": 0, "priority": "high"}, {"step": 2, "action_type": "notification", "template": "Firsat hala temas edilmemis — yoneticiye bildir", "delay_days": 2}]',
        "category": "retention",
    },
    {
        "name": "Yuksek Riskli Firsat Kurtarma",
        "description": "Churn riski yuksek firsatlar icin acil aksiyon plani",
        "trigger_conditions_json": '[{"field": "signal_type", "op": "eq", "value": "churn_risk"}, {"field": "severity", "op": "gte", "value": "high"}]',
        "steps_json": '[{"step": 1, "action_type": "task", "template": "Acil musteri gorusmesi planla", "delay_days": 0, "priority": "urgent"}, {"step": 2, "action_type": "task", "template": "Ozel teklif hazirla", "delay_days": 1, "priority": "high"}, {"step": 3, "action_type": "notification", "template": "Kurtarma plani ilerleme raporu", "delay_days": 3}]',
        "category": "retention",
    },
    {
        "name": "Cross-Sell Firsati Takibi",
        "description": "Cross-sell sinyali alinan musterilere urun onerisi gorev zinciri",
        "trigger_conditions_json": '[{"field": "signal_type", "op": "eq", "value": "cross_sell_opportunity"}]',
        "steps_json": '[{"step": 1, "action_type": "task", "template": "Musteri ihtiyac analizi yap", "delay_days": 0, "priority": "normal"}, {"step": 2, "action_type": "task", "template": "Ilgili urun teklifi hazirla", "delay_days": 2, "priority": "normal"}]',
        "category": "growth",
    },
    {
        "name": "Teklif Takip Otomasyonu",
        "description": "Duran teklifler icin hatirlatma ve takip gorevleri",
        "trigger_conditions_json": '[{"field": "signal_type", "op": "eq", "value": "quote_stalled"}]',
        "steps_json": '[{"step": 1, "action_type": "task", "template": "Musteriye teklif durumunu sor", "delay_days": 0, "priority": "normal"}, {"step": 2, "action_type": "task", "template": "Revize teklif hazirla", "delay_days": 3, "priority": "high"}, {"step": 3, "action_type": "notification", "template": "Teklif hala yanit bekliyor — eskalasyon gerekebilir", "delay_days": 5}]',
        "category": "pipeline",
    },
]


# ── Endpoints ──


@router.get("/", response_model=PaginatedResponse[PlaybookResponse])
async def list_playbooks(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """List all playbooks (manager only)."""
    service = PlaybookService(db)
    playbooks = await service.list_playbooks()
    total = len(playbooks)
    # Round-12 R12-API-1 — canonical pagination envelope.
    return {
        "items": playbooks,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
    }


@router.post("/", status_code=201, response_model=PlaybookResponse)
async def create_playbook(
    body: PlaybookCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Create a new playbook (manager only)."""
    service = PlaybookService(db)
    playbook = await service.create_playbook(
        # Round-10 R10-DB-3 — tenant_id NOT NULL; bind to the creator.
        tenant_id=current_user.tenant_id,
        name=body.name,
        description=body.description,
        trigger_conditions_json=body.trigger_conditions_json,
        steps_json=body.steps_json,
        category=body.category,
        created_by=current_user.id,
    )
    return {
        "message": "Playbook olusturuldu",
        "id": playbook.id,
        "name": playbook.name,
    }


@router.get("/analytics", response_model=PlaybookAnalyticsResponse)
async def playbook_analytics(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Playbook analytics: completion rates, avg time, effectiveness, most triggered."""
    # Completion rates per playbook
    from app.models.playbook import Playbook

    stats_result = await db.execute(
        select(
            PlaybookExecution.playbook_id,
            func.count(PlaybookExecution.id).label("total"),
            func.count(
                PlaybookExecution.id
            ).filter(PlaybookExecution.status == "completed").label("completed"),
            func.count(
                PlaybookExecution.id
            ).filter(PlaybookExecution.status == "cancelled").label("cancelled"),
        ).group_by(PlaybookExecution.playbook_id)
    )
    stats_rows = stats_result.all()

    # Playbook name lookup
    pb_result = await db.execute(select(Playbook))
    playbooks = {p.id: p.name for p in pb_result.scalars().all()}

    per_playbook = []
    total_completed = 0
    total_all = 0

    for row in stats_rows:
        playbook_id = row[0]
        total = row[1]
        completed = row[2]
        cancelled = row[3]
        finished = completed + cancelled
        completion_rate = round(completed / finished * 100, 1) if finished > 0 else 0

        total_completed += completed
        total_all += total

        per_playbook.append({
            "playbook_id": playbook_id,
            # Round-4 R4-TS-1 — TS expects `name` / `executions`;
            # the prior `playbook_name` / `total_executions` keys
            # caused PlaybookAnalyticsPage to render `undefined` in
            # every table cell.
            "name": playbooks.get(playbook_id, "Bilinmiyor"),
            "executions": total,
            "completed": completed,
            "cancelled": cancelled,
            "completion_rate": completion_rate,
        })

    # Sort by total executions descending (most triggered first)
    per_playbook.sort(key=lambda x: x["executions"], reverse=True)

    # Average completion time (days)
    avg_time_result = await db.execute(
        select(
            func.avg(
                func.extract("epoch", PlaybookExecution.completed_at)
                - func.extract("epoch", PlaybookExecution.started_at)
            ) / 86400.0
        ).where(
            PlaybookExecution.status == "completed",
            PlaybookExecution.completed_at.isnot(None),
        )
    )
    avg_days_raw = avg_time_result.scalar()
    avg_completion_days = round(float(avg_days_raw), 1) if avg_days_raw else None

    # Win rate comparison: opps with playbook vs without
    opp_with_playbook = await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.id.in_(
                select(PlaybookExecution.opportunity_id).where(
                    PlaybookExecution.status == "completed"
                )
            ),
            Opportunity.status == "won",
        )
    )
    won_with = opp_with_playbook.scalar() or 0

    opp_with_playbook_total = await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.id.in_(
                select(PlaybookExecution.opportunity_id).where(
                    PlaybookExecution.status == "completed"
                )
            ),
            Opportunity.status.in_(["won", "lost"]),
        )
    )
    total_with = opp_with_playbook_total.scalar() or 0
    win_rate_with_playbook = round(won_with / total_with * 100, 1) if total_with > 0 else None

    opp_without_playbook = await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.id.notin_(
                select(PlaybookExecution.opportunity_id)
            ),
            Opportunity.status == "won",
        )
    )
    won_without = opp_without_playbook.scalar() or 0

    opp_without_total = await db.execute(
        select(func.count(Opportunity.id)).where(
            Opportunity.id.notin_(
                select(PlaybookExecution.opportunity_id)
            ),
            Opportunity.status.in_(["won", "lost"]),
        )
    )
    total_without = opp_without_total.scalar() or 0
    win_rate_without_playbook = round(won_without / total_without * 100, 1) if total_without > 0 else None

    return {
        "total_executions": total_all,
        "total_completed": total_completed,
        "avg_completion_days": avg_completion_days,
        "win_rate_with_playbook": win_rate_with_playbook,
        "win_rate_without_playbook": win_rate_without_playbook,
        "per_playbook": per_playbook,
        # Round-4 R4-TS-1 — TS interface declares this as an array of
        # {playbook_id, name, count}; previously emitted a string,
        # which crashed PlaybookAnalyticsPage on .length / .map.
        "most_triggered": [
            {"playbook_id": p["playbook_id"], "name": p["name"], "count": p["executions"]}
            for p in per_playbook[:5]
        ],
    }


@router.get("/templates", response_model=ItemsResponse)
async def get_templates(
    current_user: User = Depends(get_current_user),
    _flag=Depends(_require_cockpit),
):
    """Get seed playbook template list."""
    return {"items": SEED_TEMPLATES, "total": len(SEED_TEMPLATES)}


@router.get("/executions", response_model=ItemsResponse)
async def list_executions(
    opportunity_id: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """List active playbook executions, optionally filtered by opportunity."""
    service = PlaybookService(db)
    executions = await service.get_active_executions(opportunity_id=opportunity_id)
    return {"items": executions, "total": len(executions)}


@router.get("/{playbook_id}", response_model=PlaybookResponse)
async def get_playbook(
    playbook_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Get playbook detail."""
    service = PlaybookService(db)
    playbook = await service.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook bulunamadi")
    return {
        "id": playbook.id,
        "name": playbook.name,
        "description": playbook.description,
        "trigger_conditions_json": playbook.trigger_conditions_json,
        "steps_json": playbook.steps_json,
        "category": playbook.category,
        "is_active": playbook.is_active,
        "created_by": playbook.created_by,
        "created_at": playbook.created_at.isoformat() if playbook.created_at else None,
    }


@router.put("/{playbook_id}", response_model=PlaybookResponse)
async def update_playbook(
    playbook_id: int,
    body: PlaybookUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Update a playbook (manager only)."""
    service = PlaybookService(db)
    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Guncellenecek alan bulunamadi")

    try:
        playbook = await service.update_playbook(playbook_id, **update_data)
    except ValueError:
        raise HTTPException(status_code=404, detail="Playbook bulunamadi")

    return {"message": "Playbook guncellendi", "id": playbook.id}


@router.delete("/{playbook_id}", response_model=MessageResponse)
async def deactivate_playbook(
    playbook_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Deactivate a playbook (soft delete, manager only)."""
    service = PlaybookService(db)
    is_ok = await service.deactivate_playbook(playbook_id)
    if not is_ok:
        raise HTTPException(status_code=404, detail="Playbook bulunamadi")
    return {"message": "Playbook devre disi birakildi", "id": playbook_id}


@router.post("/executions/{execution_id}/cancel", response_model=MessageResponse)
async def cancel_execution(
    execution_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Cancel an active playbook execution."""
    service = PlaybookService(db)
    is_ok = await service.cancel_execution(execution_id)
    if not is_ok:
        raise HTTPException(status_code=404, detail="Aktif calisma bulunamadi")
    return {"message": "Playbook calismasi iptal edildi", "id": execution_id}
