"""Universal value objects and cross-cutting types.

These are the atoms that every domain module shares. If you're moving
a quantity of a product through the system, you use LineItem. If you're
identifying the authenticated caller, you use CurrentUser.
"""
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, field_validator


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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def subtotal(self) -> float:
        return round(self.unit_price * self.quantity, 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cost_total(self) -> float:
        return round(self.cost * self.quantity, 2)


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
