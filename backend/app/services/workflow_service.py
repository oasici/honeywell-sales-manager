from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_rule import WorkflowRule

logger = logging.getLogger(__name__)


class WorkflowService:
    """Evaluate workflow rules against entity events and execute matching actions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate_event(
        self,
        entity_type: str,
        trigger_event: str,
        entity_data: dict,
        *,
        ctx=None,
    ) -> int:
        """Evaluate all active rules for this event and execute matching ones.

        D-013 — caller may pass a ``RuleExecutionContext``; the runtime
        depth + visited guards then catch runaway A→B→A chains. When
        no ctx is supplied (root event from user action), we create a
        fresh one so the guard *always* runs.
        """
        from app.services.workflow_cycle_detector import (
            RuleExecutionContext,
            WorkflowCycleDetected,
            WorkflowDepthExceeded,
        )

        if ctx is None:
            ctx = RuleExecutionContext()

        rules = (
            await self.db.execute(
                select(WorkflowRule).where(
                    WorkflowRule.entity_type == entity_type,
                    WorkflowRule.trigger_event == trigger_event,
                    WorkflowRule.is_active.is_(True),
                )
            )
        ).scalars().all()

        executed = 0
        for rule in rules:
            if not self._match_conditions(rule, entity_data):
                continue
            # D-013 — enter/exit guards. A cycle or depth overflow
            # raises; we log and abort the chain rather than poisoning
            # downstream rules' state.
            try:
                ctx.enter(rule.id)
            except (WorkflowCycleDetected, WorkflowDepthExceeded) as exc:
                logger.warning(
                    "Workflow chain aborted (rule_id=%d, root=%s): %s",
                    rule.id, ctx.root_event_id, exc,
                )
                await self._record_workflow_block(
                    rule, ctx,
                    outcome="blocked_cycle" if isinstance(exc, WorkflowCycleDetected) else "blocked_depth",
                    note=str(exc),
                )
                break
            try:
                await self._execute_actions(rule, entity_data)
                executed += 1
            finally:
                ctx.exit_(rule.id)
        return executed

    async def _record_workflow_block(self, rule, ctx, *, outcome: str, note: str) -> None:
        """Persist a row in workflow_execution_log when a chain is blocked.

        Best-effort: wrapped in a SAVEPOINT so a logging failure
        (table missing on partial deploys, FK constraint, etc.)
        doesn't poison the surrounding transaction.
        """
        from sqlalchemy import text

        try:
            async with self.db.begin_nested():
                await self.db.execute(
                    text(
                        """
                        INSERT INTO workflow_execution_log
                          (tenant_id, root_event_id, rule_id, depth, outcome, note, created_at)
                        VALUES
                          (:tid, :root, :rid, :depth, :outcome, :note, now())
                        """
                    ),
                    {
                        "tid": getattr(rule, "tenant_id", None) or 0,
                        "root": ctx.root_event_id,
                        "rid": rule.id,
                        "depth": ctx.depth,
                        "outcome": outcome,
                        "note": (note or "")[:500],
                    },
                )
        except Exception:
            logger.exception("workflow_execution_log insert failed")

    def _match_conditions(self, rule: WorkflowRule, entity_data: dict) -> bool:
        """Check whether all conditions on a rule match the entity data."""
        if not rule.conditions_json:
            return True

        conditions = json.loads(rule.conditions_json)
        for cond in conditions:
            field = cond.get("field", "")
            op = cond.get("operator", "eq")
            value = cond.get("value", "")
            actual = str(entity_data.get(field, ""))

            if op == "eq" and actual != value:
                return False
            if op == "neq" and actual == value:
                return False
            if op == "contains" and value.lower() not in actual.lower():
                return False
            if op == "gte":
                try:
                    if float(actual) < float(value):
                        return False
                except ValueError:
                    return False
            if op == "lte":
                try:
                    if float(actual) > float(value):
                        return False
                except ValueError:
                    return False
        return True

    async def _execute_actions(
        self, rule: WorkflowRule, entity_data: dict,
    ) -> None:
        """Run all actions defined on a matched rule."""
        actions = json.loads(rule.actions_json)
        for action in actions:
            action_type = action.get("type", "")
            try:
                if action_type == "send_notification":
                    await self._action_send_notification(rule, action, entity_data)
                elif action_type == "create_task":
                    await self._action_create_task(rule, action, entity_data)
                elif action_type == "field_update":
                    logger.info("Field update action: %s", action)
                elif action_type == "emit_signal":
                    await self._action_emit_signal(rule, action, entity_data)
                elif action_type == "enroll_sequence":
                    await self._action_enroll_sequence(action, entity_data)
                elif action_type == "pause_sequence":
                    await self._action_pause_sequence(action, entity_data)
                elif action_type == "exit_sequence":
                    await self._action_exit_sequence(action, entity_data)
                elif action_type == "update_score":
                    await self._action_update_score(action, entity_data)
            except Exception as exc:
                logger.warning(
                    "Workflow action failed for rule %d: %s", rule.id, exc,
                )

    async def _action_send_notification(
        self, rule: WorkflowRule, action: dict, entity_data: dict,
    ) -> None:
        from app.services.notification_service import create_notification

        user_id = entity_data.get("owner_id") or entity_data.get("created_by")
        if user_id:
            await create_notification(
                self.db,
                user_id=user_id,
                type="workflow_rule",
                title=action.get("title", rule.name),
                message=action.get("message", f"Kural tetiklendi: {rule.name}"),
            )

    async def _action_create_task(
        self, rule: WorkflowRule, action: dict, entity_data: dict,
    ) -> None:
        # This path can be called repeatedly for the same event; dedupe in DB write-path.
        from app.services.dedupe_service import upsert_task

        await upsert_task(
            self.db,
            owner_id=entity_data.get("owner_id", 1),
            opportunity_id=entity_data.get("opportunity_id") or entity_data.get("id"),
            title=action.get("title", f"Kural gorevi: {rule.name}")[:255],
            description=action.get("description", ""),
            source="rule",
            priority=action.get("priority", "normal"),
            status="open",
            dedupe_window_days=14,
        )

    async def _action_emit_signal(
        self, rule: WorkflowRule, action: dict, entity_data: dict,
    ) -> None:
        from app.services.revenue_signal_service import emit_signal

        await emit_signal(
            self.db,
            signal_type=action.get("signal_type", "workflow_triggered"),
            source_entity_type=rule.entity_type,
            source_entity_id=entity_data.get("id"),
            owner_id=entity_data.get("owner_id"),
            severity=action.get("severity", "med"),
            confidence=0.9,
            recommended_action=action.get("message", rule.name),
        )

    # ── Sequence V2 actions (FEATURE_SEQUENCES_V2) ──

    async def _action_enroll_sequence(
        self, action: dict, entity_data: dict,
    ) -> None:
        """Enroll a lead/opportunity in a sequence (idempotent)."""
        from app.core.config import settings as app_settings

        if not app_settings.FEATURE_SEQUENCES_V2:
            return

        from datetime import datetime, timezone
        from app.models.engagement import SequenceEnrollment

        sequence_id = action.get("sequence_id")
        if not sequence_id:
            return

        lead_id = entity_data.get("lead_id")
        opportunity_id = entity_data.get("opportunity_id") or entity_data.get("id")

        # Idempotent: skip if already enrolled
        existing = (
            await self.db.execute(
                select(SequenceEnrollment).where(
                    SequenceEnrollment.sequence_id == sequence_id,
                    SequenceEnrollment.status.in_(["active", "paused"]),
                    (SequenceEnrollment.lead_id == lead_id) if lead_id else
                    (SequenceEnrollment.opportunity_id == opportunity_id),
                )
            )
        ).scalar_one_or_none()
        if existing:
            logger.debug("Already enrolled in sequence %d — skipping", sequence_id)
            return

        enrollment = SequenceEnrollment(
            sequence_id=sequence_id,
            lead_id=lead_id,
            opportunity_id=opportunity_id if not lead_id else None,
            enrolled_by=entity_data.get("owner_id", 1),
            current_step=1,
            status="active",
            next_action_at=datetime.now(timezone.utc),
        )
        self.db.add(enrollment)
        logger.info("Enrolled in sequence %d via workflow rule", sequence_id)

    async def _action_pause_sequence(
        self, action: dict, entity_data: dict,
    ) -> None:
        """Pause active sequence enrollments for a lead/opportunity."""
        from app.core.config import settings as app_settings

        if not app_settings.FEATURE_SEQUENCES_V2:
            return

        from app.models.engagement import SequenceEnrollment

        lead_id = entity_data.get("lead_id")
        opportunity_id = entity_data.get("opportunity_id") or entity_data.get("id")

        query = select(SequenceEnrollment).where(
            SequenceEnrollment.status == "active",
        )
        if lead_id:
            query = query.where(SequenceEnrollment.lead_id == lead_id)
        elif opportunity_id:
            query = query.where(SequenceEnrollment.opportunity_id == opportunity_id)
        else:
            return

        enrollments = (await self.db.execute(query)).scalars().all()
        for e in enrollments:
            e.status = "paused"
            e.is_paused = True
        logger.info("Paused %d enrollment(s) via workflow rule", len(enrollments))

    async def _action_exit_sequence(
        self, action: dict, entity_data: dict,
    ) -> None:
        """Exit active sequence enrollments for a lead/opportunity."""
        from app.core.config import settings as app_settings

        if not app_settings.FEATURE_SEQUENCES_V2:
            return

        from app.models.engagement import SequenceEnrollment
        from app.services.sequence_engine import exit_enrollment

        lead_id = entity_data.get("lead_id")
        opportunity_id = entity_data.get("opportunity_id") or entity_data.get("id")
        exit_reason = action.get("exit_reason", "manual")

        query = select(SequenceEnrollment).where(
            SequenceEnrollment.status == "active",
        )
        if lead_id:
            query = query.where(SequenceEnrollment.lead_id == lead_id)
        elif opportunity_id:
            query = query.where(SequenceEnrollment.opportunity_id == opportunity_id)
        else:
            return

        enrollments = (await self.db.execute(query)).scalars().all()
        for e in enrollments:
            await exit_enrollment(self.db, e, exit_reason)
        logger.info("Exited %d enrollment(s) via workflow rule (reason=%s)", len(enrollments), exit_reason)

    async def _action_update_score(
        self, action: dict, entity_data: dict,
    ) -> None:
        """Update lead score via workflow rule action."""
        from app.core.config import settings as app_settings

        if not app_settings.FEATURE_BEHAVIORAL_SCORING:
            return

        from app.services.scoring_service import update_lead_score

        lead_id = entity_data.get("lead_id")
        if not lead_id:
            return

        signal_type = action.get("signal_type", "workflow_triggered")
        await update_lead_score(self.db, lead_id, signal_type, reason="workflow_rule")
