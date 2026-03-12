"""Department models."""

from pydantic import BaseModel

from shared.kernel.entity import Entity


class DepartmentCreate(BaseModel):
    name: str
    code: str
    description: str | None = ""


class Department(Entity):
    name: str
    code: str
    description: str = ""
    product_count: int = 0
