"""Vendor models."""
from typing import Optional

from pydantic import BaseModel

from kernel.entity import Entity


class VendorCreate(BaseModel):
    name: str
    contact_name: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    address: Optional[str] = ""


class Vendor(Entity):
    name: str
    contact_name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    product_count: int = 0
