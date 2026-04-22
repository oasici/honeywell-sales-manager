"""Subscribers for ERP domain events.

Wires ERP sync output into the rest of the platform:

    erp.stock.changed   -> low_stock_risk RevenueSignal + playbook trigger
    erp.customer.synced -> no-op for now (future: enqueue vector re-embedding)
    erp.sync.failed     -> admin notification

Handlers are registered once in ``main.py`` lifespan via
:func:`register_erp_handlers`. They never raise - any exception is logged
and swallowed so the event bus keeps delivering to the remaining
subscribers.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.database import async_session
from app.core.event_bus import event_bus
from app.models.enums import UserRole

logger = logging.getLogger(__name__)


# Threshold for "significant" drop (%): below this ratio of previous qty we
# consider it meaningful enough to create a signal.
LOW_STOCK_DROP_RATIO = 0.5
# Hard floor — create a signal if stock falls below this absolute number
# regardless of relative change.
DEFAULT_LOW_STOCK_FLOOR = 5.0


async def on_stock_changed(event_type: str, payload: dict) -> None:
    """Create a low_stock_risk signal when a part dips under its threshold."""
    spare_part_id = payload.get("spare_part_id")
    sku = payload.get("sku")
    old_qty = payload.get("old_qty")
    new_qty = payload.get("new_qty")

    if spare_part_id is None or new_qty is None:
        return

    try:
        from app.models.spare_part import SparePart
        from app.services.revenue_signal_service import emit_signal

        async with async_session() as db:
            part = await db.get(SparePart, spare_part_id)
            if not part:
                return

            threshold = part.low_stock_threshold or DEFAULT_LOW_STOCK_FLOOR
            # Only signal when we crossed the threshold on the way down.
            crossed_threshold = (
                new_qty < threshold and (old_qty is None or old_qty >= threshold)
            )
            significant_drop = (
                old_qty is not None
                and old_qty > 0
                and new_qty / old_qty < LOW_STOCK_DROP_RATIO
            )

            if not (crossed_threshold or significant_drop):
                return

            severity = "high" if new_qty < threshold * 0.25 else "med"
            recommendation = (
                f"{sku} stok seviyesi {new_qty:g} birime indi "
                f"(eşik {threshold:g}). Logo/Paraşüt'ten tedarik siparişi açın."
            )

            await emit_signal(
                db,
                signal_type="low_stock_risk",
                source_entity_type="spare_part",
                source_entity_id=spare_part_id,
                severity=severity,
                confidence=0.85,
                recommended_action=recommendation,
                metadata={
                    "sku": sku,
                    "old_qty": old_qty,
                    "new_qty": new_qty,
                    "threshold": threshold,
                },
                event_key=f"stock:{spare_part_id}:{int(new_qty)}",
            )
            await db.commit()
            logger.info(
                "erp.stock.changed -> low_stock_risk part=%s sku=%s qty=%s",
                spare_part_id, sku, new_qty,
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("on_stock_changed failed: %s", exc)


async def on_customer_synced(event_type: str, payload: dict) -> None:
    """Flag downstream services that the customer dataset changed.

    Currently only logs; v3.1 will enqueue a vector re-embedding job so the
    deal-similarity search stays fresh.
    """
    customer_id = payload.get("customer_id") or payload.get("internal_id")
    connection_id = payload.get("connection_id")
    logger.info(
        "erp.customer.synced connection=%s customer=%s", connection_id, customer_id,
    )


async def on_sync_failed(event_type: str, payload: dict) -> None:
    """Notify sales managers when an ERP sync job fails."""
    job_id = payload.get("job_id")
    error = payload.get("error") or payload.get("status")
    connection_id = payload.get("connection_id")

    try:
        from app.models.user import User
        from app.services.notification_service import create_notification

        async with async_session() as db:
            managers = (
                await db.execute(
                    select(User).where(
                        User.role == UserRole.SALES_MANAGER.value,
                        User.is_active.is_(True),
                    )
                )
            ).scalars().all()

            for mgr in managers:
                await create_notification(
                    db,
                    user_id=mgr.id,
                    type="erp_sync_failed",
                    title="ERP Senkronizasyonu Başarısız",
                    message=(
                        f"Bağlantı #{connection_id} iş #{job_id} başarısız oldu: {error}"
                    ),
                    entity_type="erp_sync_job",
                    entity_id=job_id,
                )

            await db.commit()
            logger.info(
                "erp.sync.failed notified %d manager(s) for job=%s",
                len(managers), job_id,
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("on_sync_failed notification failed: %s", exc)


def register_erp_handlers() -> None:
    """Attach ERP event handlers to the in-process event bus.

    Idempotent: calling twice is safe because ``event_bus.subscribe`` allows
    duplicates but we de-dupe by reference check here.
    """
    mappings = [
        ("erp.stock.changed", on_stock_changed),
        ("erp.customer.synced", on_customer_synced),
        ("erp.product.synced", on_customer_synced),  # reuse logger only
        ("erp.sync.failed", on_sync_failed),
    ]
    for event_type, handler in mappings:
        already = handler in event_bus._handlers.get(event_type, [])  # noqa: SLF001
        if not already:
            event_bus.subscribe(event_type, handler)
    logger.info("ERP event handlers registered (%d subscriptions)", len(mappings))
