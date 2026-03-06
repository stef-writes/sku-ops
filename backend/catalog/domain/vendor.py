"""Vendor models."""
from typing import Optional

from pydantic import BaseModel

from kernel.entity import Entity


class VendorCreate(BaseModel):
    name: str
    contact_name: str | None = ""
    email: str | None = ""
    phone: str | None = ""
    address: str | None = ""


class Vendor(Entity):
    name: str
    contact_name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    product_count: int = 0
