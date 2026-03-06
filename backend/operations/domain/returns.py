"""Return models — reversing all or part of a material withdrawal."""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from kernel.entity import AuditedEntity
from kernel.types import round_money


class ReturnReason(str, Enum):
    WRONG_ITEM = "wrong_item"
    DEFECTIVE = "defective"
    OVERORDER = "overorder"
    JOB_CANCELLED = "job_cancelled"
    OTHER = "other"


class ReturnItem(BaseModel):
    """A line on a return — references the original withdrawal item."""
    model_config = ConfigDict(extra="ignore")

    product_id: str
    sku: str
    name: str
    quantity: float
    unit_price: float = 0.0
    cost: float = 0.0
    unit: str = "each"
    reason: ReturnReason = ReturnReason.OTHER
    notes: str = ""

    @property
    def refund_amount(self) -> float:
        return round_money(self.unit_price * self.quantity)

    @property
    def cost_total(self) -> float:
        return round_money(self.cost * self.quantity)


class ReturnCreate(BaseModel):
    """API payload to create a return."""
    withdrawal_id: str
    items: list[ReturnItem]
    reason: ReturnReason = ReturnReason.OTHER
    notes: str | None = None


class MaterialReturn(AuditedEntity):
    """A return against a previous withdrawal."""
    withdrawal_id: str
    contractor_id: str
    contractor_name: str = ""
    billing_entity: str = ""
    job_id: str = ""
    items: list[ReturnItem]
    subtotal: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    cost_total: float = 0.0
    reason: ReturnReason = ReturnReason.OTHER
    notes: str | None = None
    credit_note_id: str | None = None
    processed_by_id: str = ""
    processed_by_name: str = ""

    def compute_totals(self, tax_rate: float = 0.10) -> None:
        self.subtotal = round_money(sum(i.refund_amount for i in self.items))
        self.cost_total = round_money(sum(i.cost_total for i in self.items))
        self.tax = round_money(self.subtotal * tax_rate)
        self.total = round_money(self.subtotal + self.tax)
