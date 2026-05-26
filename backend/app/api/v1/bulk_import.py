"""F-021 wire — bulk-import endpoints (customers + parts).

Synchronous CSV upload. Returns the import report inline — at this
scale (≤10K rows per upload, ≤500 typical), the request stays well
under the 30s timeout.

    POST   /bulk-import/customers   (multipart CSV)
    POST   /bulk-import/parts       (multipart CSV)

Both endpoints require Operations role (the import touches every
tenant row at once). Tenant_id is taken from the authenticated user
— operators cannot import into a different tenant.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.bulk_import import import_customers, import_leads, import_parts

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/bulk-import", tags=["Bulk Import"])


_MAX_CSV_BYTES = 5 * 1024 * 1024     # 5 MiB safety cap; ~50K rows of CRM data


def _require_ops(user: User) -> None:
    role = getattr(user, "role", None)
    if role not in {
        "operations", "ops_users", "ops_data", "ops_billing",
    }:
        raise HTTPException(403, detail="bulk_import_requires_ops")


async def _read_csv_text(file: UploadFile) -> str:
    if file.size and file.size > _MAX_CSV_BYTES:
        raise HTTPException(413, detail="file_too_large_max_5MiB")
    raw = await file.read()
    if len(raw) > _MAX_CSV_BYTES:
        raise HTTPException(413, detail="file_too_large_max_5MiB")
    # Try utf-8 first, then windows-1254 (common in TR Excel exports).
    for enc in ("utf-8-sig", "utf-8", "windows-1254", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise HTTPException(400, detail="csv_encoding_unrecognised")


@router.post("/customers")
async def bulk_import_customers(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a customer CSV. Returns inserted/updated/skipped counts
    + per-row errors.

    Required columns: ``name``, ``vergi_no``.
    Optional: ``email``, ``phone``, ``industry``, ``city``, ``tier``.

    Vergi_no is the natural key — re-uploading the same sheet
    updates rather than duplicates.
    """
    _require_ops(current_user)
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(400, detail="user_has_no_tenant")

    csv_text = await _read_csv_text(file)
    report = await import_customers(
        db, csv_text, tenant_id=tenant_id, actor_id=current_user.id
    )
    logger.info(
        "Customer bulk import by user %d (tenant %d): %s",
        current_user.id, tenant_id,
        {"inserted": report.inserted, "updated": report.updated, "skipped": report.skipped},
    )
    return report.as_dict()


@router.post("/leads")
async def bulk_import_leads(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """D-031 — upload a lead CSV.

    Required columns: ``first_name``, ``last_name``, ``email``.
    Optional: ``phone``, ``company``, ``title``, ``source``.

    Natural key: (tenant, lower(email)). Re-uploading the same sheet
    updates rather than duplicates.
    """
    _require_ops(current_user)
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(400, detail="user_has_no_tenant")

    csv_text = await _read_csv_text(file)
    report = await import_leads(
        db, csv_text, tenant_id=tenant_id, actor_id=current_user.id
    )
    await db.commit()
    logger.info(
        "Lead bulk import by user %d (tenant %d): %s",
        current_user.id, tenant_id,
        {"inserted": report.inserted, "updated": report.updated, "skipped": report.skipped},
    )
    return report.as_dict()


@router.post("/parts")
async def bulk_import_parts(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a spare-parts CSV.

    Required columns: ``part_code``, ``description``.
    Optional: ``category``, ``list_price``, ``currency``, ``min_stock``.

    (tenant_id, part_code) is the natural key.
    """
    _require_ops(current_user)
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(400, detail="user_has_no_tenant")

    csv_text = await _read_csv_text(file)
    report = await import_parts(
        db, csv_text, tenant_id=tenant_id, actor_id=current_user.id
    )
    logger.info(
        "Parts bulk import by user %d (tenant %d): %s",
        current_user.id, tenant_id,
        {"inserted": report.inserted, "updated": report.updated, "skipped": report.skipped},
    )
    return report.as_dict()
