"""Department repository port — testable contract for department persistence."""
from typing import List, Optional, Protocol, runtime_checkable

from catalog.domain.department import Department


@runtime_checkable
class DepartmentRepoPort(Protocol):

    async def list_all(self, organization_id: str | None = None) -> list[dict]: ...

    async def get_by_id(
        self, dept_id: str, organization_id: str | None = None,
    ) -> dict | None: ...

    async def get_by_code(
        self, code: str, organization_id: str | None = None,
    ) -> dict | None: ...

    async def insert(self, department: Department, conn=None) -> None: ...

    async def update(
        self, dept_id: str, name: str, description: str, conn=None,
    ) -> dict | None: ...

    async def count_products_by_department(self, dept_id: str) -> int: ...

    async def delete(self, dept_id: str) -> int: ...

    async def increment_product_count(
        self, dept_id: str, delta: int, conn=None,
    ) -> None: ...
