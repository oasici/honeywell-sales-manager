from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.decision_gap import DecisionGap, StakeholderRole
from app.models.opportunity import Opportunity
from app.models.sequence_v2 import Stakeholder


@dataclass(frozen=True)
class GapResult:
    opportunity_id: int
    gap_type: str
    severity: str
    recommended_actions: list[str]
    expected_roles: list[str]
    observed_roles: list[str]
    drivers: list[dict]


DEFAULT_EXPECTED_ROLES_BY_STAGE: dict[str, list[str]] = {
    "prospecting": ["champion", "technical"],
    "qualified": ["champion", "technical", "economic"],
    "proposal": ["champion", "technical", "economic", "procurement"],
    "negotiation": ["champion", "technical", "economic", "procurement", "legal"],
}


def _map_to_role_key(s: Stakeholder) -> str | None:
    """Best-effort mapping from V1 stakeholder fields to normalized role keys."""
    # direct buyer_role mapping
    if s.buyer_role == "champion":
        return "champion"
    if s.buyer_role == "decision_maker":
        return "economic"
    if s.department_group == "tech":
        return "technical"
    if s.department_group == "legal":
        return "legal"
    if s.department_group == "finance":
        return "procurement"
    return None


def _severity_for_missing(role_key: str) -> str:
    return {
        "economic": "high",
        "champion": "high",
        "technical": "med",
        "procurement": "med",
        "legal": "low",
    }.get(role_key, "med")


async def rebuild_decision_gaps_for_opportunity(db: AsyncSession, *, opportunity_id: int) -> list[GapResult]:
    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if not opp:
        return []

    stage = str(opp.stage or "prospecting")
    expected_roles = DEFAULT_EXPECTED_ROLES_BY_STAGE.get(stage, ["champion", "technical"])

    stakeholders = (
        await db.execute(select(Stakeholder).where(Stakeholder.opportunity_id == opportunity_id))
    ).scalars().all()

    observed: set[str] = set()
    role_rows: list[StakeholderRole] = []
    for s in stakeholders:
        rk = _map_to_role_key(s)
        if rk:
            observed.add(rk)
            role_rows.append(
                StakeholderRole(
                    opportunity_id=opportunity_id,
                    stakeholder_id=int(s.id),
                    role_key=rk,
                    confidence=70,
                    source="rule",
                    created_at=datetime.now(timezone.utc),
                )
            )

    # overwrite stakeholder_roles for this opportunity
    await db.execute(sa.delete(StakeholderRole).where(StakeholderRole.opportunity_id == opportunity_id))
    if role_rows:
        db.add_all(role_rows)
        await db.flush()

    results: list[GapResult] = []

    # Gap 1: single-threaded risk
    if len(stakeholders) < 3:
        results.append(
            GapResult(
                opportunity_id=opportunity_id,
                gap_type="single_threaded_risk",
                severity="high" if len(stakeholders) <= 1 else "med",
                recommended_actions=["En az 2 yeni paydaş ekle (ekonomik + teknik)"],
                expected_roles=expected_roles,
                observed_roles=sorted(observed),
                drivers=[{"label": "Stakeholder sayısı düşük", "value": len(stakeholders), "impact": -10}],
            )
        )

    # Missing expected roles
    for role_key in expected_roles:
        if role_key not in observed:
            results.append(
                GapResult(
                    opportunity_id=opportunity_id,
                    gap_type=f"missing_{role_key}",
                    severity=_severity_for_missing(role_key),
                    recommended_actions=[f"{role_key} rolünde bir paydaş belirle ve ilişki kur"],
                    expected_roles=expected_roles,
                    observed_roles=sorted(observed),
                    drivers=[{"label": "Beklenen rol eksik", "value": role_key, "impact": -8}],
                )
            )

    # overwrite decision_gaps for this opportunity
    await db.execute(sa.delete(DecisionGap).where(DecisionGap.opportunity_id == opportunity_id))
    now = datetime.now(timezone.utc)
    # Round-15 Sprint 15m cohort 3 — DecisionGap.tenant_id NOT NULL.
    # Inherit from the loaded opportunity (cohort 1 guarantees it's set).
    derived_tenant_id = opp.tenant_id
    gap_rows = [
        DecisionGap(
            tenant_id=derived_tenant_id,
            opportunity_id=opportunity_id,
            gap_type=r.gap_type,
            severity=r.severity,
            is_resolved=False,
            expected_roles_json=json.dumps(r.expected_roles, ensure_ascii=False),
            observed_roles_json=json.dumps(r.observed_roles, ensure_ascii=False),
            recommended_actions_json=json.dumps(r.recommended_actions, ensure_ascii=False),
            drivers_json=json.dumps(r.drivers, ensure_ascii=False),
            created_at=now,
        )
        for r in results
    ]
    if gap_rows:
        db.add_all(gap_rows)
        await db.flush()

    return results


async def rebuild_decision_gaps_nightly(db: AsyncSession, *, owner_id: int | None = None) -> int:
    """Nightly job: recompute gaps for active opportunities (optionally scoped)."""
    conditions = [Opportunity.status == "active"]
    if owner_id is not None:
        conditions.append(Opportunity.owner_id == owner_id)

    opp_ids = (
        await db.execute(select(Opportunity.id).where(sa.and_(*conditions)))
    ).scalars().all()
    count = 0
    for oid in opp_ids:
        await rebuild_decision_gaps_for_opportunity(db, opportunity_id=int(oid))
        count += 1
    return count

