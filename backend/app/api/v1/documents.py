from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.shared_document import SharedDocument
from app.models.user import User

router = APIRouter(prefix="/documents", tags=["Documents"])


class ShareRequest(BaseModel):
    quote_id: int | None = None
    file_name: str
    file_url: str
    shared_with_email: str


@router.post("/share")
async def share_document(
    body: ShareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a shared document with a unique tracking token."""
    tracking_token = uuid.uuid4().hex
    doc = SharedDocument(
        quote_id=body.quote_id,
        file_name=body.file_name,
        file_url=body.file_url,
        shared_with_email=body.shared_with_email,
        tracking_token=tracking_token,
        created_by=current_user.id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return {
        "data": {
            "id": doc.id,
            "tracking_token": tracking_token,
            "tracking_url": f"/api/v1/documents/track/{tracking_token}",
        }
    }


@router.get("/track/{token}")
async def track_document(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """PUBLIC endpoint. Increment views and return file info."""
    result = await db.execute(
        select(SharedDocument).where(SharedDocument.tracking_token == token)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException("Belge bulunamadi")

    now = datetime.now(timezone.utc)
    doc.views_count += 1
    if doc.first_viewed_at is None:
        doc.first_viewed_at = now
    doc.last_viewed_at = now
    await db.commit()

    return {"data": {"file_url": doc.file_url, "file_name": doc.file_name}}


@router.get("/")
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List shared documents for the current user."""
    result = await db.execute(
        select(SharedDocument)
        .where(SharedDocument.created_by == current_user.id)
        .order_by(SharedDocument.created_at.desc())
    )
    docs = result.scalars().all()
    return {
        "data": [
            {
                "id": d.id,
                "quote_id": d.quote_id,
                "file_name": d.file_name,
                "file_url": d.file_url,
                "shared_with_email": d.shared_with_email,
                "tracking_token": d.tracking_token,
                "views_count": d.views_count,
                "first_viewed_at": d.first_viewed_at.isoformat() if d.first_viewed_at else None,
                "last_viewed_at": d.last_viewed_at.isoformat() if d.last_viewed_at else None,
                "total_view_seconds": d.total_view_seconds,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    }


@router.get("/{document_id}/analytics")
async def get_document_analytics(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return view analytics for a specific document."""
    result = await db.execute(
        select(SharedDocument).where(
            SharedDocument.id == document_id,
            SharedDocument.created_by == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException("Belge bulunamadi")

    return {
        "data": {
            "id": doc.id,
            "file_name": doc.file_name,
            "shared_with_email": doc.shared_with_email,
            "views_count": doc.views_count,
            "first_viewed_at": doc.first_viewed_at.isoformat() if doc.first_viewed_at else None,
            "last_viewed_at": doc.last_viewed_at.isoformat() if doc.last_viewed_at else None,
            "total_view_seconds": doc.total_view_seconds,
        }
    }
