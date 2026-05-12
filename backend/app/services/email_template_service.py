"""Email template rendering and sending service."""

from __future__ import annotations

import json
import logging
import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.email_template import EmailTemplate
from app.services.email_sender import send_quote_email

logger = logging.getLogger(__name__)

AVAILABLE_VARIABLES = [
    "customer_name",
    "company",
    "quote_number",
    "rep_name",
    "rep_email",
    "date",
    "amount",
    "product_name",
]

VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class EmailTemplateService:
    """Manage email templates: CRUD, rendering, and sending."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_templates(
        self, user_id: int, tenant_id: int | None = None
    ) -> list[EmailTemplate]:
        """Return templates owned by user or shared within the tenant.

        Round-12 R12-AUTH-1 — ``is_shared=True`` templates were
        globally readable pre-fix. The query now additionally filters
        on ``EmailTemplate.tenant_id`` when the caller has one, so
        is_shared is bounded to the caller's tenant rather than the
        whole deployment.
        """
        conditions = [
            or_(
                EmailTemplate.created_by == user_id,
                EmailTemplate.is_shared.is_(True),
            )
        ]
        if tenant_id is not None:
            conditions.append(EmailTemplate.tenant_id == tenant_id)
        result = await self.db.execute(
            select(EmailTemplate)
            .where(*conditions)
            .order_by(EmailTemplate.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_template(
        self, template_id: int, tenant_id: int | None = None
    ) -> EmailTemplate:
        """Fetch a single template by id, scoped to tenant.

        Round-12 R12-AUTH-1 — pre-fix had no tenant filter at all.
        Cross-tenant access maps to 404 (per CLAUDE.md convention).
        """
        conditions = [EmailTemplate.id == template_id]
        if tenant_id is not None:
            conditions.append(EmailTemplate.tenant_id == tenant_id)
        result = await self.db.execute(
            select(EmailTemplate).where(*conditions)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise NotFoundException("Email sablonu bulunamadi")
        return template

    async def create_template(
        self,
        name: str,
        subject: str,
        body_html: str,
        user_id: int,
        variables_json: str | None = None,
        category: str | None = None,
        is_shared: bool = False,
        tenant_id: int | None = None,
    ) -> EmailTemplate:
        """Create a new email template scoped to the caller's tenant."""
        template = EmailTemplate(
            name=name,
            subject=subject,
            body_html=body_html,
            variables_json=variables_json,
            category=category,
            is_shared=is_shared,
            created_by=user_id,
            tenant_id=tenant_id,
        )
        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def update_template(
        self,
        template_id: int,
        user_id: int,
        tenant_id: int | None = None,
        **fields: object,
    ) -> EmailTemplate:
        """Update template fields. Only the owner can update; cross-tenant 404s."""
        template = await self.get_template(template_id, tenant_id=tenant_id)
        if template.created_by != user_id:
            raise NotFoundException("Bu sablonu duzenleme yetkiniz yok")

        allowed_fields = {
            "name", "subject", "body_html", "variables_json",
            "category", "is_shared",
        }
        for key, value in fields.items():
            if key in allowed_fields and value is not None:
                setattr(template, key, value)

        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def delete_template(
        self, template_id: int, user_id: int, tenant_id: int | None = None
    ) -> None:
        """Delete template. Only the owner can delete; cross-tenant 404s."""
        template = await self.get_template(template_id, tenant_id=tenant_id)
        if template.created_by != user_id:
            raise NotFoundException("Bu sablonu silme yetkiniz yok")
        await self.db.delete(template)
        await self.db.flush()

    async def render(
        self, template_id: int, context: dict[str, str],
    ) -> tuple[str, str]:
        """Render template with variable substitution.

        Returns (subject, body_html) with ``{{variable}}`` patterns
        replaced by the corresponding context values.
        """
        template = await self.get_template(template_id)

        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            return context.get(var_name, match.group(0))

        rendered_subject = VARIABLE_PATTERN.sub(_replace, template.subject)
        rendered_body = VARIABLE_PATTERN.sub(_replace, template.body_html)
        return rendered_subject, rendered_body

    async def send_rendered(
        self,
        template_id: int,
        to_email: str,
        context: dict[str, str],
        user_id: int,
    ) -> bool:
        """Render a template and send via the existing email sender."""
        subject, body_html = await self.render(template_id, context)
        logger.info(
            "Sending rendered template %d to %s by user %d",
            template_id, to_email, user_id,
        )
        return await send_quote_email(to_email, subject, body_html)
