"""ERP integration package.

Public surface:
    ERPConnector        - Protocol every adapter implements.
    ERPCustomer / ERPProduct / ERPInvoice / ERPStockLevel - domain DTOs.
    ConnectorError      - base exception raised by adapters.
    build_connector     - factory from ORM ERPConnection row.
"""

from app.services.erp.base import (
    ConnectorError,
    ConnectorAuthError,
    ConnectorRateLimitError,
    ConnectorTimeoutError,
    ERPConnector,
    ERPCustomer,
    ERPInvoice,
    ERPInvoiceLine,
    ERPProduct,
    ERPStockLevel,
)
from app.services.erp.factory import build_connector

__all__ = [
    "ConnectorError",
    "ConnectorAuthError",
    "ConnectorRateLimitError",
    "ConnectorTimeoutError",
    "ERPConnector",
    "ERPCustomer",
    "ERPInvoice",
    "ERPInvoiceLine",
    "ERPProduct",
    "ERPStockLevel",
    "build_connector",
]
