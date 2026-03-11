"""Invoicing gateway port — provider-agnostic abstraction for accounting integrations."""

from dataclasses import dataclass
from typing import Protocol

from finance.domain.invoice import InvoiceWithDetails
from finance.domain.xero_settings import XeroSettings


@dataclass
class InvoiceSyncResult:
    success: bool
    external_id: str | None = None
    external_journal_id: str | None = None
    error: str | None = None


class InvoicingGateway(Protocol):
    """Port for accounting/invoicing integration.

    Implementations: XeroAdapter, StubXeroAdapter.
    """

    async def sync_invoice(
        self, invoice: InvoiceWithDetails, settings: XeroSettings
    ) -> InvoiceSyncResult: ...

    async def sync_po_receipt(
        self, po: dict, cost_total: float, settings: XeroSettings
    ) -> InvoiceSyncResult: ...

    async def sync_credit_note(
        self, credit_note: dict, settings: XeroSettings
    ) -> InvoiceSyncResult: ...

    async def fetch_invoice(self, xero_invoice_id: str, settings: XeroSettings) -> dict: ...

    async def fetch_credit_note(self, xero_credit_note_id: str, settings: XeroSettings) -> dict: ...

    async def list_tracking_categories(self, settings: XeroSettings) -> list[dict]: ...

    async def refresh_token(self, settings: XeroSettings) -> XeroSettings: ...

    async def get_tenants(self, access_token: str) -> list[dict]: ...
