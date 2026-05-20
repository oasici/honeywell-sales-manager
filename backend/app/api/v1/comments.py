"""Comment / Mention API endpoints."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.comment import Comment
from app.models.customer import Customer
from app.models.lead import Lead
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.tenant_context import assert_same_tenant, scoped_for_user
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.round15_pagination import CommentRow

router = APIRouter(prefix="/comments", tags=["Comments"])

MENTION_PATTERN = re.compile(r"@(\w+)")
ALLOWED_ENTITY_TYPES = {"opportunity", "customer", "lead"}
# Round-4 R4-TEN-18 — parent-entity model lookup table for tenant resolution.
_PARENT_MODEL_BY_TYPE = {
    "opportunity": Opportunity,
    "customer": Customer,
    "lead": Lead,
}


async def _load_parent_for_tenant_check(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
):
    """Load the parent CRM entity referenced by a comment.

    Returns None when ``entity_type`` is not in the allow list. Callers
    should treat ``None`` as "404 not found" so we never leak whether the
    parent exists in another tenant.
    """
    model = _PARENT_MODEL_BY_TYPE.get(entity_type)
    if model is None:
        return None
    return (
        await db.execute(select(model).where(model.id == entity_id))
    ).scalar_one_or_none()


class CommentCreate(BaseModel):
    entity_type: str = Field(..., min_length=1)
    entity_id: int
    body: str = Field(..., min_length=1)
    parent_id: int | None = None


def _serialize_comment(comment: Comment) -> dict:
    """Convert a Comment ORM instance to a JSON-friendly dict."""
    return {
        "id": comment.id,
        # Round-4 R4-DTO — round-trip tenant_id (R4-TEN-18).
        "tenant_id": getattr(comment, "tenant_id", None),
        "entity_type": comment.entity_type,
        "entity_id": comment.entity_id,
        "user_id": comment.user_id,
        "body": comment.body,
        "mentions_json": comment.mentions_json,
        "parent_id": comment.parent_id,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
        "updated_at": comment.updated_at.isoformat() if comment.updated_at else None,
        "user": {
            "id": comment.user.id,
            "full_name": comment.user.full_name,
        }
        if comment.user
        else None,
        "replies": [_serialize_comment(r) for r in (comment.replies or [])],
    }


@router.get("/", response_model=PaginatedResponse[CommentRow])
async def list_comments(
    entity_type: str = Query(...),
    entity_id: int = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List top-level comments with nested replies for an entity."""
    # Round-4 R4-TEN-18 — verify the parent CRM entity is in the caller's
    # tenant before listing comments. Treat unknown entity types and
    # cross-tenant access as 404 to avoid leaking existence.
    parent = await _load_parent_for_tenant_check(db, entity_type, entity_id)
    if parent is None:
        raise NotFoundException("Not found")
    assert_same_tenant(parent, current_user, exception_cls=NotFoundException)

    stmt = (
        select(Comment)
        .options(
            selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.user),
        )
        .where(
            Comment.entity_type == entity_type,
            Comment.entity_id == entity_id,
            Comment.parent_id.is_(None),
        )
        .order_by(Comment.created_at.asc())
    )
    # Round-4 R4-TEN-18 — also scope the comment query directly so legacy
    # rows with tenant_id from a different tenant never leak even if the
    # parent check is bypassed by future refactors.
    stmt = scoped_for_user(stmt, current_user, column=Comment.tenant_id)
    result = await db.execute(stmt)
    comments = result.scalars().all()
    # R6-PAGE-1 — canonical envelope.
    items = [_serialize_comment(c) for c in comments]
    total = len(items)
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
    }


@router.post("/", status_code=201, response_model=dict)
async def create_comment(
    body: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a comment and generate mention notifications."""
    if body.entity_type not in ALLOWED_ENTITY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"entity_type must be one of {ALLOWED_ENTITY_TYPES}",
        )

    # Round-4 R4-TEN-18 — verify the parent CRM entity is in the caller's
    # tenant before inserting. Treat cross-tenant + unknown as 404.
    parent = await _load_parent_for_tenant_check(db, body.entity_type, body.entity_id)
    if parent is None:
        raise NotFoundException("Not found")
    assert_same_tenant(parent, current_user, exception_cls=NotFoundException)

    # Parse @mentions from body text. Round-4 R4-TEN-18 — restrict the
    # mention lookup to the caller's tenant so foreign-tenant managers
    # cannot be silently @-tagged into our notifications.
    mentioned_usernames = MENTION_PATTERN.findall(body.body)
    mentioned_user_ids: list[int] = []

    for username in set(mentioned_usernames):
        mention_stmt = scoped_for_user(
            select(User).where(User.full_name.ilike(f"%{username}%")),
            current_user,
            column=User.tenant_id,
        )
        user_result = await db.execute(mention_stmt)
        mentioned_user = user_result.scalar_one_or_none()
        if mentioned_user and mentioned_user.id != current_user.id:
            mentioned_user_ids.append(mentioned_user.id)

    comment = Comment(
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        user_id=current_user.id,
        body=body.body,
        mentions_json=json.dumps(mentioned_user_ids) if mentioned_user_ids else None,
        parent_id=body.parent_id,
        # Round-4 R4-TEN-18 — stamp tenant on create.
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    db.add(comment)
    await db.flush()

    # Create notifications for mentioned users. Round-10 R10-DB-5 —
    # Notification.tenant_id is NOT NULL; mentions stay inside the
    # current user's tenant (mention across tenants is impossible
    # because the user-lookup is already tenant-scoped upstream).
    for uid in mentioned_user_ids:
        notification = Notification(
            tenant_id=current_user.tenant_id,
            user_id=uid,
            type="mention",
            title=f"{current_user.full_name} sizi bir yorumda etiketledi",
            message=body.body[:200],
            entity_type=body.entity_type,
            entity_id=body.entity_id,
        )
        db.add(notification)

    await db.flush()
    await db.refresh(comment)
    return _serialize_comment(comment)


@router.delete("/{comment_id}", response_model=MessageResponse)
async def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete own comment only."""
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()

    if not comment:
        raise HTTPException(status_code=404, detail="Yorum bulunamadi")
    # Round-4 R4-TEN-18 — block cross-tenant delete (404 to avoid leaking).
    assert_same_tenant(comment, current_user, exception_cls=NotFoundException)

    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sadece kendi yorumunuzu silebilirsiniz")

    await db.delete(comment)
    await db.flush()
    return {"message": "Yorum silindi"}
