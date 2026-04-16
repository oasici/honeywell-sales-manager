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
from app.models.comment import Comment
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(prefix="/comments", tags=["Comments"])

MENTION_PATTERN = re.compile(r"@(\w+)")
ALLOWED_ENTITY_TYPES = {"opportunity", "customer", "lead"}


class CommentCreate(BaseModel):
    entity_type: str = Field(..., min_length=1)
    entity_id: int
    body: str = Field(..., min_length=1)
    parent_id: int | None = None


def _serialize_comment(comment: Comment) -> dict:
    """Convert a Comment ORM instance to a JSON-friendly dict."""
    return {
        "id": comment.id,
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


@router.get("/")
async def list_comments(
    entity_type: str = Query(...),
    entity_id: int = Query(...),
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List top-level comments with nested replies for an entity."""
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
    result = await db.execute(stmt)
    comments = result.scalars().all()
    return {"comments": [_serialize_comment(c) for c in comments]}


@router.post("/", status_code=201)
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

    # Parse @mentions from body text
    mentioned_usernames = MENTION_PATTERN.findall(body.body)
    mentioned_user_ids: list[int] = []

    for username in set(mentioned_usernames):
        user_result = await db.execute(
            select(User).where(User.full_name.ilike(f"%{username}%"))
        )
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
    )
    db.add(comment)
    await db.flush()

    # Create notifications for mentioned users
    for uid in mentioned_user_ids:
        notification = Notification(
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


@router.delete("/{comment_id}")
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

    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sadece kendi yorumunuzu silebilirsiniz")

    await db.delete(comment)
    await db.flush()
    return {"message": "Yorum silindi"}
