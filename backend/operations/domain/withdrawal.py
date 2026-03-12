"""Material withdrawal (POS) models."""

from dataclasses import dataclass

from pydantic import BaseModel, field_validator

from shared.kernel.entity import Entity
from shared.kernel.types import LineItem, round_money


@dataclass(frozen=True)
class ContractorContext:
    """Typed snapshot of contractor identity used when creating a withdrawal.

    Replaces the raw ``dict`` previously threaded through the application layer.
    Using a dataclass ensures ``id`` is always present and prevents silent None
    propagation as ``contractor_id``.
    """

    id: str
    name: str = ""
    company: str = ""
    billing_entity: str = ""
    billing_entity_id: str | None = None


class WithdrawalItem(LineItem):
    """A line item on a material withdrawal — extends the universal LineItem."""


class MaterialWithdrawalCreate(BaseModel):
    items: list[WithdrawalItem]
    job_id: str
    service_address: str
    notes: str | None = None

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one item is required")
        return v


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
