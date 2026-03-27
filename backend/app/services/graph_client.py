"""Microsoft Graph API client for Outlook email reading."""

import logging
from typing import Any

import httpx
import msal

from app.core.config import settings

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


class GraphEmailClient:
    """Microsoft Graph API client for Outlook email reading."""

    def __init__(self) -> None:
        self._app: msal.ConfidentialClientApplication | None = None

    def _get_msal_app(self) -> msal.ConfidentialClientApplication:
        if self._app is None:
            self._app = msal.ConfidentialClientApplication(
                client_id=settings.AZURE_CLIENT_ID,
                client_credential=settings.AZURE_CLIENT_SECRET,
                authority=f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}",
            )
        return self._app

    async def get_access_token(self) -> str:
        """Get OAuth2 token using MSAL client credentials flow."""
        app = self._get_msal_app()
        result = app.acquire_token_for_client(scopes=GRAPH_SCOPE)

        if "access_token" in result:
            return result["access_token"]

        error = result.get("error", "unknown")
        error_desc = result.get("error_description", "No description")
        logger.error("Failed to acquire token: %s - %s", error, error_desc)
        raise RuntimeError(f"Failed to acquire Graph API token: {error} - {error_desc}")

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def fetch_new_emails(
        self, delta_link: str | None = None
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch new emails using delta query.

        First call: gets all inbox messages.
        Subsequent calls: only new/changed since last delta_link.
        Returns (emails, new_delta_link).
        """
        token = await self.get_access_token()
        headers = self._headers(token)

        if delta_link:
            url = delta_link
        else:
            user_email = settings.GRAPH_USER_EMAIL
            url = (
                f"{GRAPH_BASE_URL}/users/{user_email}"
                f"/mailFolders/inbox/messages/delta"
                f"?$filter=isRead eq false"
                f"&$select=id,subject,from,body,receivedDateTime,isRead"
                f"&$top=50"
            )

        emails: list[dict[str, Any]] = []
        new_delta_link: str | None = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while url:
                try:
                    response = await client.get(url, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                except httpx.HTTPStatusError as exc:
                    logger.error(
                        "Graph API error %s: %s",
                        exc.response.status_code,
                        exc.response.text[:500],
                    )
                    raise
                except httpx.RequestError as exc:
                    logger.error("Graph API request failed: %s", exc)
                    raise

                emails.extend(data.get("value", []))

                # Follow pagination
                url = data.get("@odata.nextLink")

                # Capture delta link when pagination is done
                if "@odata.deltaLink" in data:
                    new_delta_link = data["@odata.deltaLink"]

        logger.info("Fetched %d emails from Graph API", len(emails))
        return emails, new_delta_link

    async def get_email_detail(self, message_id: str) -> dict[str, Any]:
        """Get full email details including body."""
        token = await self.get_access_token()
        headers = self._headers(token)
        user_email = settings.GRAPH_USER_EMAIL
        url = f"{GRAPH_BASE_URL}/users/{user_email}/messages/{message_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

    async def mark_as_read(self, message_id: str) -> None:
        """Mark email as read via PATCH."""
        token = await self.get_access_token()
        headers = self._headers(token)
        user_email = settings.GRAPH_USER_EMAIL
        url = f"{GRAPH_BASE_URL}/users/{user_email}/messages/{message_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(
                url, headers=headers, json={"isRead": True}
            )
            response.raise_for_status()
            logger.debug("Marked message %s as read", message_id)

    def is_internal_email(self, from_address: str) -> bool:
        """Check if email is from an internal domain (should be skipped)."""
        if not from_address:
            return False
        domain = from_address.rsplit("@", 1)[-1].lower()
        return domain in settings.internal_domains_list


# Module-level singleton
graph_client = GraphEmailClient()
