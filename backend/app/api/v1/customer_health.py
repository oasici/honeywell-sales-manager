"""Musteri saglik skoru API endpointleri."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.user import User
from app.services.customer_health_service import CustomerHealthService

router = APIRouter(prefix="/customers/health", tags=["Customer Health"])


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
        "customer_id": report.customer_id,
        "customer_name": report.customer_name,
        "company": report.company,
        "score": report.score,
        "risk_level": report.risk_level,
        "indicators": [_indicator_to_dict(i) for i in report.indicators],
        "recommendations": report.recommendations,
    }


@router.get("/overview")
async def get_health_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tum musterilerin saglik skoru ozeti."""
    service = CustomerHealthService(db)
    reports = await service.get_all_health_scores()

    healthy_count = sum(1 for r in reports if r.risk_level == "healthy")
    at_risk_count = sum(1 for r in reports if r.risk_level == "at_risk")
    churning_count = sum(1 for r in reports if r.risk_level == "churning")
    avg_score = round(
        sum(r.score for r in reports) / len(reports), 1
    ) if reports else 0

    return {
        "summary": {
            "total_customers": len(reports),
            "healthy_count": healthy_count,
            "at_risk_count": at_risk_count,
            "churning_count": churning_count,
            "average_score": avg_score,
        },
        "customers": [_report_to_dict(r) for r in reports],
    }


@router.get("/at-risk")
async def get_at_risk_customers(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Risk altindaki musteri listesi."""
    import logging
    try:
        service = CustomerHealthService(db)
        reports = await service.get_at_risk_customers(limit=limit)
        return {
            "count": len(reports),
            "customers": [_report_to_dict(r) for r in reports],
        }
    except Exception as exc:
        logging.getLogger(__name__).error("At-risk customers failed: %s", exc)
        return {"count": 0, "customers": []}


@router.get("/{customer_id}")
async def get_customer_health(
    customer_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tek bir musterinin saglik raporu."""
    service = CustomerHealthService(db)
    report = await service.calculate_health_score(customer_id)

    if not report:
        raise NotFoundException(f"Musteri bulunamadi: {customer_id}")

    return _report_to_dict(report)
