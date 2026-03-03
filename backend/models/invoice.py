"""Invoice models."""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class InvoiceLineItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid4()))
    invoice_id: str = ""
    description: str = ""
    quantity: float = 1.0
    unit_price: float = 0.0
    amount: float = 0.0
    cost: float = 0.0
    product_id: Optional[str] = None


class InvoiceCreate(BaseModel):
    """Payload for creating invoice from withdrawal IDs."""
    withdrawal_ids: List[str]


class InvoiceSyncXeroBulk(BaseModel):
    """Payload for bulk sync to Xero."""
    invoice_ids: List[str]


class InvoiceUpdate(BaseModel):
    """Payload for updating invoice."""
    billing_entity: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    tax: Optional[float] = None
    line_items: Optional[List[InvoiceLineItem]] = None


class Invoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid4()))
    invoice_number: str = ""
    billing_entity: str = ""
    contact_name: str = ""
    contact_email: str = ""
    status: str = "draft"  # draft, sent, paid
    subtotal: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    notes: Optional[str] = None
    xero_invoice_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InvoiceWithDetails(Invoice):
    """Invoice with line items and linked withdrawals."""
    line_items: List[InvoiceLineItem] = []
    withdrawal_ids: List[str] = []
