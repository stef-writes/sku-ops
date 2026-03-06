"""Department models."""
from typing import Optional

from pydantic import BaseModel

from kernel.entity import Entity


class DepartmentCreate(BaseModel):
    name: str
    code: str
    description: str | None = ""


class Department(Entity):
    name: str
    code: str
    description: str = ""
    product_count: int = 0
