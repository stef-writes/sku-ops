"""Shared stock primitives — used across contexts that interact with inventory."""

from pydantic import BaseModel


class StockDecrement(BaseModel):
    """What inventory needs to know to reduce stock — no pricing or billing."""

    product_id: str
    sku: str
    name: str
    quantity: float
    unit: str = "each"
