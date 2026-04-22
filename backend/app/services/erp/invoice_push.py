"""Quote → ERP invoice push helper.

Converts an accepted Quote into an :class:`ERPInvoice`, calls the adapter's
``push_invoice`` method, and records the resulting external id on an
``erp_entity_mappings`` row so the operation stays idempotent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.erp import ERPConnection, ERPEntityMapping
from app.models.quote import Quote
from app.services.domain_events import emit_domain_event
from app.services.erp import build_connector
from app.services.erp.base import (
    ConnectorError,
    ERPInvoice,
    ERPInvoiceLine,
)
from app.services.erp.mapping_engine import compute_payload_hash

logger = logging.getLogger(__name__)


class InvoicePushError(Exception):
    """Raised when the quote cannot be translated or the ERP rejects it."""


async def push_quote_as_invoice(
    db: AsyncSession,
    *,
    quote_id: int,
    connection_id: int,
    actor_id: int | None = None,
) -> dict:
    """Create an ERP invoice from an accepted quote.

    Idempotency: if we already have an ``erp_entity_mappings`` row for this
    quote against the connection we return the stored external id without a
    second push.
    """
    stmt = (
        select(Quote)
        .options(selectinload(Quote.items), selectinload(Quote.customer))
        .where(Quote.id == quote_id)
    )
    quote = (await db.execute(stmt)).scalar_one_or_none()
    if not quote:
        raise InvoicePushError(f"Quote {quote_id} not found")
    if not quote.customer_id or not quote.customer:
        raise InvoicePushError("Quote has no linked customer")

    connection = await db.get(ERPConnection, connection_id)
    if not connection or not connection.is_active:
        raise InvoicePushError("ERP connection missing or inactive")

    # Idempotency check
    existing_mapping = (
        await db.execute(
            select(ERPEntityMapping).where(
                ERPEntityMapping.connection_id == connection_id,
                ERPEntityMapping.entity_type == "invoice",
                ERPEntityMapping.internal_id == quote_id,
            )
        )
    ).scalar_one_or_none()
    if existing_mapping:
        logger.info(
            "quote.invoice.push idempotent quote=%s external=%s",
            quote_id, existing_mapping.external_id,
        )
        return {
            "external_id": existing_mapping.external_id,
            "already_pushed": True,
        }

    # Need the customer to exist on ERP side first.
    customer_mapping = (
        await db.execute(
            select(ERPEntityMapping).where(
                ERPEntityMapping.connection_id == connection_id,
                ERPEntityMapping.entity_type == "customer",
                ERPEntityMapping.internal_id == quote.customer_id,
            )
        )
    ).scalar_one_or_none()
    if not customer_mapping:
        raise InvoicePushError(
            "Customer has no ERP mapping yet; run customer sync before pushing invoice"
        )

    lines: list[ERPInvoiceLine] = []
    for item in quote.items:
        lines.append(
            ERPInvoiceLine(
                sku=item.honeywell_code or str(item.spare_part_id or item.id),
                description=item.description,
                quantity=float(item.quantity or 1),
                unit_price=float(item.unit_price or 0),
                vat_rate=None,
                line_total=float(item.line_total or 0),
            )
        )

    invoice = ERPInvoice(
        external_id=None,
        invoice_number=None,
        customer_external_id=customer_mapping.external_id,
        issue_date=datetime.now(timezone.utc),
        due_date=None,
        currency=quote.currency or "TRY",
        subtotal=float(quote.subtotal or 0),
        vat_total=float(quote.tax_amount or 0),
        grand_total=float(quote.grand_total or 0),
        lines=lines,
        notes=f"Quote {quote.quote_number}",
    )

    connector = build_connector(connection)
    try:
        external_id = await connector.push_invoice(invoice)
    except ConnectorError as exc:
        raise InvoicePushError(f"ERP rejected invoice: {exc}") from exc

    payload_hash = compute_payload_hash(invoice.model_dump())
    mapping = ERPEntityMapping(
        connection_id=connection_id,
        entity_type="invoice",
        internal_id=quote_id,
        external_id=external_id,
        payload_hash=payload_hash,
        last_source="hss",
    )
    db.add(mapping)
    await db.flush()

    await emit_domain_event(
        db,
        "erp.invoice.pushed",
        {
            "quote_id": quote_id,
            "connection_id": connection_id,
            "external_id": external_id,
            "grand_total": float(quote.grand_total or 0),
            "actor_id": actor_id,
        },
        entity_type="quote",
        entity_id=quote_id,
        persist=True,
    )

    logger.info(
        "quote.invoice.push success quote=%s connection=%s external=%s",
        quote_id, connection_id, external_id,
    )
    return {
        "external_id": external_id,
        "already_pushed": False,
    }
