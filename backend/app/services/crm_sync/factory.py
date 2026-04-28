"""Adapter factory — pick a concrete adapter from a connection row."""

from __future__ import annotations

import json
from typing import Any

from app.models.v9_crm_sync import CrmConnection
from app.services.crm_sync.base import CRMConnectorProtocol, ConnectorError
from app.services.crm_sync.hubspot_adapter import HubSpotAdapter
from app.services.crm_sync.salesforce_adapter import SalesforceAdapter


def get_adapter(
    connection: CrmConnection, *, test_mode: bool = False
) -> CRMConnectorProtocol:
    """Build the concrete adapter for ``connection``.

    Test mode is forced when the connection lacks credentials so unit
    tests don't need network access.
    """
    creds: dict[str, Any] = {}
    if connection.credentials_json:
        try:
            creds = json.loads(connection.credentials_json)
        except json.JSONDecodeError:
            creds = {}

    provider = (connection.provider or "").lower()
    if provider == "salesforce":
        access_token = creds.get("access_token") or connection.oauth_token_encrypted or ""
        instance_url = (
            creds.get("instance_url")
            or connection.base_url
            or "https://login.salesforce.com"
        )
        return SalesforceAdapter(
            instance_url=instance_url,
            access_token=access_token,
            test_mode=test_mode or not access_token,
        )
    if provider == "hubspot":
        access_token = creds.get("access_token") or connection.oauth_token_encrypted or ""
        return HubSpotAdapter(
            access_token=access_token,
            test_mode=test_mode or not access_token,
        )
    raise ConnectorError(f"Unsupported CRM provider: {connection.provider}")
