"""Stage validation service — checks if opportunity meets requirements for target stage."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stage_requirement import StageRequirement

logger = logging.getLogger(__name__)


async def validate_stage_transition(
    db: AsyncSession,
    opportunity: object,
    target_stage: str,
) -> dict:
    """Check if opportunity meets requirements for target stage.

    Returns {"valid": bool, "errors": [], "tips": []}.
    Does not block — caller decides whether to warn or reject.
    """
    result = await db.execute(
        select(StageRequirement).where(
            StageRequirement.stage == target_stage,
            StageRequirement.is_active.is_(True),
        )
    )
    requirement = result.scalar_one_or_none()

    if not requirement:
        return {"valid": True, "errors": [], "tips": []}

    errors: list[str] = []
    tips: list[str] = []

    # Check required fields
    required_fields = json.loads(requirement.required_fields_json)
    for field_name in required_fields:
        value = getattr(opportunity, field_name, None)
        if value is None:
            errors.append(
                f"'{field_name}' alani {target_stage} asamasi icin zorunludur"
            )

    # Check validation rules
    if requirement.validation_rules_json:
        validation_rules = json.loads(requirement.validation_rules_json)
        for rule_def in validation_rules:
            rule_type = rule_def.get("rule")
            message = rule_def.get("message", f"Dogrulama hatasi: {rule_type}")

            if rule_type == "has_quote":
                is_valid = await _check_has_quote(db, opportunity.id)
                if not is_valid:
                    errors.append(message)

    # Load coaching tips
    if requirement.coaching_tips_json:
        tips = json.loads(requirement.coaching_tips_json)

    is_valid = len(errors) == 0
    return {"valid": is_valid, "errors": errors, "tips": tips}


STAGE_ORDER = {
    "prospecting": 1,
    "qualified": 2,
    "proposal": 3,
    "negotiation": 4,
    "closed_won": 5,
    "closed_lost": 6,
}

STAGE_LABELS = {
    "prospecting": "Arastirma",
    "qualified": "Nitelenmis",
    "proposal": "Teklif",
    "negotiation": "Muzakere",
    "closed_won": "Kazanildi",
    "closed_lost": "Kaybedildi",
}

# Default required fields when no StageRequirement row exists
DEFAULT_REQUIRED_FIELDS: dict[str, list[str]] = {
    "prospecting": ["title", "customer_id"],
    "qualified": ["title", "customer_id", "amount"],
    "proposal": ["title", "customer_id", "amount", "close_date"],
    "negotiation": ["title", "customer_id", "amount", "close_date"],
    "closed_won": ["title", "customer_id", "amount", "close_date"],
    "closed_lost": ["title", "customer_id"],
}

FIELD_LABELS: dict[str, str] = {
    "title": "Baslik",
    "customer_id": "Musteri",
    "amount": "Tutar",
    "close_date": "Kapanma Tarihi",
    "currency": "Para Birimi",
    "owner_id": "Sahip",
    "probability": "Olasilik",
    "loss_reason": "Kayip Nedeni",
    "forecast_category": "Tahmin Kategorisi",
}


async def get_all_stage_status(
    db: AsyncSession,
    opportunity: object,
) -> list[dict]:
    """Build completion status for every stage relative to the given opportunity."""
    result = await db.execute(
        select(StageRequirement).where(StageRequirement.is_active.is_(True))
    )
    requirements = result.scalars().all()
    req_map: dict[str, StageRequirement] = {r.stage: r for r in requirements}

    current_stage = getattr(opportunity, "stage", "prospecting")
    current_order = STAGE_ORDER.get(current_stage, 1)
    stages_out: list[dict] = []

    for stage_name in STAGE_ORDER:
        order = STAGE_ORDER[stage_name]
        label = STAGE_LABELS.get(stage_name, stage_name)
        is_current = stage_name == current_stage

        # Determine required fields from DB or defaults
        req = req_map.get(stage_name)
        if req:
            raw_fields = json.loads(req.required_fields_json)
        else:
            raw_fields = DEFAULT_REQUIRED_FIELDS.get(stage_name, [])

        # Check completion of each field
        required_fields_status: list[dict] = []
        completed_count = 0
        for field_name in raw_fields:
            value = getattr(opportunity, field_name, None)
            is_completed = value is not None
            if isinstance(value, str) and value.strip() == "":
                is_completed = False
            if is_completed:
                completed_count += 1
            required_fields_status.append({
                "name": field_name,
                "label": FIELD_LABELS.get(field_name, field_name),
                "completed": is_completed,
            })

        total_fields = len(required_fields_status)
        completion_pct = round(
            (completed_count / total_fields) * 100
        ) if total_fields > 0 else 100

        # Coaching tips
        coaching_tips: list[str] = []
        if req and req.coaching_tips_json:
            coaching_tips = json.loads(req.coaching_tips_json)

        stages_out.append({
            "stage": stage_name,
            "label": label,
            "order": order,
            "completion_pct": completion_pct,
            "is_current": is_current,
            "required_fields": required_fields_status,
            "coaching_tips": coaching_tips,
        })

    return stages_out


async def _check_has_quote(db: AsyncSession, opportunity_id: int) -> bool:
    """Check if at least one quote exists for the opportunity."""
    from sqlalchemy import func

    from app.models.quote import Quote

    count_result = await db.execute(
        select(func.count(Quote.id)).where(
            Quote.opportunity_id == opportunity_id
        )
    )
    count = count_result.scalar() or 0
    return count > 0
