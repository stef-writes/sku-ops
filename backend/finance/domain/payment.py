"""Payment domain models — first-class record of money received."""

from enum import StrEnum

from pydantic import BaseModel, Field

from shared.kernel.entity import AuditedEntity


class PaymentMethod(StrEnum):
    BANK_TRANSFER = "bank_transfer"
    CHECK = "check"
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    OTHER = "other"


class Payment(AuditedEntity):
    """A payment received against one or more withdrawals/invoices."""

    invoice_id: str | None = None
    billing_entity_id: str | None = None
    amount: float
    method: str = PaymentMethod.BANK_TRANSFER
    reference: str = ""
    payment_date: str
    notes: str | None = None
    recorded_by_id: str
    xero_payment_id: str | None = None
    withdrawal_ids: list[str] = Field(default_factory=list)


class PaymentCreate(BaseModel):
    withdrawal_ids: list[str] = []
    invoice_id: str | None = None
    amount: float | None = None
    method: str = PaymentMethod.BANK_TRANSFER
    reference: str = ""
    payment_date: str | None = None
    notes: str | None = None
