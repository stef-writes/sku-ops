"""User and auth models."""
from typing import Optional

from pydantic import BaseModel

from kernel.entity import Entity

ROLES = ["admin", "warehouse_manager", "contractor"]


class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    role: str = "warehouse_manager"
    company: Optional[str] = None
    billing_entity: Optional[str] = None
    phone: Optional[str] = None
    organization_id: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    billing_entity: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


class UserLogin(BaseModel):
    email: str
    password: str


class User(Entity):
    email: str
    name: str
    role: str = "warehouse_manager"
    company: Optional[str] = None
    billing_entity: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool = True
    organization_id: Optional[str] = None
