"""Event bus → RevenueSignal bridge.

Subscribes to existing events and translates them into canonical RevenueSignals.
Each handler is registered in main.py lifespan.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class RevenueSignalHandler:
    """Stateful handler that holds a session factory for event-driven signal emission."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def on_email_parsed(self, event_type: str, payload: dict) -> None:
        """email.parsed → RevenueSignal(email_parsed)."""
        async with self._session_factory() as db:
            try:
                from app.services.revenue_signal_service import emit_signal
                await emit_signal(
                    db,
                    signal_type="email_parsed",
                    source_entity_type="email",
                    source_entity_id=payload.get("email_id"),
                    opportunity_id=None,
                    customer_id=payload.get("customer_id"),
                    severity="low",
                    confidence=0.8,
                    recommended_action="Email incelenmeli ve ilgili firsata baglanmali",
                    event_key=f"email_parsed:{payload.get('email_id')}",
                    metadata=payload,
                )
                await db.commit()
            except Exception as exc:
                logger.warning("on_email_parsed failed: %s", exc)
                await db.rollback()

    async def on_stage_changed(self, event_type: str, payload: dict) -> None:
        """opportunity.stage_changed → RevenueSignal(stage_change)."""
        async with self._session_factory() as db:
            try:
                from app.services.revenue_signal_service import emit_signal

                old_stage = payload.get("old_stage", "")
                new_stage = payload.get("new_stage", "")

                # Determine severity from stage transition
                severity = "low"
                if new_stage in ("closed_lost",):
                    severity = "critical"
                elif new_stage in ("negotiation", "closed_won"):
                    severity = "high"
                elif new_stage in ("proposal",):
                    severity = "med"

                await emit_signal(
                    db,
                    signal_type="stage_change",
                    source_entity_type="opportunity",
                    source_entity_id=payload.get("opportunity_id"),
                    opportunity_id=payload.get("opportunity_id"),
                    owner_id=payload.get("owner_id"),
                    severity=severity,
                    confidence=1.0,
                    recommended_action=f"Asama degisti: {old_stage} → {new_stage}",
                    event_key=f"stage:{payload.get('opportunity_id')}:{old_stage}:{new_stage}",
                    metadata=payload,
                )
                await db.commit()
            except Exception as exc:
                logger.warning("on_stage_changed failed: %s", exc)
                await db.rollback()

    async def on_opportunity_created(self, event_type: str, payload: dict) -> None:
        """opportunity.created → RevenueSignal(stage_change) for new pipeline entry."""
        async with self._session_factory() as db:
            try:
                from app.services.revenue_signal_service import emit_signal
                await emit_signal(
                    db,
                    signal_type="stage_change",
                    source_entity_type="opportunity",
                    source_entity_id=payload.get("opportunity_id"),
                    opportunity_id=payload.get("opportunity_id"),
                    owner_id=payload.get("owner_id"),
                    severity="low",
                    confidence=1.0,
                    recommended_action="Yeni firsat olusturuldu — ilk aksiyonu planla",
                    event_key=f"opp_created:{payload.get('opportunity_id')}",
                    metadata=payload,
                )
                await db.commit()
            except Exception as exc:
                logger.warning("on_opportunity_created failed: %s", exc)
                await db.rollback()

    async def on_quote_event(self, event_type: str, payload: dict) -> None:
        """quote.approved / quote.sent → RevenueSignal."""
        async with self._session_factory() as db:
            try:
                from app.services.revenue_signal_service import emit_signal

                signal_type = "positive" if "approved" in event_type else "positive"
                severity = "med"
                action = "Teklif onaylandi" if "approved" in event_type else "Teklif gonderildi"

                await emit_signal(
                    db,
                    signal_type=signal_type,
                    source_entity_type="quote",
                    source_entity_id=payload.get("quote_id"),
                    opportunity_id=None,
                    customer_id=payload.get("customer_id"),
                    severity=severity,
                    confidence=1.0,
                    recommended_action=action,
                    event_key=f"{event_type}:{payload.get('quote_id')}",
                    metadata=payload,
                )
                await db.commit()
            except Exception as exc:
                logger.warning("on_quote_event failed: %s", exc)
                await db.rollback()

    async def on_lead_converted(self, event_type: str, payload: dict) -> None:
        """lead.converted → RevenueSignal(expansion_signal)."""
        async with self._session_factory() as db:
            try:
                from app.services.revenue_signal_service import emit_signal
                await emit_signal(
                    db,
                    signal_type="expansion_signal",
                    source_entity_type="lead",
                    source_entity_id=payload.get("lead_id"),
                    opportunity_id=payload.get("opportunity_id"),
                    customer_id=payload.get("customer_id"),
                    owner_id=payload.get("converted_by"),
                    severity="med",
                    confidence=1.0,
                    recommended_action="Lead musteri oldu — onboarding baslatilmali",
                    event_key=f"lead_converted:{payload.get('lead_id')}",
                    metadata=payload,
                )
                await db.commit()
            except Exception as exc:
                logger.warning("on_lead_converted failed: %s", exc)
                await db.rollback()
