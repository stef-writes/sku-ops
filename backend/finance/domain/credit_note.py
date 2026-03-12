"""Credit note models — issued when materials are returned."""

from pydantic import BaseModel, Field

from shared.kernel.entity import AuditedEntity


class CreditNoteLineItem(BaseModel):
    id: str = ""
    credit_note_id: str = ""
    description: str = ""
    quantity: float = 1.0
    unit_price: float = 0.0
    amount: float = 0.0
    cost: float = 0.0
    product_id: str | None = None


class CreditNote(AuditedEntity):
    """An accounting credit issued against an invoice for returned goods."""

    credit_note_number: str = ""
    invoice_id: str | None = None
    return_id: str | None = None
    billing_entity: str = ""
    status: str = "draft"  # draft → applied → void
    subtotal: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    notes: str | None = None
    xero_credit_note_id: str | None = None
    xero_sync_status: str | None = None
    line_items: list[CreditNoteLineItem] = Field(default_factory=list)
    line_count: int = 0
