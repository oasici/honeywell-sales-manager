"""Sequence Engine v2 — idempotent execution, global exit, telemetry, branching, A/B variants.

Gated by FEATURE_SEQUENCES_V2. When the flag is off, the original
execute_sequence_step logic in job_queue.py continues to work unchanged.

Step schema v2 format (backward-compatible):
  [
    {"step": 1, "action": "email", "delay_days": 0, "template": "...",
     "variants": [
       {"key": "A", "template": "Version A", "split_pct": 50},
       {"key": "B", "template": "Version B", "split_pct": 50}
     ],
     "branch_rules": [
       {"condition": "replied", "goto_step": 4},
       {"condition": "no_engagement", "goto_step": 3}
     ]
    },
    ...
  ]
Old format (step/action/delay_days/template) still works unchanged.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.engagement import Sequence, SequenceEnrollment
from app.models.sequence_v2 import SequenceStepRun

logger = logging.getLogger(__name__)

# ── Exit reason constants ──
EXIT_ALL_STEPS = "all_steps_completed"
EXIT_LEAD_CONVERTED = "lead_converted"
EXIT_OPP_CLOSED = "opp_closed"
EXIT_EMAIL_BOUNCED = "email_bounced"
EXIT_DNC = "dnc"
EXIT_MANUAL = "manual"
EXIT_GLOBAL = "global_exit"


async def check_global_exit(
    db: AsyncSession,
    enrollment: SequenceEnrollment,
) -> str | None:
    """Check global exit conditions for an enrollment.

    Returns the exit_reason string if the enrollment should exit,
    or None if it should continue.
    """
    # 1. Lead converted?
    if enrollment.lead_id:
        from app.models.lead import Lead

        lead = (
            await db.execute(
                select(Lead).where(Lead.id == enrollment.lead_id)
            )
        ).scalar_one_or_none()
        if lead and lead.status == "converted":
            return EXIT_LEAD_CONVERTED

    # 2. Opportunity closed?
    if enrollment.opportunity_id:
        from app.models.opportunity import Opportunity

        opp = (
            await db.execute(
                select(Opportunity).where(Opportunity.id == enrollment.opportunity_id)
            )
        ).scalar_one_or_none()
        if opp and opp.status == "closed":
            return EXIT_OPP_CLOSED

    # 3. Sequence-level exit_criteria_json
    seq = (
        await db.execute(
            select(Sequence).where(Sequence.id == enrollment.sequence_id)
        )
    ).scalar_one_or_none()
    if seq and seq.exit_criteria_json:
        try:
            criteria = json.loads(seq.exit_criteria_json)
            exit_reason = _evaluate_exit_criteria(criteria, enrollment, db)
            if exit_reason:
                return exit_reason
        except (json.JSONDecodeError, TypeError):
            pass

    return None


def _evaluate_exit_criteria(
    criteria: list[dict],
    enrollment: SequenceEnrollment,
    db: AsyncSession,
) -> str | None:
    """Evaluate sequence-level exit criteria (simple field checks)."""
    # For now, criteria is a list of dicts like:
    #   [{"condition": "lead_converted"}, {"condition": "opp_closed"}]
    # These are already handled above, but this allows custom conditions.
    for rule in criteria:
        cond = rule.get("condition", "")
        if cond == "lead_converted" or cond == "opp_closed":
            continue  # Already handled
    return None


# ── Variant bucketing ──

def select_variant(
    variants: list[dict],
    target_id: int,
    step_number: int,
) -> dict | None:
    """Deterministically select a variant for a target using hash bucketing.

    The same (target_id, step_number) always maps to the same variant,
    ensuring sticky assignment across retries.

    Returns the selected variant dict or None if no variants defined.
    """
    if not variants:
        return None

    # Create deterministic hash from target_id + step_number
    key = f"{target_id}:{step_number}"
    hash_val = int(hashlib.md5(key.encode()).hexdigest(), 16)
    bucket = hash_val % 100  # 0-99

    cumulative = 0
    for variant in variants:
        cumulative += variant.get("split_pct", 50)
        if bucket < cumulative:
            return variant

    # Fallback to last variant
    return variants[-1]


def evaluate_branch_rules(
    branch_rules: list[dict],
    step_outcome: str | None,
    steps: list[dict],
) -> int | None:
    """Evaluate branch rules and return the target step number if a rule matches.

    step_outcome: "replied", "opened", "clicked", "bounced", "no_engagement", etc.
    Returns the goto_step number or None to continue normally.
    """
    if not branch_rules or not step_outcome:
        return None

    for rule in branch_rules:
        condition = rule.get("condition", "")
        goto_step = rule.get("goto_step")

        if condition == step_outcome and goto_step is not None:
            # Validate goto_step exists
            if 1 <= goto_step <= len(steps):
                return goto_step

    return None


async def has_step_run(
    db: AsyncSession,
    enrollment_id: int,
    step_number: int,
) -> bool:
    """Check if a step has already been executed (idempotency guard)."""
    existing = (
        await db.execute(
            select(SequenceStepRun.id).where(
                and_(
                    SequenceStepRun.enrollment_id == enrollment_id,
                    SequenceStepRun.step_number == step_number,
                )
            )
        )
    ).scalar_one_or_none()
    return existing is not None


async def record_step_run(
    db: AsyncSession,
    *,
    enrollment_id: int,
    sequence_id: int,
    step_number: int,
    step_action: str,
    variant_key: str | None = None,
    status: str = "completed",
    reason_codes: list[str] | None = None,
    payload_snapshot: dict | None = None,
    started_at: datetime | None = None,
) -> SequenceStepRun:
    """Record a step execution in the telemetry table."""
    now = datetime.now(timezone.utc)
    run = SequenceStepRun(
        enrollment_id=enrollment_id,
        sequence_id=sequence_id,
        step_number=step_number,
        step_action=step_action,
        variant_key=variant_key,
        status=status,
        reason_codes=json.dumps(reason_codes) if reason_codes else None,
        payload_snapshot=json.dumps(payload_snapshot, default=str) if payload_snapshot else None,
        started_at=started_at or now,
        completed_at=now if status in ("completed", "skipped", "failed") else None,
    )
    db.add(run)
    return run


async def exit_enrollment(
    db: AsyncSession,
    enrollment: SequenceEnrollment,
    exit_reason: str,
) -> None:
    """Mark an enrollment as exited with a reason."""
    now = datetime.now(timezone.utc)
    enrollment.status = "exited" if exit_reason != EXIT_ALL_STEPS else "completed"
    enrollment.exit_reason = exit_reason
    enrollment.completed_at = now
    enrollment.next_action_at = None


async def execute_step_v2(
    db: AsyncSession,
    enrollment: SequenceEnrollment,
) -> str:
    """Execute the current step for an enrollment with v2 guarantees.

    Returns a human-readable result string.

    Guarantees:
    1. Idempotent — won't re-execute if StepRun already exists
    2. Global exit — checks exit conditions before executing
    3. Telemetry — writes SequenceStepRun record
    4. Events — emits domain events for downstream consumers
    """
    from app.services.domain_events import DomainEvents, emit_domain_event

    current = enrollment.current_step

    # 1. Global exit check
    exit_reason = await check_global_exit(db, enrollment)
    if exit_reason:
        await exit_enrollment(db, enrollment, exit_reason)
        await _emit_exit_event(db, enrollment, exit_reason)
        return f"Enrollment {enrollment.id} exited: {exit_reason}"

    # 2. Load sequence + steps
    seq = (
        await db.execute(
            select(Sequence).where(Sequence.id == enrollment.sequence_id)
        )
    ).scalar_one_or_none()
    if not seq:
        return f"Sequence not found for enrollment {enrollment.id}"

    steps = json.loads(seq.steps_json) if seq.steps_json else []
    if current > len(steps):
        await exit_enrollment(db, enrollment, EXIT_ALL_STEPS)
        await _emit_completion_event(db, enrollment, len(steps))
        return f"Sequence completed for enrollment {enrollment.id}"

    # 3. Idempotency check
    if await has_step_run(db, enrollment.id, current):
        logger.info(
            "Step %d already executed for enrollment %d — skipping (idempotent)",
            current, enrollment.id,
        )
        # Advance pointer without re-executing
        enrollment.current_step = current + 1
        if enrollment.current_step > len(steps):
            await exit_enrollment(db, enrollment, EXIT_ALL_STEPS)
            await _emit_completion_event(db, enrollment, len(steps))
        else:
            next_delay = steps[current].get("delay_days", 1) if current < len(steps) else 0
            enrollment.next_action_at = datetime.now(timezone.utc) + timedelta(days=next_delay)
        return f"Step {current} already ran for enrollment {enrollment.id} — advanced pointer"

    # 4. Execute step (with variant selection if available)
    step = steps[current - 1]
    action = step.get("action", "task")
    template = step.get("template", "")
    started_at = datetime.now(timezone.utc)

    # Variant selection (A/B testing)
    variant_key: str | None = None
    variants = step.get("variants")
    if variants:
        target_id = enrollment.lead_id or enrollment.opportunity_id or enrollment.customer_id or enrollment.id
        selected_variant = select_variant(variants, target_id, current)
        if selected_variant:
            variant_key = selected_variant.get("key")
            template = selected_variant.get("template", template)

    step_status = "completed"
    reason_codes: list[str] = []

    try:
        if action == "task":
            from app.models.opportunity import Task

            task = Task(
                owner_id=enrollment.enrolled_by or 1,
                opportunity_id=enrollment.opportunity_id,
                title=template or f"Sira adimi {current}",
                source="rule",
                priority="normal",
            )
            db.add(task)
            reason_codes.append("task_created")
        elif action == "email":
            reason_codes.append("email_step_logged")
        elif action == "wait":
            reason_codes.append("wait_completed")
        else:
            reason_codes.append(f"action_{action}")

        if variant_key:
            reason_codes.append(f"variant_{variant_key}")
    except Exception as exc:
        step_status = "failed"
        reason_codes.append(f"error:{exc}")
        logger.error("Step %d execution failed for enrollment %d: %s", current, enrollment.id, exc)

    # 5. Record telemetry
    await record_step_run(
        db,
        enrollment_id=enrollment.id,
        sequence_id=enrollment.sequence_id,
        step_number=current,
        step_action=action,
        variant_key=variant_key,
        status=step_status,
        reason_codes=reason_codes,
        payload_snapshot=step,
        started_at=started_at,
    )

    # 6. Advance enrollment (with branch evaluation)
    branch_rules = step.get("branch_rules")
    next_step = current + 1

    if branch_rules:
        # For now, branch outcome is determined by step action type
        # In full implementation, this would check engagement data
        # (e.g., "did they open the email?"). Here we default to None.
        branch_target = evaluate_branch_rules(branch_rules, None, steps)
        if branch_target:
            next_step = branch_target

    enrollment.current_step = next_step
    if enrollment.current_step > len(steps):
        await exit_enrollment(db, enrollment, EXIT_ALL_STEPS)
        await _emit_completion_event(db, enrollment, len(steps))
    else:
        target_step = steps[next_step - 1] if next_step <= len(steps) else {}
        next_delay = target_step.get("delay_days", 1)
        enrollment.next_action_at = datetime.now(timezone.utc) + timedelta(days=next_delay)

    # 7. Emit step completed event
    await emit_domain_event(
        db,
        DomainEvents.SEQUENCE_STEP_COMPLETED,
        {
            "enrollment_id": enrollment.id,
            "sequence_id": enrollment.sequence_id,
            "step_number": current,
            "step_action": action,
            "variant_key": variant_key,
            "opportunity_id": enrollment.opportunity_id,
            "customer_id": enrollment.customer_id,
            "lead_id": enrollment.lead_id,
        },
        entity_type="sequence_enrollment",
        entity_id=enrollment.id,
        actor_id=enrollment.enrolled_by,
    )

    return f"Step {current} executed for enrollment {enrollment.id}"


async def _emit_completion_event(
    db: AsyncSession,
    enrollment: SequenceEnrollment,
    total_steps: int,
) -> None:
    """Emit sequence.completed event."""
    from app.services.domain_events import DomainEvents, emit_domain_event

    await emit_domain_event(
        db,
        DomainEvents.SEQUENCE_COMPLETED,
        {
            "enrollment_id": enrollment.id,
            "sequence_id": enrollment.sequence_id,
            "exit_reason": EXIT_ALL_STEPS,
            "total_steps": total_steps,
            "opportunity_id": enrollment.opportunity_id,
            "customer_id": enrollment.customer_id,
            "lead_id": enrollment.lead_id,
        },
        entity_type="sequence_enrollment",
        entity_id=enrollment.id,
        actor_id=enrollment.enrolled_by,
    )


async def _emit_exit_event(
    db: AsyncSession,
    enrollment: SequenceEnrollment,
    exit_reason: str,
) -> None:
    """Emit sequence.exited event."""
    from app.services.domain_events import DomainEvents, emit_domain_event

    await emit_domain_event(
        db,
        DomainEvents.SEQUENCE_EXITED,
        {
            "enrollment_id": enrollment.id,
            "sequence_id": enrollment.sequence_id,
            "exit_reason": exit_reason,
            "current_step": enrollment.current_step,
            "opportunity_id": enrollment.opportunity_id,
            "customer_id": enrollment.customer_id,
            "lead_id": enrollment.lead_id,
        },
        entity_type="sequence_enrollment",
        entity_id=enrollment.id,
        actor_id=enrollment.enrolled_by,
    )
