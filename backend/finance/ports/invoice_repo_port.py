"""Invoice repository port — testable contract for invoice persistence."""
from typing import List, Optional, Protocol, runtime_checkable

from finance.domain.invoice import Invoice, InvoiceLineItem


@runtime_checkable
class InvoiceRepoPort(Protocol):

    async def insert(self, invoice: Invoice) -> dict: ...

    async def get_by_id(
        self, invoice_id: str, organization_id: Optional[str] = None,
    ) -> Optional[dict]: ...

    async def list_invoices(
        self,
        status: Optional[str] = None,
        billing_entity: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000,
        organization_id: Optional[str] = None,
    ) -> List[dict]: ...

    async def update(
        self,
        invoice_id: str,
        billing_entity: Optional[str] = None,
        contact_name: Optional[str] = None,
        contact_email: Optional[str] = None,
        status: Optional[str] = None,
        notes: Optional[str] = None,
        tax: Optional[float] = None,
        line_items: Optional[List[InvoiceLineItem]] = None,
    ) -> Optional[dict]: ...

    async def add_withdrawals(
        self, invoice_id: str, withdrawal_ids: List[str],
        organization_id: Optional[str] = None,
    ) -> Optional[dict]: ...

    async def create_from_withdrawals(
        self, withdrawal_ids: List[str],
        organization_id: Optional[str] = None, conn=None,
    ) -> dict: ...

    async def mark_paid_for_withdrawal(self, withdrawal_id: str) -> None: ...

    async def set_xero_invoice_id(
        self, invoice_id: str, xero_invoice_id: str,
    ) -> None: ...

    async def delete_draft(self, invoice_id: str) -> bool: ...
