"""Invoicing gateway port — provider-agnostic abstraction for accounting integrations."""
from dataclasses import dataclass
from typing import Optional, Protocol

from identity.domain.org_settings import OrgSettings


@dataclass
class InvoiceSyncResult:
    success: bool
    xero_invoice_id: Optional[str] = None
    xero_journal_id: Optional[str] = None
    error: Optional[str] = None


# Backward-compatible alias
XeroSyncResult = InvoiceSyncResult


class InvoicingGateway(Protocol):
    """Port for accounting/invoicing integration.

    Implementations: XeroAdapter, StubXeroAdapter.
    """

    async def sync_invoice(self, invoice: dict, settings: OrgSettings) -> InvoiceSyncResult:
        """Create or update an invoice in the external accounting system."""
        ...

    async def sync_po_receipt(self, po: dict, cost_total: float, settings: OrgSettings) -> InvoiceSyncResult:
        """Post a journal entry when a PO is received into stock."""
        ...

    async def list_tracking_categories(self, settings: OrgSettings) -> list[dict]:
        """List tracking categories available for the connected org."""
        ...

    async def refresh_token(self, settings: OrgSettings) -> OrgSettings:
        """Refresh the OAuth access token and return updated settings."""
        ...

    async def get_tenants(self, access_token: str) -> list[dict]:
        """List organisations (tenants) the token has access to."""
        ...


# Backward-compatible alias
XeroGateway = InvoicingGateway
