"""Playbook execution engine — evaluate signals, run steps, advance via scheduler."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook import Playbook, PlaybookExecution
from app.models.revenue_signal import RevenueSignal

logger = logging.getLogger(__name__)

# Ordinal values for severity comparison (gte/lte need numeric ordering, not lexicographic)
_ORDINAL_MAP: dict[str, dict[str, int]] = {
    "severity": {"low": 0, "med": 1, "high": 2, "critical": 3},
    "priority": {"low": 0, "normal": 1, "high": 2, "urgent": 3},
}


def _compare_values(field_val: str, cond_val: str, field_name: str, op: str) -> bool:
    """Compare values with ordinal awareness for severity/priority fields."""
    ordinals = _ORDINAL_MAP.get(field_name)
    if ordinals and op in ("gte", "lte"):
        left = ordinals.get(str(field_val).lower(), -1)
        right = ordinals.get(str(cond_val).lower(), -1)
        return left >= right if op == "gte" else left <= right
    if op == "gte":
        return str(field_val) >= str(cond_val)
    if op == "lte":
        return str(field_val) <= str(cond_val)
    return False  # fallback


# Operator functions for trigger condition matching
_OPERATORS = {
    "eq": lambda field_val, cond_val, **_: str(field_val) == str(cond_val),
    "neq": lambda field_val, cond_val, **_: str(field_val) != str(cond_val),
    "gte": lambda field_val, cond_val, field_name="", **_: _compare_values(field_val, cond_val, field_name, "gte"),
    "lte": lambda field_val, cond_val, field_name="", **_: _compare_values(field_val, cond_val, field_name, "lte"),
    "contains": lambda field_val, cond_val, **_: str(cond_val) in str(field_val),
    "in": lambda field_val, cond_val, **_: str(field_val) in (
        cond_val if isinstance(cond_val, list) else [str(cond_val)]
    ),
}


class PlaybookService:
    def __init__(self, db: AsyncSession):
        self._db = db

    # ── Signal evaluation ──

    async def evaluate_signal(self, signal: RevenueSignal) -> PlaybookExecution | None:
        """Check all active playbooks against signal. Create execution if match found.

        - Load all active playbooks
        - For each: check trigger_conditions_json against signal fields
        - If match AND no active execution for same opp+playbook: create execution
        - Execute first step immediately
        - Return execution or None
        """
        if not signal.opportunity_id:
            return None

        result = await self._db.execute(
            select(Playbook).where(Playbook.is_active.is_(True))
        )
        playbooks = result.scalars().all()

        for playbook in playbooks:
            if not self._matches_conditions(playbook, signal):
                continue

            # Prevent duplicate: no active execution for same opp+playbook
            existing = await self._db.execute(
                select(PlaybookExecution.id).where(
                    and_(
                        PlaybookExecution.opportunity_id == signal.opportunity_id,
                        PlaybookExecution.playbook_id == playbook.id,
                        PlaybookExecution.status == "active",
                    )
                )
            )
            if existing.scalar_one_or_none() is not None:
                logger.debug(
                    "Active execution already exists for opp=%d playbook=%d",
                    signal.opportunity_id,
                    playbook.id,
                )
                continue

            execution = PlaybookExecution(
                playbook_id=playbook.id,
                opportunity_id=signal.opportunity_id,
                triggered_by_signal_id=signal.id,
                current_step=1,
                status="active",
            )
            self._db.add(execution)
            await self._db.flush()

            # Execute first step immediately
            await self._execute_step_internal(execution, playbook)

            return execution

        return None

    # ── Step execution ──

    async def execute_step(self, execution_id: int) -> bool:
        """Execute current step of a playbook execution. Returns True on success."""
        result = await self._db.execute(
            select(PlaybookExecution).where(PlaybookExecution.id == execution_id)
        )
        execution = result.scalar_one_or_none()
        if not execution or execution.status != "active":
            return False

        pb_result = await self._db.execute(
            select(Playbook).where(Playbook.id == execution.playbook_id)
        )
        playbook = pb_result.scalar_one_or_none()
        if not playbook:
            return False

        return await self._execute_step_internal(execution, playbook)

    async def _execute_step_internal(
        self, execution: PlaybookExecution, playbook: Playbook
    ) -> bool:
        """Internal step execution logic."""
        steps = json.loads(playbook.steps_json) if playbook.steps_json else []
        if not steps:
            execution.status = "completed"
            execution.completed_at = datetime.now(timezone.utc)
            await self._db.flush()
            return True

        # Find current step (1-indexed)
        current_step_data = None
        for step in steps:
            if step.get("step") == execution.current_step:
                current_step_data = step
                break

        if not current_step_data:
            execution.status = "completed"
            execution.completed_at = datetime.now(timezone.utc)
            await self._db.flush()
            return True

        action_type = current_step_data.get("action_type", "task")
        now = datetime.now(timezone.utc)

        if action_type == "condition":
            next_step_num = await self._evaluate_condition(
                execution, current_step_data, steps
            )
            if next_step_num is not None:
                next_step_data = None
                for step in steps:
                    if step.get("step") == next_step_num:
                        next_step_data = step
                        break
                if next_step_data:
                    execution.current_step = next_step_num
                    delay_days = next_step_data.get("delay_days", 0)
                    execution.next_action_at = now + timedelta(days=delay_days)
                else:
                    execution.status = "completed"
                    execution.completed_at = now
                    execution.next_action_at = None
                    await self._emit_completion_signal(execution, playbook)
                await self._db.flush()
                return True
        elif action_type == "task":
            await self._create_task(execution, current_step_data)
        elif action_type == "notification":
            await self._create_notification(execution, current_step_data)

        # Advance to next step
        next_step_num = execution.current_step + 1
        next_step_data = None
        for step in steps:
            if step.get("step") == next_step_num:
                next_step_data = step
                break

        if next_step_data:
            execution.current_step = next_step_num
            delay_days = next_step_data.get("delay_days", 0)
            execution.next_action_at = now + timedelta(days=delay_days)
        else:
            # No more steps — completed
            execution.status = "completed"
            execution.completed_at = now
            execution.next_action_at = None

            # Emit playbook_completed signal
            await self._emit_completion_signal(execution, playbook)

        await self._db.flush()
        return True

    async def _create_task(
        self, execution: PlaybookExecution, step_data: dict
    ) -> None:
        """Create a Task from a playbook step."""
        from app.models.opportunity import Opportunity
        from app.services.dedupe_service import upsert_task

        # Get opportunity owner
        opp_result = await self._db.execute(
            select(Opportunity).where(Opportunity.id == execution.opportunity_id)
        )
        opp = opp_result.scalar_one_or_none()
        if not opp:
            logger.warning(
                "Opportunity %d not found for playbook task creation",
                execution.opportunity_id,
            )
            return

        delay_days = step_data.get("delay_days", 0)
        due_at = datetime.now(timezone.utc) + timedelta(days=max(delay_days, 1))

        await upsert_task(
            self._db,
            owner_id=opp.owner_id,
            opportunity_id=execution.opportunity_id,
            title=str(step_data.get("template", "Playbook gorevi"))[:255],
            description=step_data.get(
                "description",
                f"Playbook: {execution.playbook_id}, Adim: {step_data.get('step')}",
            ),
            due_at=due_at,
            status="open",
            source="rule",
            priority=step_data.get("priority", "normal"),
            dedupe_window_days=14,
        )

    async def _create_notification(
        self, execution: PlaybookExecution, step_data: dict
    ) -> None:
        """Create a Notification from a playbook step."""
        from app.models.opportunity import Opportunity
        from app.services.notification_service import create_notification

        opp_result = await self._db.execute(
            select(Opportunity).where(Opportunity.id == execution.opportunity_id)
        )
        opp = opp_result.scalar_one_or_none()
        if not opp:
            return

        await create_notification(
            self._db,
            user_id=opp.owner_id,
            type="playbook_action",
            title=step_data.get("template", "Playbook bildirimi"),
            message=step_data.get("description", ""),
            entity_type="opportunity",
            entity_id=execution.opportunity_id,
        )

    async def _evaluate_condition(
        self,
        execution: PlaybookExecution,
        step_data: dict,
        steps: list[dict],
    ) -> int | None:
        """Evaluate a condition step and return the target step number.

        Condition format in step_data:
        {
            "condition": {"field": "severity", "op": "gte", "value": "high"},
            "if_true_step": 3,
            "if_false_step": 4
        }
        """
        condition = step_data.get("condition", {})
        if_true_step = step_data.get("if_true_step")
        if_false_step = step_data.get("if_false_step")

        if not condition or if_true_step is None:
            # Malformed condition — skip to next sequential step
            return execution.current_step + 1

        field = condition.get("field", "")
        op = condition.get("op", "eq")
        expected = condition.get("value")

        # Try to get field value from the triggering signal
        actual_value = None
        if execution.triggered_by_signal_id:
            from app.models.revenue_signal import RevenueSignal

            sig_result = await self._db.execute(
                select(RevenueSignal).where(
                    RevenueSignal.id == execution.triggered_by_signal_id
                )
            )
            signal = sig_result.scalar_one_or_none()
            if signal and hasattr(signal, field):
                actual_value = getattr(signal, field)

        # Also try opportunity fields if signal didn't have the field
        if actual_value is None and execution.opportunity_id:
            from app.models.opportunity import Opportunity

            opp_result = await self._db.execute(
                select(Opportunity).where(Opportunity.id == execution.opportunity_id)
            )
            opp = opp_result.scalar_one_or_none()
            if opp and hasattr(opp, field):
                actual_value = getattr(opp, field)

        # Evaluate the condition
        is_match = False
        if actual_value is not None and expected is not None:
            operator_fn = _OPERATORS.get(op)
            if operator_fn:
                is_match = operator_fn(actual_value, expected, field_name=field)

        if is_match:
            return if_true_step
        return if_false_step if if_false_step is not None else execution.current_step + 1

    async def _emit_completion_signal(
        self, execution: PlaybookExecution, playbook: Playbook
    ) -> None:
        """Emit a playbook_completed RevenueSignal."""
        from app.services.revenue_signal_service import emit_signal

        try:
            await emit_signal(
                self._db,
                signal_type="playbook_completed",
                source_entity_type="playbook_execution",
                source_entity_id=execution.id,
                opportunity_id=execution.opportunity_id,
                severity="low",
                confidence=1.0,
                recommended_action=f"Playbook tamamlandi: {playbook.name}",
                event_key=f"playbook_completed:{execution.id}",
                metadata={
                    "playbook_id": playbook.id,
                    "playbook_name": playbook.name,
                    "execution_id": execution.id,
                },
            )
        except Exception as exc:
            logger.warning("Failed to emit playbook_completed signal: %s", exc)

    # ── Scheduler entry point ──

    async def advance_due_executions(self) -> int:
        """Called by scheduler. Find executions where next_action_at <= now and status=active.
        Execute each. Return count of advanced executions.
        """
        now = datetime.now(timezone.utc)
        result = await self._db.execute(
            select(PlaybookExecution).where(
                and_(
                    PlaybookExecution.status == "active",
                    PlaybookExecution.next_action_at <= now,
                )
            )
        )
        due_executions = result.scalars().all()

        count = 0
        for execution in due_executions:
            try:
                is_ok = await self.execute_step(execution.id)
                if is_ok:
                    count += 1
            except Exception as exc:
                logger.warning(
                    "Failed to advance execution %d: %s", execution.id, exc
                )

        return count

    # ── Cancel ──

    async def cancel_execution(self, execution_id: int) -> bool:
        """Cancel an active playbook execution. Returns True if found and cancelled."""
        result = await self._db.execute(
            select(PlaybookExecution).where(PlaybookExecution.id == execution_id)
        )
        execution = result.scalar_one_or_none()
        if not execution or execution.status != "active":
            return False

        execution.status = "cancelled"
        execution.completed_at = datetime.now(timezone.utc)
        execution.next_action_at = None
        await self._db.flush()
        return True

    # ── Queries ──

    async def get_active_executions(
        self, opportunity_id: int | None = None
    ) -> list[dict]:
        """Get active playbook executions, optionally filtered by opportunity."""
        conditions = [PlaybookExecution.status == "active"]
        if opportunity_id:
            conditions.append(PlaybookExecution.opportunity_id == opportunity_id)

        result = await self._db.execute(
            select(PlaybookExecution)
            .where(and_(*conditions))
            .order_by(PlaybookExecution.started_at.desc())
        )
        executions = result.scalars().all()
        return [_execution_to_dict(e) for e in executions]

    # ── CRUD for playbooks ──

    async def create_playbook(self, **kwargs) -> Playbook:
        """Create a new playbook."""
        playbook = Playbook(**kwargs)
        self._db.add(playbook)
        await self._db.flush()
        return playbook

    async def list_playbooks(self) -> list[dict]:
        """List all playbooks."""
        result = await self._db.execute(
            select(Playbook).order_by(Playbook.created_at.desc())
        )
        playbooks = result.scalars().all()
        return [_playbook_to_dict(p) for p in playbooks]

    async def get_playbook(self, playbook_id: int) -> Playbook | None:
        """Get a single playbook by ID."""
        result = await self._db.execute(
            select(Playbook).where(Playbook.id == playbook_id)
        )
        return result.scalar_one_or_none()

    async def update_playbook(self, playbook_id: int, **kwargs) -> Playbook:
        """Update a playbook. Returns updated playbook or raises."""
        result = await self._db.execute(
            select(Playbook).where(Playbook.id == playbook_id)
        )
        playbook = result.scalar_one_or_none()
        if not playbook:
            raise ValueError(f"Playbook {playbook_id} bulunamadi")

        for key, value in kwargs.items():
            if hasattr(playbook, key):
                setattr(playbook, key, value)

        await self._db.flush()
        return playbook

    async def deactivate_playbook(self, playbook_id: int) -> bool:
        """Deactivate a playbook (soft delete). Returns True if found."""
        result = await self._db.execute(
            select(Playbook).where(Playbook.id == playbook_id)
        )
        playbook = result.scalar_one_or_none()
        if not playbook:
            return False

        playbook.is_active = False
        await self._db.flush()
        return True

    # ── Private helpers ──

    @staticmethod
    def _matches_conditions(playbook: Playbook, signal: RevenueSignal) -> bool:
        """Check if a signal matches all trigger conditions of a playbook."""
        conditions = json.loads(playbook.trigger_conditions_json) if playbook.trigger_conditions_json else []
        if not conditions:
            return False

        for condition in conditions:
            field = condition.get("field")
            op = condition.get("op", "eq")
            expected_value = condition.get("value")

            if not field or not hasattr(signal, field):
                return False

            actual_value = getattr(signal, field)
            operator_fn = _OPERATORS.get(op)
            if not operator_fn:
                return False

            if actual_value is None:
                return False

            if not operator_fn(actual_value, expected_value, field_name=field):
                return False

        return True


def _playbook_to_dict(p: Playbook) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "trigger_conditions_json": p.trigger_conditions_json,
        "steps_json": p.steps_json,
        "category": p.category,
        "is_active": p.is_active,
        "created_by": p.created_by,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _execution_to_dict(e: PlaybookExecution) -> dict:
    return {
        "id": e.id,
        "playbook_id": e.playbook_id,
        "opportunity_id": e.opportunity_id,
        "triggered_by_signal_id": e.triggered_by_signal_id,
        "current_step": e.current_step,
        "status": e.status,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        "next_action_at": e.next_action_at.isoformat() if e.next_action_at else None,
    }
