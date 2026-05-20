"""Musteri saglik skoru API endpointleri."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.user import User
from app.services.customer_health_service import CustomerHealthService
from app.schemas.common import PaginatedResponse
from app.schemas.customer_health import CustomerHealthReportResponse

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


def _report_to_dict(report, include_explanations: bool = False) -> dict:
    data = {
        "customer_id": report.customer_id,
        "customer_name": report.customer_name,
        "company": report.company,
        "score": report.score,
        "risk_level": report.risk_level,
        "indicators": [_indicator_to_dict(i) for i in report.indicators],
        "recommendations": report.recommendations,
    }
    if include_explanations:
        total_weight = sum(i.weight for i in report.indicators) or 1
        data["explanations"] = [
            {
                "indicator": i.name,
                "label": i.label,
                "value": i.raw_value,
                "weight": i.weight,
                "contribution": round(i.score * i.weight / total_weight, 1),
                "recommendation": next(
                    (r for r in report.recommendations if i.label.lower() in r.lower()),
                    None,
                ),
            }
            for i in report.indicators
        ]
    return data


@router.get(
    "/overview",
    response_model=PaginatedResponse[CustomerHealthReportResponse],
)
async def get_health_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tum musterilerin saglik skoru ozeti.

    N15-AUTH-4 (Round-15) — scope to ``current_user.tenant_id`` so the
    overview never leaks foreign-tenant customers.
    """
    service = CustomerHealthService(db)
    reports = await service.get_all_health_scores(tenant_id=current_user.tenant_id)

    healthy_count = sum(1 for r in reports if r.risk_level == "healthy")
    at_risk_count = sum(1 for r in reports if r.risk_level == "at_risk")
    churning_count = sum(1 for r in reports if r.risk_level == "churning")
    avg_score = round(
        sum(r.score for r in reports) / len(reports), 1
    ) if reports else 0

    items = [_report_to_dict(r) for r in reports]
    total = len(items)
    summary = {
        "total_customers": total,
        "healthy_count": healthy_count,
        "at_risk_count": at_risk_count,
        "churning_count": churning_count,
        "average_score": avg_score,
    }
    # R7-API-4 — canonical pagination envelope (CLAUDE.md ban on
    # ``{breaches: [], count: N}``-style envelopes applies here).
    # ``customers`` and ``summary`` aliases are kept for the SPA.
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
        # Backwards-compatible keys for SPA consumers mid-migration.
        "summary": summary,
        "customers": items,
    }


@router.get(
    "/at-risk",
    response_model=PaginatedResponse[CustomerHealthReportResponse],
)
async def get_at_risk_customers(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Risk altindaki musteri listesi.

    N15-AUTH-4 — scope to ``current_user.tenant_id``.
    """
    import logging
    try:
        service = CustomerHealthService(db)
        reports = await service.get_at_risk_customers(
            limit=limit, tenant_id=current_user.tenant_id,
        )
        items = [_report_to_dict(r) for r in reports]
        total = len(items)
        # R7-API-4 — canonical pagination envelope. ``count``/``customers``
        # kept as legacy aliases for in-flight SPA consumers.
        return {
            "items": items,
            "total": total,
            "page": 1,
            "page_size": total,
            "pages": 1 if total > 0 else 0,
            "count": total,
            "customers": items,
        }
    except Exception as exc:
        logging.getLogger(__name__).error("At-risk customers failed: %s", exc)
        return {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 0,
            "pages": 0,
            "count": 0,
            "customers": [],
        }


@router.get("/{customer_id}", response_model=CustomerHealthReportResponse)
async def get_customer_health(
    customer_id: int,
    explain: bool = Query(False, description="Include score explanations"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tek bir musterinin saglik raporu. ?explain=true ile skor aciklamalari eklenir.

    N15-AUTH-4 — cross-tenant lookups collapse to 404 (CLAUDE.md convention).
    """
    service = CustomerHealthService(db)
    report = await service.calculate_health_score(
        customer_id, tenant_id=current_user.tenant_id,
    )

    if not report:
        raise NotFoundException(f"Musteri bulunamadi: {customer_id}")

    return _report_to_dict(report, include_explanations=explain)
