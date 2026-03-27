"""Email sending service via Graph API or SMTP fallback."""

import base64
import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.graph_client import graph_client

logger = logging.getLogger(__name__)


async def send_quote_email(
    to_address: str,
    subject: str,
    body_html: str,
    pdf_path: str | None = None,
) -> bool:
    """Send email with optional PDF attachment.

    Uses Graph API sendMail if configured, otherwise SMTP fallback.
    Returns True on success, False on failure.
    """
    # Try Graph API first if configured
    if settings.AZURE_CLIENT_ID and settings.GRAPH_USER_EMAIL:
        try:
            return await _send_via_graph(to_address, subject, body_html, pdf_path)
        except Exception as exc:
            logger.warning("Graph API send failed, trying SMTP fallback: %s", exc)

    # SMTP fallback
    if settings.SMTP_HOST and settings.SMTP_USER:
        try:
            return await _send_via_smtp(to_address, subject, body_html, pdf_path)
        except Exception as exc:
            logger.error("SMTP send also failed: %s", exc)
            return False

    logger.error("No email sending method configured (Graph API or SMTP)")
    return False


async def _send_via_graph(
    to_address: str,
    subject: str,
    body_html: str,
    pdf_path: str | None = None,
) -> bool:
    """Send email via Microsoft Graph API."""
    token = await graph_client.get_access_token()
    user_email = settings.GRAPH_USER_EMAIL
    url = f"https://graph.microsoft.com/v1.0/users/{user_email}/sendMail"

    message: dict = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": body_html,
        },
        "toRecipients": [
            {"emailAddress": {"address": to_address}}
        ],
    }

    # Attach PDF if provided
    if pdf_path:
        attachment = _prepare_graph_attachment(pdf_path)
        if attachment:
            message["attachments"] = [attachment]

    payload = {"message": message, "saveToSentItems": True}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()

    logger.info("Email sent via Graph API to %s: %s", to_address, subject)
    return True


def _prepare_graph_attachment(pdf_path: str) -> dict | None:
    """Prepare a file attachment for Graph API sendMail."""
    path = Path(pdf_path)
    if not path.exists():
        logger.warning("Attachment file not found: %s", pdf_path)
        return None

    with open(path, "rb") as f:
        content_bytes = base64.b64encode(f.read()).decode("utf-8")

    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": path.name,
        "contentType": "application/pdf",
        "contentBytes": content_bytes,
    }


async def _send_via_smtp(
    to_address: str,
    subject: str,
    body_html: str,
    pdf_path: str | None = None,
) -> bool:
    """Send email via SMTP (synchronous, wrapped for async context)."""
    msg = MIMEMultipart("mixed")
    msg["From"] = settings.SMTP_FROM_ADDRESS or settings.SMTP_USER
    msg["To"] = to_address
    msg["Subject"] = subject

    # HTML body
    html_part = MIMEText(body_html, "html", "utf-8")
    msg.attach(html_part)

    # PDF attachment
    if pdf_path:
        path = Path(pdf_path)
        if path.exists():
            with open(path, "rb") as f:
                pdf_part = MIMEApplication(f.read(), _subtype="pdf")
                pdf_part.add_header(
                    "Content-Disposition", "attachment", filename=path.name
                )
                msg.attach(pdf_part)
        else:
            logger.warning("SMTP attachment file not found: %s", pdf_path)

    # Send
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)

    logger.info("Email sent via SMTP to %s: %s", to_address, subject)
    return True
