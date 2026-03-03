"""Xero gateway port — abstraction for Xero API interactions."""
from dataclasses import dataclass
from typing import Optional, Protocol

from models.org_settings import OrgSettings


@dataclass
class XeroSyncResult:
    success: bool
    xero_invoice_id: Optional[str] = None
    xero_journal_id: Optional[str] = None
    error: Optional[str] = None


class XeroGateway(Protocol):
    """Port for Xero integration. Implementations: XeroAdapter, StubXeroAdapter."""

    async def sync_invoice(self, invoice: dict, settings: OrgSettings) -> XeroSyncResult:
        """Create or update a Xero invoice from an sku-ops invoice dict.
        Posts a COGS manual journal alongside the invoice."""
        ...

    async def sync_po_receipt(self, po: dict, cost_total: float, settings: OrgSettings) -> XeroSyncResult:
        """Post a Dr Inventory / Cr AP journal when a PO is received into stock."""
        ...

    async def list_tracking_categories(self, settings: OrgSettings) -> list[dict]:
        """List Xero tracking categories available for the connected org."""
        ...

    async def refresh_token(self, settings: OrgSettings) -> OrgSettings:
        """Refresh the Xero OAuth access token and return updated settings."""
        ...

    async def get_tenants(self, access_token: str) -> list[dict]:
        """List Xero organisations (tenants) the token has access to."""
        ...
