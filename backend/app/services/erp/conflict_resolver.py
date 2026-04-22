"""Decide whether an incoming ERP record should overwrite, be overwritten, or
be parked as a conflict for human resolution.

Resolution policy (per entity, configurable via ``ERPConnection.config_json``):

    default -> "last_write_wins_erp"
    options: "last_write_wins_erp", "last_write_wins_hss", "always_erp",
             "always_hss", "manual"

"always_*" modes never create conflicts; "manual" parks every divergent
record; LWW modes park only when both sides changed since the last sync.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.erp import ERPEntityMapping, ERPSyncConflict
from app.services.erp.mapping_engine import compute_payload_hash, diff_payloads

logger = logging.getLogger(__name__)


@dataclass
class Decision:
    action: str  # "upsert" | "skip" | "conflict"
    reason: str
    mapping: ERPEntityMapping | None = None


class ConflictResolver:
    def __init__(self, db: AsyncSession, *, policy: str = "last_write_wins_erp") -> None:
        self.db = db
        self.policy = policy

    async def _load_mapping(
        self, *, connection_id: int, entity_type: str, external_id: str
    ) -> ERPEntityMapping | None:
        stmt = select(ERPEntityMapping).where(
            ERPEntityMapping.connection_id == connection_id,
            ERPEntityMapping.entity_type == entity_type,
            ERPEntityMapping.external_id == external_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def decide(
        self,
        *,
        connection_id: int,
        entity_type: str,
        external_id: str,
        incoming_payload: dict[str, Any],
        existing_hss_payload: dict[str, Any] | None,
        hss_updated_at: datetime | None,
        erp_updated_at: datetime | None,
    ) -> Decision:
        """Return the action the orchestrator should take for this record."""
        mapping = await self._load_mapping(
            connection_id=connection_id,
            entity_type=entity_type,
            external_id=external_id,
        )
        incoming_hash = compute_payload_hash(incoming_payload)

        # Nothing to compare - first time we see this external record.
        if not mapping or not existing_hss_payload:
            return Decision(action="upsert", reason="new_record", mapping=mapping)

        if mapping.payload_hash == incoming_hash:
            return Decision(action="skip", reason="unchanged", mapping=mapping)

        if self.policy == "always_erp":
            return Decision(action="upsert", reason="policy_always_erp", mapping=mapping)
        if self.policy == "always_hss":
            return Decision(action="skip", reason="policy_always_hss", mapping=mapping)

        diffs = diff_payloads(existing_hss_payload, incoming_payload)
        if not diffs:
            return Decision(action="skip", reason="no_diff_after_ignores", mapping=mapping)

        both_changed = (
            mapping.last_source == "hss"
            and hss_updated_at is not None
            and mapping.last_synced_at is not None
            and hss_updated_at > mapping.last_synced_at
        )
        if self.policy == "manual" or both_changed:
            await self._record_conflict(
                connection_id=connection_id,
                entity_type=entity_type,
                external_id=external_id,
                internal_id=mapping.internal_id,
                hss=existing_hss_payload,
                erp=incoming_payload,
                diffs=diffs,
            )
            return Decision(action="conflict", reason="concurrent_edit", mapping=mapping)

        # LWW by timestamp when only the ERP side changed since last sync.
        return Decision(action="upsert", reason=f"lww_{self.policy}", mapping=mapping)

    async def _record_conflict(
        self,
        *,
        connection_id: int,
        entity_type: str,
        external_id: str,
        internal_id: int,
        hss: dict[str, Any],
        erp: dict[str, Any],
        diffs: list[dict[str, Any]],
    ) -> ERPSyncConflict:
        row = ERPSyncConflict(
            connection_id=connection_id,
            entity_type=entity_type,
            internal_id=internal_id,
            external_id=external_id,
            hss_snapshot=json.dumps(hss, default=str, ensure_ascii=False),
            erp_snapshot=json.dumps(erp, default=str, ensure_ascii=False),
            field_diffs=json.dumps(diffs, default=str, ensure_ascii=False),
            status="pending",
        )
        self.db.add(row)
        await self.db.flush()
        logger.info(
            "erp.conflict.detected connection=%s entity=%s external_id=%s diffs=%d",
            connection_id,
            entity_type,
            external_id,
            len(diffs),
        )
        return row
