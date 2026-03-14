"""Invoice repository port — testable contract for invoice persistence."""

from typing import Any, Protocol, runtime_checkable

from finance.domain.invoice import Invoice, InvoiceWithDetails


@runtime_checkable
class InvoiceRepoPort(Protocol):
    async def insert(self, invoice: Invoice) -> InvoiceWithDetails | None: ...

    async def get_by_id(
        self,
        invoice_id: str,
        organization_id: str | None = None,
    ) -> InvoiceWithDetails | None: ...

    async def list_invoices(
        self,
        status: str | None = None,
        billing_entity: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 1000,
        organization_id: str | None = None,
    ) -> list[Invoice]: ...

    async def update_fields(
        self,
        invoice_id: str,
        updates: dict,
        organization_id: str | None = None,
    ) -> InvoiceWithDetails | None: ...

    async def mark_paid_for_withdrawal(self, withdrawal_id: str) -> None: ...

    async def update_invoice_totals(
        self,
        invoice_id: str,
        subtotal: float,
        tax: float,
        total: float,
    ) -> None: ...

    async def update_invoice_billing(
        self,
        invoice_id: str,
        billing_entity: str,
        contact_name: str,
        updated_at: str,
    ) -> None: ...

    async def update_invoice_fields_dynamic(
        self,
        invoice_id: str,
        fields: dict[str, Any],
    ) -> None: ...

    async def set_xero_invoice_id(
        self,
        invoice_id: str,
        xero_invoice_id: str,
        xero_cogs_journal_id: str | None = None,
        organization_id: str | None = None,
    ) -> None: ...

    async def set_xero_sync_status(
        self,
        invoice_id: str,
        status: str,
        organization_id: str | None = None,
    ) -> None: ...

    async def list_unsynced_invoices(self, organization_id: str) -> list[Invoice]: ...

    async def list_invoices_needing_reconciliation(self, organization_id: str) -> list[Invoice]: ...

    async def list_failed_invoices(self, organization_id: str) -> list[Invoice]: ...

    async def list_mismatch_invoices(self, organization_id: str) -> list[Invoice]: ...

    async def list_stale_cogs_invoices(self, organization_id: str) -> list[Invoice]: ...
