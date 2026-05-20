"""Email template CRUD and send endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import ForbiddenException
from app.models.user import User
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.email_template import EmailTemplateResponse
from app.services.email_template_service import (
    AVAILABLE_VARIABLES,
    EmailTemplateService,
)

router = APIRouter(prefix="/email-templates", tags=["Email Templates"])


# ── Pydantic schemas ──


class EmailTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    subject: str = Field(..., min_length=1, max_length=500)
    body_html: str = Field(..., min_length=1)
    variables_json: str | None = None
    category: str | None = Field(None, max_length=50)
    is_shared: bool = False


class EmailTemplateUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    subject: str | None = Field(None, max_length=500)
    body_html: str | None = None
    variables_json: str | None = None
    category: str | None = Field(None, max_length=50)
    is_shared: bool | None = None


class EmailTemplateSend(BaseModel):
    to_email: str
    context: dict[str, str] = Field(default_factory=dict)


# ── Helpers ──


def _serialize(template: object) -> dict:
    """Convert an EmailTemplate ORM instance to a JSON-safe dict."""
    return {
        "id": template.id,  # type: ignore[attr-defined]
        "name": template.name,  # type: ignore[attr-defined]
        "subject": template.subject,  # type: ignore[attr-defined]
        "body_html": template.body_html,  # type: ignore[attr-defined]
        "variables_json": template.variables_json,  # type: ignore[attr-defined]
        "category": template.category,  # type: ignore[attr-defined]
        "is_shared": template.is_shared,  # type: ignore[attr-defined]
        "created_by": template.created_by,  # type: ignore[attr-defined]
        "created_at": (
            template.created_at.isoformat()  # type: ignore[attr-defined]
            if template.created_at  # type: ignore[attr-defined]
            else None
        ),
        "updated_at": (
            template.updated_at.isoformat()  # type: ignore[attr-defined]
            if template.updated_at  # type: ignore[attr-defined]
            else None
        ),
    }


# ── Endpoints ──


@router.get("/variables", response_model=dict)
async def get_available_variables(
    current_user: User = Depends(get_current_user),
):
    """Return the list of available template variables."""
    return {"variables": AVAILABLE_VARIABLES}


@router.get("/", response_model=PaginatedResponse[EmailTemplateResponse])
async def list_email_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List email templates visible to the current user (own + shared).

    Round-12 R12-AUTH-1 — shared templates are now bounded to the
    caller's tenant via ``tenant_id``.
    """
    svc = EmailTemplateService(db)
    tenant_id = getattr(current_user, "tenant_id", None)
    templates = await svc.list_templates(current_user.id, tenant_id=tenant_id)
    items = [_serialize(t) for t in templates]
    total = len(items)
    # Round-12 R12-API-1 — canonical pagination envelope.
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
    }


@router.post("/", status_code=201, response_model=EmailTemplateResponse)
async def create_email_template(
    body: EmailTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new email template scoped to caller's tenant."""
    svc = EmailTemplateService(db)
    template = await svc.create_template(
        name=body.name,
        subject=body.subject,
        body_html=body.body_html,
        user_id=current_user.id,
        variables_json=body.variables_json,
        category=body.category,
        is_shared=body.is_shared,
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    return _serialize(template)


@router.put("/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: int,
    body: EmailTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an email template (owner only; cross-tenant 404s)."""
    svc = EmailTemplateService(db)
    template = await svc.update_template(
        template_id,
        current_user.id,
        tenant_id=getattr(current_user, "tenant_id", None),
        **body.model_dump(exclude_none=True),
    )
    return _serialize(template)


@router.delete("/{template_id}", response_model=MessageResponse)
async def delete_email_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an email template (owner only; cross-tenant 404s)."""
    svc = EmailTemplateService(db)
    await svc.delete_template(
        template_id,
        current_user.id,
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    return {"message": "Sablon silindi", "id": template_id}


@router.post("/{template_id}/send", response_model=MessageResponse)
async def send_email_template(
    template_id: int,
    body: EmailTemplateSend,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Render a template with context variables and send via email."""
    svc = EmailTemplateService(db)
    success = await svc.send_rendered(
        template_id=template_id,
        to_email=body.to_email,
        context=body.context,
        user_id=current_user.id,
    )
    if success:
        return {"message": "Email gonderildi", "to": body.to_email}
    raise ForbiddenException("Email gonderilemedi. Email ayarlarini kontrol edin.")
