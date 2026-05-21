"""Deal health scoring endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.user import User
from app.schemas.round16_aggregates import (
    DealHealthAtRiskResponse,
    DealHealthOverviewResponse,
    DealHealthReportRow,
)
from app.services.deal_health_service import DealHealthService

router = APIRouter(prefix="/deal-health", tags=["Deal Health"])


def _check_feature_flag() -> None:
    if not settings.FEATURE_DEAL_HEALTH:
        raise HTTPException(
            status_code=403,
            detail="Deal health ozelligi aktif degil.",
        )


def _indicator_to_dict(indicator) -> dict:
    return {
        "name": indicator.name,
        "label": indicator.label,
        "score": round(indicator.score, 1),
        "weight": indicator.weight,
        "raw_value": indicator.raw_value,
        "description": indicator.description,
    }


def _report_to_dict(report) -> dict:
    return {
        "opportunity_id": report.opportunity_id,
        "title": report.title,
        "score": report.score,
        "risk_level": report.risk_level,
        "indicators": [_indicator_to_dict(i) for i in report.indicators],
        "recommendations": report.recommendations,
    }


@router.get("/{opportunity_id}", response_model=DealHealthReportRow)
async def get_deal_health(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tek bir firsatin saglik raporu."""
    _check_feature_flag()

    service = DealHealthService(db)
    report = await service.compute_deal_health(opportunity_id)

    if report is None:
        raise NotFoundException(f"Firsat bulunamadi: {opportunity_id}")

    return _report_to_dict(report)


@router.get("/overview/all", response_model=DealHealthOverviewResponse)
async def get_deal_health_overview(
    owner_id: int | None = Query(None, description="Sahip ID ile filtrele"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tum aktif firsatlarin saglik skorlari."""
    _check_feature_flag()

    service = DealHealthService(db)
    reports = await service.get_all_deal_health(owner_id=owner_id)

    healthy_count = sum(1 for r in reports if r.risk_level == "healthy")
    at_risk_count = sum(1 for r in reports if r.risk_level == "at_risk")
    critical_count = sum(1 for r in reports if r.risk_level == "critical")
    avg_score = round(
        sum(r.score for r in reports) / len(reports), 1
    ) if reports else 0

    return {
        "summary": {
            "total_opportunities": len(reports),
            "healthy_count": healthy_count,
            "at_risk_count": at_risk_count,
            "critical_count": critical_count,
            "average_score": avg_score,
        },
        "opportunities": [_report_to_dict(r) for r in reports],
    }


@router.get("/at-risk/list", response_model=DealHealthAtRiskResponse)
async def get_at_risk_deals(
    threshold: int = Query(40, ge=0, le=100, description="Saglik skoru esik degeri"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Esik degerinin altindaki firsatlar."""
    _check_feature_flag()

    service = DealHealthService(db)
    reports = await service.get_at_risk(threshold=threshold)

    return {
        "threshold": threshold,
        "count": len(reports),
        "opportunities": [_report_to_dict(r) for r in reports],
    }
