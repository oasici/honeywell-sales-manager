"""Factory that instantiates the right adapter from an ``ERPConnection`` row."""

from __future__ import annotations

from app.core.crypto import decrypt_json
from app.models.erp import ERPConnection
from app.services.erp.base import ERPConnector


def build_connector(connection: ERPConnection) -> ERPConnector:
    """Dispatch on ``connection.type`` and return a ready-to-use adapter.

    Credentials are decrypted here so adapters only see plain values.
    """
    creds = decrypt_json(connection.credentials_encrypted) if connection.credentials_encrypted else {}

    if connection.type == "parasut":
        from app.services.erp.adapters.parasut import ParasutConnector

        return ParasutConnector(endpoint=connection.endpoint, credentials=creds)

    if connection.type == "logo":
        from app.services.erp.adapters.logo import LogoConnector

        return LogoConnector(endpoint=connection.endpoint, credentials=creds)

    if connection.type == "sap_b1":
        from app.services.erp.adapters.sap_b1 import SAPBusinessOneConnector

        return SAPBusinessOneConnector(endpoint=connection.endpoint, credentials=creds)

    if connection.type == "webhook":
        from app.services.erp.adapters.webhook import GenericWebhookConnector

        return GenericWebhookConnector(endpoint=connection.endpoint, credentials=creds)

    raise ValueError(f"Unsupported ERP connector type: {connection.type!r}")
