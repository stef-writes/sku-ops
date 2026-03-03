"""Product models."""
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_BASE_UNITS = {
    "each", "case", "box", "pack", "bag", "roll", "kit",
    "gallon", "quart", "pint", "liter",
    "pound", "ounce",
    "foot", "meter", "yard",
    "sqft",
}


def _validate_unit(v: str) -> str:
    v = (v or "each").lower().strip()
    if v not in ALLOWED_BASE_UNITS:
        raise ValueError(f"Unit must be one of: {sorted(ALLOWED_BASE_UNITS)}")
    return v


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    price: float
    cost: float = 0.0
    quantity: int = 0
    min_stock: int = 5
    department_id: str
    vendor_id: Optional[str] = None
    original_sku: Optional[str] = None
    barcode: Optional[str] = None
    vendor_barcode: Optional[str] = None
    base_unit: str = "each"
    sell_uom: str = "each"
    pack_qty: int = 1

    @field_validator("base_unit", "sell_uom")
    @classmethod
    def valid_unit(cls, v: str) -> str:
        return _validate_unit(v)

    @field_validator("pack_qty")
    @classmethod
    def valid_pack_qty(cls, v: int) -> int:
        if v < 1:
            raise ValueError("pack_qty must be at least 1")
        return v


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    cost: Optional[float] = None
    quantity: Optional[int] = None
    min_stock: Optional[int] = None
    department_id: Optional[str] = None
    vendor_id: Optional[str] = None
    barcode: Optional[str] = None
    vendor_barcode: Optional[str] = None
    base_unit: Optional[str] = None
    sell_uom: Optional[str] = None
    pack_qty: Optional[int] = None

    @field_validator("base_unit", "sell_uom")
    @classmethod
    def valid_unit(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_unit(v)

    @field_validator("pack_qty")
    @classmethod
    def valid_pack_qty(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("pack_qty must be at least 1")
        return v


class Product(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid4()))
    sku: str
    name: str
    description: str = ""
    price: float
    cost: float = 0.0
    quantity: int = 0
    min_stock: int = 5
    department_id: str
    department_name: str = ""
    vendor_id: Optional[str] = None
    vendor_name: str = ""
    original_sku: Optional[str] = None
    barcode: Optional[str] = None
    vendor_barcode: Optional[str] = None
    base_unit: str = "each"
    sell_uom: str = "each"
    pack_qty: int = 1
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ExtractedProduct(BaseModel):
    name: str
    quantity: int = 1
    price: float
    original_sku: Optional[str] = None
    base_unit: Optional[str] = None
    sell_uom: Optional[str] = None
    pack_qty: Optional[int] = None
    cost: Optional[float] = None
    suggested_department: Optional[str] = None
    ordered_qty: Optional[int] = None
    delivered_qty: Optional[int] = None
