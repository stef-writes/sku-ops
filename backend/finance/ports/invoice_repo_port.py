"""Invoice repository port — testable contract for invoice persistence."""
from typing import List, Optional, Protocol, Union, runtime_checkable

from finance.domain.invoice import Invoice, InvoiceLineItem


@runtime_checkable
class InvoiceRepoPort(Protocol):

    async def insert(self, invoice: Invoice | dict) -> dict | None: ...

    async def get_by_id(
        self, invoice_id: str, organization_id: str | None = None,
    ) -> dict | None: ...

    async def list_invoices(
        self,
        status: str | None = None,
        billing_entity: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 1000,
        organization_id: str | None = None,
    ) -> list[dict]: ...

    async def update(
        self,
        invoice_id: str,
        billing_entity: str | None = None,
        contact_name: str | None = None,
        contact_email: str | None = None,
        status: str | None = None,
        notes: str | None = None,
        tax: float | None = None,
        line_items: list[InvoiceLineItem] | None = None,
    ) -> dict | None: ...

    async def add_withdrawals(
        self, invoice_id: str, withdrawal_ids: list[str],
        organization_id: str | None = None,
    ) -> dict | None: ...

    async def create_from_withdrawals(
        self, withdrawal_ids: list[str],
        organization_id: str | None = None, conn=None,
    ) -> dict: ...

    async def mark_paid_for_withdrawal(self, withdrawal_id: str) -> None: ...

    async def set_xero_invoice_id(
        self, invoice_id: str, xero_invoice_id: str,
    ) -> None: ...

    async def delete_draft(self, invoice_id: str) -> bool: ...
