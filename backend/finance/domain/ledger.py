"""Financial ledger — immutable record of every monetary event.

Mirrors the stock_transactions pattern but for dollars instead of units.
Every withdrawal, return, PO receipt, stock adjustment, and payment writes
entries here at event time. Reports read from this table — they never
recompute from operational data.
"""

from enum import StrEnum

from shared.kernel.entity import Entity


class Account(StrEnum):
    REVENUE = "revenue"
    COGS = "cogs"
    TAX_COLLECTED = "tax_collected"
    INVENTORY = "inventory"
    ACCOUNTS_RECEIVABLE = "accounts_receivable"
    ACCOUNTS_PAYABLE = "accounts_payable"
    SHRINKAGE = "shrinkage"
    DAMAGE = "damage"


class ReferenceType(StrEnum):
    WITHDRAWAL = "withdrawal"
    RETURN = "return"
    PO_RECEIPT = "po_receipt"
    ADJUSTMENT = "adjustment"
    PAYMENT = "payment"
    CREDIT_NOTE = "credit_note"


class FinancialEntry(Entity):
    """One line in the financial ledger — always created, never mutated."""

    journal_id: str | None = None
    account: Account
    amount: float
    quantity: float | None = None
    unit: str | None = None
    unit_cost: float | None = None
    department: str | None = None
    job_id: str | None = None
    billing_entity: str | None = None
    contractor_id: str | None = None
    vendor_name: str | None = None
    product_id: str | None = None
    performed_by_user_id: str | None = None
    reference_type: ReferenceType
    reference_id: str
