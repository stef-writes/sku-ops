"""SKU (stock-keeping unit) domain models."""

from pydantic import BaseModel, field_validator

from shared.kernel.entity import AuditedEntity
from shared.kernel.units import ALLOWED_BASE_UNITS


def _validate_unit(v: str) -> str:
    v = (v or "each").lower().strip()
    if v not in ALLOWED_BASE_UNITS:
        raise ValueError(f"Unit must be one of: {sorted(ALLOWED_BASE_UNITS)}")
    return v


class SkuCreate(BaseModel):
    name: str
    description: str | None = ""
    price: float
    cost: float = 0.0
    quantity: float = 0
    min_stock: int = 5
    category_id: str
    product_id: str | None = None
    barcode: str | None = None
    vendor_barcode: str | None = None
    base_unit: str = "each"
    sell_uom: str = "each"
    pack_qty: int = 1
    purchase_uom: str = "each"
    purchase_pack_qty: int = 1

    @field_validator("base_unit", "sell_uom", "purchase_uom")
    @classmethod
    def valid_unit(cls, v: str) -> str:
        return _validate_unit(v)

    @field_validator("pack_qty", "purchase_pack_qty")
    @classmethod
    def valid_pack_qty(cls, v: int) -> int:
        if v < 1:
            raise ValueError("pack_qty must be at least 1")
        return v


class SkuUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: float | None = None
    cost: float | None = None
    quantity: float | None = None
    min_stock: int | None = None
    category_id: str | None = None
    product_id: str | None = None
    barcode: str | None = None
    vendor_barcode: str | None = None
    base_unit: str | None = None
    sell_uom: str | None = None
    pack_qty: int | None = None
    purchase_uom: str | None = None
    purchase_pack_qty: int | None = None

    @field_validator("base_unit", "sell_uom", "purchase_uom")
    @classmethod
    def valid_unit(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_unit(v)

    @field_validator("pack_qty", "purchase_pack_qty")
    @classmethod
    def valid_pack_qty(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("pack_qty must be at least 1")
        return v


class Sku(AuditedEntity):
    sku: str
    product_id: str = ""
    name: str
    description: str = ""
    price: float
    cost: float = 0.0
    quantity: float = 0
    min_stock: int = 5
    category_id: str = ""
    category_name: str = ""
    barcode: str | None = None
    vendor_barcode: str | None = None
    base_unit: str = "each"
    sell_uom: str = "each"
    pack_qty: int = 1
    purchase_uom: str = "each"
    purchase_pack_qty: int = 1

    @property
    def is_low_stock(self) -> bool:
        return self.quantity <= self.min_stock

    @property
    def margin_pct(self) -> float | None:
        if self.price <= 0:
            return None
        return round((self.price - self.cost) / self.price * 100, 2)

    def reorder_urgency(self, days_of_stock: float | None = None) -> str:
        if not self.is_low_stock:
            return "ok"
        if days_of_stock is None:
            return "no_velocity_data"
        if days_of_stock <= 3:
            return "critical"
        if days_of_stock <= 7:
            return "high"
        return "medium"
