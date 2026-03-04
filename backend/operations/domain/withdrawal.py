"""Material withdrawal (POS) models."""
from typing import List, Optional

from pydantic import BaseModel

from kernel.entity import Entity


class WithdrawalItem(BaseModel):
    product_id: str
    sku: str
    name: str
    quantity: int
    price: float
    cost: float = 0.0
    subtotal: float
    unit: str = "each"  # sell_uom from product for display

    @property
    def computed_subtotal(self) -> float:
        return round(self.price * self.quantity, 2)


class MaterialWithdrawalCreate(BaseModel):
    items: List[WithdrawalItem]
    job_id: str
    service_address: str
    notes: Optional[str] = None


class MaterialWithdrawal(Entity):
    items: List[WithdrawalItem]
    job_id: str
    service_address: str
    notes: Optional[str] = None
    subtotal: float
    tax: float
    total: float
    cost_total: float
    contractor_id: str
    contractor_name: str = ""
    contractor_company: str = ""
    billing_entity: str = ""
    payment_status: str = "unpaid"
    invoice_id: Optional[str] = None
    paid_at: Optional[str] = None
    processed_by_id: str
    processed_by_name: str = ""

    def compute_totals(self, tax_rate: float = 0.08) -> None:
        """Calculate subtotal, tax, total, and cost_total from line items."""
        self.subtotal = sum(i.subtotal for i in self.items)
        self.cost_total = sum(i.cost * i.quantity for i in self.items)
        self.tax = round(self.subtotal * tax_rate, 2)
        self.total = round(self.subtotal + self.tax, 2)
