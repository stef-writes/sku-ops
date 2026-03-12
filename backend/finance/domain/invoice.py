"""Invoice models."""

from datetime import datetime, timedelta
from typing import ClassVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from shared.kernel.entity import AuditedEntity
from shared.kernel.types import LineItem, round_money

PAYMENT_TERMS_DAYS: dict[str, int] = {
    "due_on_receipt": 0,
    "net_15": 15,
    "net_30": 30,
    "net_45": 45,
    "net_60": 60,
    "net_90": 90,
}


def compute_due_date(invoice_date: str, payment_terms: str) -> str:
    """Return ISO due-date string from invoice_date + payment_terms."""
    days = PAYMENT_TERMS_DAYS.get(payment_terms, 30)
    dt = datetime.fromisoformat(invoice_date)
    due = dt + timedelta(days=days)
    return due.isoformat()


class InvoiceLineItem(BaseModel):
    """A line on an accounting document.

    Uses accounting-standard field names (unit_price, amount) rather than
    the operational names on LineItem (unit_price, subtotal). The underlying
    data is the same — unit_price * quantity = amount.
    """

    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid4()))
    invoice_id: str = ""
    description: str = ""
    quantity: float = 1.0
    unit_price: float = 0.0
    amount: float = 0.0
    cost: float = 0.0
    sell_cost: float = 0.0
    unit: str | None = None
    product_id: str | None = None
    job_id: str | None = None

    @property
    def margin(self) -> float:
        return round_money(self.amount - (self.cost * self.quantity))

    @property
    def margin_pct(self) -> float | None:
        if self.amount <= 0:
            return None
        return round(self.margin / self.amount * 100, 2)

    @classmethod
    def from_line_item(
        cls,
        item: LineItem,
        invoice_id: str = "",
        job_id: str | None = None,
    ) -> "InvoiceLineItem":
        """Convert a universal LineItem to an InvoiceLineItem."""
        return cls(
            invoice_id=invoice_id,
            description=item.name,
            quantity=float(item.quantity),
            unit_price=item.unit_price,
            amount=item.subtotal,
            cost=item.cost,
            product_id=item.product_id,
            job_id=job_id,
        )


class InvoiceCreate(BaseModel):
    """Payload for creating invoice from withdrawal IDs."""

    withdrawal_ids: list[str]


class InvoiceSyncXeroBulk(BaseModel):
    """Payload for bulk sync to Xero."""

    invoice_ids: list[str]


class InvoiceUpdate(BaseModel):
    """Payload for updating invoice."""

    billing_entity: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    status: str | None = None
    notes: str | None = None
    tax: float | None = None
    tax_rate: float | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    payment_terms: str | None = None
    billing_address: str | None = None
    po_reference: str | None = None
    line_items: list[InvoiceLineItem] | None = None


class Invoice(AuditedEntity):
    invoice_number: str = ""
    billing_entity: str = ""
    contact_name: str = ""
    contact_email: str = ""
    status: str = "draft"
    subtotal: float = 0.0
    tax: float = 0.0
    tax_rate: float = 0.0
    total: float = 0.0
    amount_credited: float = 0.0
    notes: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    payment_terms: str = "net_30"
    billing_address: str = ""
    po_reference: str = ""
    currency: str = "USD"
    approved_by_id: str | None = None
    approved_at: str | None = None
    xero_invoice_id: str | None = None
    xero_cogs_journal_id: str | None = None
    xero_sync_status: str | None = None
    deleted_at: str | None = None
    withdrawal_count: int = 0
    line_count: int = 0

    ALLOWED_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        "draft": {"approved", "sent", "paid"},
        "approved": {"sent", "paid"},
        "sent": {"paid"},
        "paid": set(),
    }

    def can_transition_to(self, target: str) -> bool:
        return target in self.ALLOWED_TRANSITIONS.get(self.status, set())

    @property
    def balance_due(self) -> float:
        return round_money(self.total - self.amount_credited)


class InvoiceWithDetails(Invoice):
    """Invoice with line items and linked withdrawals."""

    line_items: list[InvoiceLineItem] = Field(default_factory=list)
    withdrawal_ids: list[str] = Field(default_factory=list)


class InvoiceCreated(BaseModel):
    """Result of successful invoice creation."""

    model_config = ConfigDict(frozen=True)
    invoice: InvoiceWithDetails
    linked_withdrawal_ids: list[str]
