"""User and auth models."""
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

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


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid4()))
    email: str
    name: str
    role: str = "warehouse_manager"
    company: Optional[str] = None
    billing_entity: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool = True
    organization_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
