"""Approval routing service -- evaluates rules, creates approval chains, processes decisions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from operator import gt, ge, lt, le

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.approval import ApprovalRequest, ApprovalRule
from app.models.enums import UserRole
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)

OPERATOR_MAP = {
    "gt": gt,
    "gte": ge,
    "lt": lt,
    "lte": le,
}


class ApprovalService:
    """Evaluate approval rules, build multi-level chains, and process decisions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def evaluate_rules(
        self, entity_type: str, entity_data: dict,
    ) -> list[ApprovalRule]:
        """Find matching approval rules sorted by priority desc.

        entity_data keys: discount_pct, grand_total, deal_amount
        """
        result = await self.db.execute(
            select(ApprovalRule)
            .where(
                and_(
                    ApprovalRule.entity_type == entity_type,
                    ApprovalRule.is_active.is_(True),
                )
            )
            .order_by(ApprovalRule.priority.desc())
        )
        all_rules = result.scalars().all()

        matched: list[ApprovalRule] = []
        for rule in all_rules:
            entity_value = entity_data.get(rule.condition_type)
            if entity_value is None:
                continue

            comparator = OPERATOR_MAP.get(rule.threshold_operator)
            if comparator is None:
                logger.warning(
                    "Unknown operator '%s' on rule %d", rule.threshold_operator, rule.id,
                )
                continue

            if comparator(entity_value, rule.threshold_value):
                matched.append(rule)

        return matched

    def _is_delegation_active(self, rule: ApprovalRule) -> bool:
        """Check if a rule has an active delegation."""
        if rule.delegate_to is None:
            return False
        if rule.delegate_until is None:
            # Permanent delegation
            return True
        return rule.delegate_until > datetime.now(timezone.utc)

    async def submit_for_approval(
        self,
        entity_type: str,
        entity_id: int,
        requested_by: int,
        entity_data: dict,
    ) -> list[ApprovalRequest]:
        """Create approval chain from matching rules.

        Returns list of ApprovalRequest instances.
        An empty list means no rules matched (auto-approve).
        """
        # Concurrent protection: check for existing pending chain
        existing_result = await self.db.execute(
            select(ApprovalRequest).where(
                and_(
                    ApprovalRequest.entity_type == entity_type,
                    ApprovalRequest.entity_id == entity_id,
                    ApprovalRequest.status == "pending",
                )
            )
        )
        existing_pending = list(existing_result.scalars().all())
        if existing_pending:
            logger.info(
                "Pending approval chain already exists for %s #%d, returning existing",
                entity_type, entity_id,
            )
            return existing_pending

        rules = await self.evaluate_rules(entity_type, entity_data)
        if not rules:
            return []

        requests: list[ApprovalRequest] = []

        # Determine chain mode from the first matching rule (all rules
        # in a single evaluation share the same chain_mode).
        chain_mode = getattr(rules[0], "chain_mode", "sequential") if rules else "sequential"
        is_parallel = chain_mode == "parallel"

        for idx, rule in enumerate(rules):
            # Resolve assignee with delegation logic
            assignee = rule.approver_user_id
            delegation_comment = None

            if self._is_delegation_active(rule):
                original_approver = rule.approver_user_id
                assignee = rule.delegate_to
                delegation_comment = (
                    f"Yetki devri: kullanici #{original_approver} → kullanici #{assignee}"
                )

            # Parallel: all requests at level 1; sequential: incrementing levels
            level = 1 if is_parallel else idx + 1

            approval_request = ApprovalRequest(
                entity_type=entity_type,
                entity_id=entity_id,
                rule_id=rule.id,
                level=level,
                status="pending",
                requested_by=requested_by,
                assigned_to=assignee,
                comments=delegation_comment,
            )
            self.db.add(approval_request)
            requests.append(approval_request)

        await self.db.flush()

        # Send notification to each approver with a direct assignment
        for req in requests:
            if req.assigned_to is not None:
                await create_notification(
                    self.db,
                    user_id=req.assigned_to,
                    type="approval_pending",
                    title="Yeni onay talebi",
                    message=f"{entity_type} #{entity_id} icin onayiniz bekleniyor (seviye {req.level})",
                    entity_type="approval_request",
                    entity_id=req.id,
                )

        return requests

    async def approve(
        self, request_id: int, user_id: int, comments: str = "",
    ) -> ApprovalRequest:
        """Approve one step in the chain. Checks if chain is complete."""
        result = await self.db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == request_id)
            .with_for_update()
        )
        approval_request = result.scalar_one_or_none()
        if not approval_request:
            raise NotFoundException("Onay talebi bulunamadi")

        if approval_request.status != "pending":
            raise BadRequestException(
                f"Bu talep zaten islendi (durum: {approval_request.status})"
            )

        # Self-approval prevention (sales_manager exempt)
        if approval_request.requested_by == user_id:
            from app.models.user import User
            user_result = await self.db.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user or user.role != UserRole.SALES_MANAGER.value:
                raise BadRequestException("Kendi talebinizi onaylayamazsiniz")

        approval_request.status = "approved"
        approval_request.decided_by = user_id
        approval_request.decided_at = datetime.now(timezone.utc)
        approval_request.comments = comments or None
        await self.db.flush()

        # Notify the requester
        await create_notification(
            self.db,
            user_id=approval_request.requested_by,
            type="approval_approved",
            title="Onay talebi kabul edildi",
            message=(
                f"{approval_request.entity_type} #{approval_request.entity_id} "
                f"seviye {approval_request.level} onaylandi"
            ),
            entity_type="approval_request",
            entity_id=approval_request.id,
        )

        logger.info(
            "Approval request %d approved by user %d", request_id, user_id,
        )
        return approval_request

    async def reject(
        self, request_id: int, user_id: int, comments: str = "",
    ) -> ApprovalRequest:
        """Reject one step -- also rejects all pending requests for the same entity."""
        result = await self.db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == request_id)
            .with_for_update()
        )
        approval_request = result.scalar_one_or_none()
        if not approval_request:
            raise NotFoundException("Onay talebi bulunamadi")

        if approval_request.status != "pending":
            raise BadRequestException(
                f"Bu talep zaten islendi (durum: {approval_request.status})"
            )

        now = datetime.now(timezone.utc)

        # Reject the target request
        approval_request.status = "rejected"
        approval_request.decided_by = user_id
        approval_request.decided_at = now
        approval_request.comments = comments or None

        # Cascade: reject all other pending requests for the same entity
        await self.db.execute(
            update(ApprovalRequest)
            .where(
                and_(
                    ApprovalRequest.entity_type == approval_request.entity_type,
                    ApprovalRequest.entity_id == approval_request.entity_id,
                    ApprovalRequest.status == "pending",
                    ApprovalRequest.id != request_id,
                )
            )
            .values(
                status="rejected",
                decided_by=user_id,
                decided_at=now,
                comments="Otomatik reddedildi (baglantili talep reddedildi)",
            )
        )
        await self.db.flush()

        # Notify the requester
        await create_notification(
            self.db,
            user_id=approval_request.requested_by,
            type="approval_rejected",
            title="Onay talebi reddedildi",
            message=(
                f"{approval_request.entity_type} #{approval_request.entity_id} "
                f"seviye {approval_request.level} reddedildi"
            ),
            entity_type="approval_request",
            entity_id=approval_request.id,
        )

        logger.info(
            "Approval request %d rejected by user %d (cascade applied)", request_id, user_id,
        )
        return approval_request

    async def get_pending_approvals(self, user_id: int) -> list[ApprovalRequest]:
        """Get approval requests pending for this user (by direct assignment or delegation)."""
        now = datetime.now(timezone.utc)

        # Find rules where this user is an active delegate
        delegate_rule_result = await self.db.execute(
            select(ApprovalRule.id).where(
                and_(
                    ApprovalRule.delegate_to == user_id,
                    ApprovalRule.is_active.is_(True),
                    or_(
                        ApprovalRule.delegate_until.is_(None),
                        ApprovalRule.delegate_until > now,
                    ),
                )
            )
        )
        delegate_rule_ids = [r for r in delegate_rule_result.scalars().all()]

        # Build conditions: directly assigned OR assigned via delegated rule
        conditions = [ApprovalRequest.assigned_to == user_id]
        if delegate_rule_ids:
            conditions.append(
                and_(
                    ApprovalRequest.rule_id.in_(delegate_rule_ids),
                    ApprovalRequest.status == "pending",
                )
            )

        result = await self.db.execute(
            select(ApprovalRequest).where(
                and_(
                    or_(*conditions),
                    ApprovalRequest.status == "pending",
                )
            )
            .order_by(ApprovalRequest.created_at.desc())
        )
        return list(result.scalars().all())

    async def is_fully_approved(self, entity_type: str, entity_id: int) -> bool:
        """Check if all approval requests for entity are approved.

        For parallel chains (all at same level): ALL requests must be approved.
        For sequential chains: each level must be approved in order.
        Both modes ultimately require every request to be approved.
        """
        result = await self.db.execute(
            select(ApprovalRequest).where(
                and_(
                    ApprovalRequest.entity_type == entity_type,
                    ApprovalRequest.entity_id == entity_id,
                )
            )
        )
        requests = result.scalars().all()

        if not requests:
            # No approval requests means no rules applied (auto-approved)
            return True

        return all(r.status == "approved" for r in requests)

    async def check_escalations(self) -> int:
        """Find pending approvals past escalation_hours. Apply escalation_action.

        Returns count of escalated approvals.
        """
        now = datetime.now(timezone.utc)
        escalated_count = 0

        # Find all pending requests with rules that have escalation configured
        result = await self.db.execute(
            select(ApprovalRequest, ApprovalRule)
            .join(ApprovalRule, ApprovalRequest.rule_id == ApprovalRule.id)
            .where(
                and_(
                    ApprovalRequest.status == "pending",
                    ApprovalRule.escalation_hours.isnot(None),
                    ApprovalRule.escalation_action.isnot(None),
                )
            )
        )
        rows = result.all()

        for approval_request, rule in rows:
            created = approval_request.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)

            hours_elapsed = (now - created).total_seconds() / 3600
            if hours_elapsed < rule.escalation_hours:
                continue

            if rule.escalation_action == "auto_approve":
                approval_request.status = "approved"
                approval_request.decided_at = now
                approval_request.comments = (
                    f"Otomatik onay: {rule.escalation_hours} saat icinde "
                    f"islem yapilmadi (eskalasyon)"
                )
                escalated_count += 1

                await create_notification(
                    self.db,
                    user_id=approval_request.requested_by,
                    type="approval_escalated",
                    title="Onay talebi otomatik onaylandi",
                    message=(
                        f"{approval_request.entity_type} #{approval_request.entity_id} "
                        f"eskalasyon suresi doldu, otomatik onaylandi"
                    ),
                    entity_type="approval_request",
                    entity_id=approval_request.id,
                )

            elif rule.escalation_action == "escalate_to_manager":
                # Reassign to a manager
                from app.models.user import User

                manager_result = await self.db.execute(
                    select(User).where(
                        and_(
                            User.role == UserRole.SALES_MANAGER.value,
                            User.is_active.is_(True),
                            User.id != approval_request.assigned_to,
                        )
                    ).limit(1)
                )
                manager = manager_result.scalar_one_or_none()

                if manager:
                    old_assignee = approval_request.assigned_to
                    approval_request.assigned_to = manager.id
                    approval_request.comments = (
                        f"Eskalasyon: kullanici #{old_assignee} "
                        f"{rule.escalation_hours} saat icinde islem yapmadi. "
                        f"Yonetici #{manager.id} atandi."
                    )
                    escalated_count += 1

                    await create_notification(
                        self.db,
                        user_id=manager.id,
                        type="approval_escalated",
                        title="Eskalasyon: Onay talebi size atandi",
                        message=(
                            f"{approval_request.entity_type} #{approval_request.entity_id} "
                            f"icin onay suresi asimi, size yonlendirildi"
                        ),
                        entity_type="approval_request",
                        entity_id=approval_request.id,
                    )

            logger.info(
                "Escalated approval request %d (action: %s)",
                approval_request.id,
                rule.escalation_action,
            )

        if escalated_count:
            await self.db.flush()

        return escalated_count

    async def get_approval_history(
        self, entity_type: str, entity_id: int,
    ) -> list[ApprovalRequest]:
        """Get all approval requests for an entity, ordered by level."""
        result = await self.db.execute(
            select(ApprovalRequest)
            .where(
                and_(
                    ApprovalRequest.entity_type == entity_type,
                    ApprovalRequest.entity_id == entity_id,
                )
            )
            .order_by(ApprovalRequest.level.asc())
        )
        return list(result.scalars().all())
