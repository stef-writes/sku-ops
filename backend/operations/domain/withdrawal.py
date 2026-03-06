"""Material withdrawal (POS) models."""
from typing import List, Optional

from pydantic import BaseModel

from kernel.entity import Entity
from kernel.types import LineItem, round_money


class WithdrawalItem(LineItem):
    """A line item on a material withdrawal — extends the universal LineItem."""


class MaterialWithdrawalCreate(BaseModel):
    items: list[WithdrawalItem]
    job_id: str
    service_address: str
    notes: str | None = None


class MaterialWithdrawal(Entity):
    items: list[WithdrawalItem]
    job_id: str
    service_address: str
    notes: str | None = None
    subtotal: float
    tax: float
    tax_rate: float = 0.0
    total: float
    cost_total: float
    contractor_id: str
    contractor_name: str = ""
    contractor_company: str = ""
    billing_entity: str = ""
    billing_entity_id: str | None = None
    payment_status: str = "unpaid"
    invoice_id: str | None = None
    paid_at: str | None = None
    processed_by_id: str
    processed_by_name: str = ""

    def compute_totals(self, tax_rate: float = 0.10) -> None:
        """Calculate subtotal, tax, total, and cost_total from line items."""
        self.tax_rate = tax_rate
        self.subtotal = round_money(sum(i.subtotal for i in self.items))
        self.cost_total = round_money(sum(i.cost_total for i in self.items))
        self.tax = round_money(self.subtotal * tax_rate)
        self.total = round_money(self.subtotal + self.tax)
