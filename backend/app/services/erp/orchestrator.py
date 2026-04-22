"""ERP sync orchestrator.

Responsibilities:
    - Enqueue sync jobs (manual trigger or scheduled cron).
    - Hold a Redis-backed distributed lock per (connection, entity) so a job
      running in worker A cannot race with worker B.
    - Stream records from the adapter through the mapping engine and conflict
      resolver, then upsert into HSS tables.
    - Persist ERPSyncJob rows with success / failure counters.
    - Emit domain events so other subsystems (signals, playbooks) can react.

This is a minimal v1 that handles customer and product entities and defers
invoice push to a dedicated helper. Full cadence of background workers will
hook into this module in Sprint 4.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.customer import Customer
from app.models.erp import ERPConnection, ERPEntityMapping, ERPSyncJob
from app.models.spare_part import SparePart
from app.services.domain_events import DomainEvents, emit_domain_event
from app.services.erp.base import (
    ConnectorError,
    ERPCustomer,
    ERPProduct,
)
from app.services.erp.conflict_resolver import ConflictResolver
from app.services.erp.factory import build_connector
from app.services.erp.mapping_engine import (
    compute_payload_hash,
    to_internal_customer,
    to_internal_product,
)

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 600  # 10 minutes
LOCK_KEY_FMT = "erp:sync:lock:{connection_id}:{entity}"


# ── Redis lock helpers ──────────────────────────────────────────────────────

class _RedisLock:
    """Tiny SET NX EX distributed lock."""

    def __init__(self, redis: Any, key: str, ttl: int):
        self._redis = redis
        self._key = key
        self._ttl = ttl
        self._owner = f"{datetime.now(timezone.utc).timestamp():.3f}"
        self._acquired = False

    async def __aenter__(self) -> "_RedisLock":
        self._acquired = bool(
            await self._redis.set(self._key, self._owner, nx=True, ex=self._ttl)
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._acquired:
            with contextlib.suppress(Exception):
                await self._redis.delete(self._key)

    @property
    def acquired(self) -> bool:
        return self._acquired


# ── Public orchestrator API ─────────────────────────────────────────────────

class ERPOrchestrator:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis

    # ── Entry points ──────────────────────────────────────────────────────

    async def trigger(
        self,
        *,
        connection_id: int,
        entity: str,
        mode: str = "delta",
        actor_id: int | None = None,
        triggered_by: str = "manual",
    ) -> int:
        """Queue a sync job and kick off its worker asynchronously.

        Returns the new ``ERPSyncJob.id``.
        """
        async with self._session_factory() as db:
            job = ERPSyncJob(
                connection_id=connection_id,
                entity=entity,
                mode=mode,
                status="queued",
                triggered_by=triggered_by,
                actor_id=actor_id,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
            job_id = job.id

        # Fire-and-forget: the worker creates its own DB session.
        asyncio.create_task(self._run(job_id))
        return job_id

    # ── Worker body ───────────────────────────────────────────────────────

    async def _run(self, job_id: int) -> None:
        async with self._session_factory() as db:
            job = await db.get(ERPSyncJob, job_id)
            if not job:
                logger.warning("erp.sync.missing job_id=%s", job_id)
                return
            connection = await db.get(ERPConnection, job.connection_id)
            if not connection or not connection.is_active:
                job.status = "failed"
                job.finished_at = datetime.now(timezone.utc)
                job.error_message = "Connection missing or inactive"
                await db.commit()
                return

            policy = _resolve_policy(connection.config_json)
            resolver = ConflictResolver(db, policy=policy)

            lock_key = LOCK_KEY_FMT.format(
                connection_id=connection.id, entity=job.entity
            )

            async with _acquire_lock(self._redis, lock_key):
                job.status = "running"
                job.started_at = datetime.now(timezone.utc)
                await db.commit()

                try:
                    connector = build_connector(connection)
                    if job.entity == "customer":
                        await self._sync_customers(db, job, connection, connector, resolver)
                    elif job.entity == "product":
                        await self._sync_products(db, job, connection, connector, resolver)
                    elif job.entity == "stock":
                        await self._sync_stock(db, job, connection, connector)
                    elif job.entity == "all":
                        await self._sync_customers(db, job, connection, connector, resolver)
                        await self._sync_products(db, job, connection, connector, resolver)
                        await self._sync_stock(db, job, connection, connector)
                    else:
                        raise ConnectorError(f"Unknown sync entity: {job.entity}")

                    job.status = "success"
                except ConnectorError as exc:
                    job.status = "failed"
                    job.error_message = str(exc)
                    logger.warning("erp.sync.failed job=%s err=%s", job_id, exc)
                except Exception as exc:  # pragma: no cover - unexpected
                    job.status = "failed"
                    job.error_message = f"unexpected: {exc}"
                    logger.exception("erp.sync.unexpected job=%s", job_id)
                finally:
                    job.finished_at = datetime.now(timezone.utc)
                    await db.commit()

            await emit_domain_event(
                db,
                _event_type(job.entity, job.status),
                {
                    "job_id": job.id,
                    "connection_id": connection.id,
                    "entity": job.entity,
                    "status": job.status,
                    "records_created": job.records_created,
                    "records_updated": job.records_updated,
                    "records_skipped": job.records_skipped,
                    "records_failed": job.records_failed,
                },
                entity_type="erp_sync_job",
                entity_id=job.id,
                persist=True,
            )
            await db.commit()

    # ── Entity-specific sync flows ────────────────────────────────────────

    async def _sync_customers(
        self,
        db: AsyncSession,
        job: ERPSyncJob,
        connection: ERPConnection,
        connector: Any,
        resolver: ConflictResolver,
    ) -> None:
        since = connection.last_customer_sync_at if job.mode == "delta" else None
        async for erp_customer in connector.fetch_customers(since=since):
            await self._process_customer(db, job, connection.id, resolver, erp_customer)
        connection.last_customer_sync_at = datetime.now(timezone.utc)

    async def _process_customer(
        self,
        db: AsyncSession,
        job: ERPSyncJob,
        connection_id: int,
        resolver: ConflictResolver,
        erp_customer: ERPCustomer,
    ) -> None:
        mapped = to_internal_customer(erp_customer.model_dump(), config_json=None)
        existing_mapping = await _load_mapping(
            db, connection_id, "customer", erp_customer.external_id
        )
        existing: Customer | None = None
        if existing_mapping:
            existing = await db.get(Customer, existing_mapping.internal_id)

        decision = await resolver.decide(
            connection_id=connection_id,
            entity_type="customer",
            external_id=erp_customer.external_id,
            incoming_payload=mapped,
            existing_hss_payload=(_customer_to_dict(existing) if existing else None),
            hss_updated_at=existing.updated_at if existing else None,
            erp_updated_at=erp_customer.updated_at,
        )

        if decision.action == "skip":
            job.records_skipped += 1
            return
        if decision.action == "conflict":
            job.records_skipped += 1
            return

        payload_hash = compute_payload_hash(mapped)
        if existing is None:
            customer = Customer(
                name=mapped.get("name") or "Unknown",
                email=mapped.get("email") or f"erp-{erp_customer.external_id}@noemail.local",
                phone=mapped.get("phone"),
                address=mapped.get("address"),
                tax_id=mapped.get("tax_number"),
            )
            db.add(customer)
            await db.flush()
            await _upsert_mapping(
                db,
                connection_id=connection_id,
                entity_type="customer",
                internal_id=customer.id,
                external_id=erp_customer.external_id,
                payload_hash=payload_hash,
                source="erp",
            )
            job.records_created += 1
        else:
            existing.name = mapped.get("name") or existing.name
            existing.phone = mapped.get("phone") or existing.phone
            existing.address = mapped.get("address") or existing.address
            existing.tax_id = mapped.get("tax_number") or existing.tax_id
            if mapped.get("email"):
                existing.email = mapped["email"]
            if existing_mapping:
                existing_mapping.payload_hash = payload_hash
                existing_mapping.last_synced_at = datetime.now(timezone.utc)
                existing_mapping.last_source = "erp"
            job.records_updated += 1

    async def _sync_stock(
        self,
        db: AsyncSession,
        job: ERPSyncJob,
        connection: ERPConnection,
        connector: Any,
    ) -> None:
        """Pull stock levels and emit ``erp.stock.changed`` when qty moves."""
        updated = 0
        async for stock in connector.fetch_stock():
            sku = stock.sku
            if not sku:
                continue
            stmt = select(SparePart).where(SparePart.honeywell_code == sku)
            part = (await db.execute(stmt)).scalar_one_or_none()
            if not part:
                job.records_skipped += 1
                continue

            old_qty = part.current_stock_qty
            new_qty = float(stock.quantity)
            part.current_stock_qty = new_qty
            part.last_stock_sync_at = datetime.now(timezone.utc)

            if old_qty is None or abs(old_qty - new_qty) > 1e-6:
                await emit_domain_event(
                    db,
                    "erp.stock.changed",
                    {
                        "spare_part_id": part.id,
                        "sku": sku,
                        "old_qty": old_qty,
                        "new_qty": new_qty,
                        "warehouse_code": stock.warehouse_code,
                        "connection_id": connection.id,
                    },
                    entity_type="spare_part",
                    entity_id=part.id,
                    persist=False,
                )
                updated += 1

        job.records_updated += updated
        connection.last_invoice_sync_at = connection.last_invoice_sync_at  # keep noqa
        logger.info(
            "erp.stock.sync connection=%s parts_updated=%d", connection.id, updated,
        )

    async def _sync_products(
        self,
        db: AsyncSession,
        job: ERPSyncJob,
        connection: ERPConnection,
        connector: Any,
        resolver: ConflictResolver,
    ) -> None:
        since = connection.last_product_sync_at if job.mode == "delta" else None
        async for erp_product in connector.fetch_products(since=since):
            await self._process_product(db, job, connection.id, resolver, erp_product)
        connection.last_product_sync_at = datetime.now(timezone.utc)

    async def _process_product(
        self,
        db: AsyncSession,
        job: ERPSyncJob,
        connection_id: int,
        resolver: ConflictResolver,
        erp_product: ERPProduct,
    ) -> None:
        mapped = to_internal_product(erp_product.model_dump(), config_json=None)
        existing_mapping = await _load_mapping(
            db, connection_id, "product", erp_product.external_id
        )
        existing: SparePart | None = None
        if existing_mapping:
            existing = await db.get(SparePart, existing_mapping.internal_id)

        decision = await resolver.decide(
            connection_id=connection_id,
            entity_type="product",
            external_id=erp_product.external_id,
            incoming_payload=mapped,
            existing_hss_payload=_product_to_dict(existing) if existing else None,
            hss_updated_at=getattr(existing, "updated_at", None) if existing else None,
            erp_updated_at=erp_product.updated_at,
        )

        if decision.action in ("skip", "conflict"):
            job.records_skipped += 1
            return

        payload_hash = compute_payload_hash(mapped)
        if existing is None:
            part = SparePart(
                honeywell_code=mapped.get("sku") or erp_product.external_id,
                name_tr=mapped.get("name") or "",
                transfer_price=mapped.get("unit_price"),
                price_currency=mapped.get("currency") or "TRY",
            )
            db.add(part)
            await db.flush()
            await _upsert_mapping(
                db,
                connection_id=connection_id,
                entity_type="product",
                internal_id=part.id,
                external_id=erp_product.external_id,
                payload_hash=payload_hash,
                source="erp",
            )
            job.records_created += 1
        else:
            if mapped.get("name"):
                existing.name_tr = mapped["name"]
            if mapped.get("unit_price") is not None:
                existing.transfer_price = mapped["unit_price"]
            if mapped.get("currency"):
                existing.price_currency = mapped["currency"]
            if existing_mapping:
                existing_mapping.payload_hash = payload_hash
                existing_mapping.last_synced_at = datetime.now(timezone.utc)
                existing_mapping.last_source = "erp"
            job.records_updated += 1


# ── Helpers ─────────────────────────────────────────────────────────────────

def _customer_to_dict(customer: Customer) -> dict[str, Any]:
    return {
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "address": customer.address,
        "tax_number": customer.tax_id,
    }


def _product_to_dict(part: SparePart) -> dict[str, Any]:
    return {
        "sku": part.honeywell_code,
        "name": part.name_tr or part.name_en,
        "unit_price": part.transfer_price,
        "currency": part.price_currency,
    }


async def _load_mapping(
    db: AsyncSession, connection_id: int, entity_type: str, external_id: str
) -> ERPEntityMapping | None:
    stmt = select(ERPEntityMapping).where(
        ERPEntityMapping.connection_id == connection_id,
        ERPEntityMapping.entity_type == entity_type,
        ERPEntityMapping.external_id == external_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _upsert_mapping(
    db: AsyncSession,
    *,
    connection_id: int,
    entity_type: str,
    internal_id: int,
    external_id: str,
    payload_hash: str,
    source: str,
) -> ERPEntityMapping:
    stmt = select(ERPEntityMapping).where(
        ERPEntityMapping.connection_id == connection_id,
        ERPEntityMapping.entity_type == entity_type,
        ERPEntityMapping.internal_id == internal_id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = ERPEntityMapping(
            connection_id=connection_id,
            entity_type=entity_type,
            internal_id=internal_id,
            external_id=external_id,
            payload_hash=payload_hash,
            last_source=source,
        )
        db.add(row)
    else:
        row.payload_hash = payload_hash
        row.last_synced_at = datetime.now(timezone.utc)
        row.last_source = source
    await db.flush()
    return row


def _resolve_policy(config_json: str | None) -> str:
    if not config_json:
        return "last_write_wins_erp"
    try:
        return (json.loads(config_json) or {}).get("conflict_policy") or "last_write_wins_erp"
    except json.JSONDecodeError:
        return "last_write_wins_erp"


def _event_type(entity: str, status: str) -> str:
    if status == "success":
        return f"erp.{entity}.synced"
    return "erp.sync.failed"


@contextlib.asynccontextmanager
async def _acquire_lock(redis: Any | None, key: str):
    """Yield control once the lock is held; fall through on no-redis dev."""
    if not redis:
        yield
        return
    async with _RedisLock(redis, key, LOCK_TTL_SECONDS) as lock:
        if not lock.acquired:
            raise ConnectorError(f"Sync already in progress for {key}")
        yield
