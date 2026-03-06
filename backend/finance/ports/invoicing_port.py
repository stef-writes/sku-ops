"""Invoicing gateway port — provider-agnostic abstraction for accounting integrations."""
from dataclasses import dataclass
from typing import List, Optional, Protocol

from finance.domain.invoice import InvoiceWithDetails
from identity.domain.org_settings import OrgSettings


@dataclass
class InvoiceSyncResult:
    success: bool
    xero_invoice_id: str | None = None
    xero_journal_id: str | None = None
    error: str | None = None


XeroSyncResult = InvoiceSyncResult


class InvoicingGateway(Protocol):
    """Port for accounting/invoicing integration.

    Implementations: XeroAdapter, StubXeroAdapter.
    """

    async def sync_invoice(self, invoice: InvoiceWithDetails, settings: OrgSettings) -> InvoiceSyncResult: ...

    async def sync_po_receipt(self, po: dict, cost_total: float, settings: OrgSettings) -> InvoiceSyncResult: ...

    async def sync_credit_note(self, credit_note: dict, settings: OrgSettings) -> InvoiceSyncResult: ...

    async def fetch_invoice(self, xero_invoice_id: str, settings: OrgSettings) -> dict: ...

    async def fetch_credit_note(self, xero_credit_note_id: str, settings: OrgSettings) -> dict: ...

    async def list_tracking_categories(self, settings: OrgSettings) -> list[dict]: ...

    async def refresh_token(self, settings: OrgSettings) -> OrgSettings: ...

    async def get_tenants(self, access_token: str) -> list[dict]: ...


XeroGateway = InvoicingGateway
