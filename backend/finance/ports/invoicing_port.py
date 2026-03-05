"""Invoicing gateway port — provider-agnostic abstraction for accounting integrations."""
from dataclasses import dataclass
from typing import List, Optional, Protocol

from finance.domain.invoice import InvoiceWithDetails
from identity.domain.org_settings import OrgSettings


@dataclass
class InvoiceSyncResult:
    success: bool
    xero_invoice_id: Optional[str] = None
    xero_journal_id: Optional[str] = None
    error: Optional[str] = None


XeroSyncResult = InvoiceSyncResult


class InvoicingGateway(Protocol):
    """Port for accounting/invoicing integration.

    Implementations: XeroAdapter, StubXeroAdapter.
    """

    async def sync_invoice(self, invoice: InvoiceWithDetails, settings: OrgSettings) -> InvoiceSyncResult: ...

    async def sync_po_receipt(self, po: dict, cost_total: float, settings: OrgSettings) -> InvoiceSyncResult: ...

    async def list_tracking_categories(self, settings: OrgSettings) -> List[dict]: ...

    async def refresh_token(self, settings: OrgSettings) -> OrgSettings: ...

    async def get_tenants(self, access_token: str) -> List[dict]: ...


XeroGateway = InvoicingGateway
