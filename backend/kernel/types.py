"""Universal value objects and cross-cutting types.

These are the atoms that every domain module shares. If you're moving
a quantity of a product through the system, you use LineItem. If you're
identifying the authenticated caller, you use CurrentUser.
"""
from decimal import ROUND_HALF_EVEN, Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, field_validator


def round_money(value: float) -> float:
    """Round to 2 decimal places using banker's rounding (IEEE 754 standard).

    Uses Python's Decimal for exact intermediate arithmetic, then converts
    back to float for storage.  This avoids the rare half-penny drift that
    plain ``round(x, 2)`` can introduce on IEEE 754 boundary values.
    """
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


class LineItem(BaseModel):
    """The universal atom: a quantity of a known product in a transaction.

    Used by withdrawals, material requests, and as the conversion target
    for PO items when they are received into inventory.
    """
    model_config = ConfigDict(extra="ignore")

    product_id: str
    sku: str
    name: str
    quantity: float
    unit_price: float = Field(
        default=0.0,
        validation_alias=AliasChoices("unit_price", "price"),
    )
    cost: float = 0.0
    unit: str = "each"
    sell_uom: str = "each"
    sell_cost: float = 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def subtotal(self) -> float:
        return round_money(self.unit_price * self.quantity)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cost_total(self) -> float:
        return round_money(self.cost * self.quantity)


class Address(BaseModel):
    """Structured address value object."""
    model_config = ConfigDict(extra="ignore")
    line1: str = ""
    line2: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = "US"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display(self) -> str:
        parts = [p for p in [self.line1, self.line2, self.city, self.state, self.postal_code] if p]
        return ", ".join(parts)


class CurrentUser(BaseModel):
    """Authenticated user context threaded through every request."""
    model_config = ConfigDict(extra="ignore")

    id: str
    email: str
    name: str
    role: str
    organization_id: str = "default"
    company: str = ""
    billing_entity: str = ""
    phone: str = ""

    @field_validator("company", "billing_entity", "phone", mode="before")
    @classmethod
    def coerce_none_to_empty(cls, v):
        return v if v is not None else ""
