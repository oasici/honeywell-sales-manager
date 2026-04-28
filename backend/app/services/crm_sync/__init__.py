"""CRM sync platform (V9).

Bidirectional Salesforce / HubSpot / Dynamics adapter layer that closes
the V2 Epic C2 scope. Adapters share a common Protocol so the
orchestrator drives them uniformly.

Public exports:
- ``CRMConnectorProtocol`` — adapter interface
- ``get_adapter(provider)`` — factory
- ``run_sync_job`` — orchestrator entry
"""

from app.services.crm_sync.base import (
    CRMConnectorProtocol,
    ExternalRecord,
    SyncResult,
)
from app.services.crm_sync.factory import get_adapter
from app.services.crm_sync.orchestrator import run_sync_job

__all__ = [
    "CRMConnectorProtocol",
    "ExternalRecord",
    "SyncResult",
    "get_adapter",
    "run_sync_job",
]
