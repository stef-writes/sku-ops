"""Department repository port — testable contract for department persistence."""
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class DepartmentRepoPort(Protocol):

    async def list_all(self, organization_id: Optional[str] = None) -> list: ...

    async def get_by_id(
        self, dept_id: str, organization_id: Optional[str] = None,
    ) -> Optional[dict]: ...

    async def get_by_code(
        self, code: str, organization_id: Optional[str] = None,
    ) -> Optional[dict]: ...

    async def insert(self, dept_dict: dict) -> None: ...

    async def update(
        self, dept_id: str, name: str, description: str, conn=None,
    ) -> Optional[dict]: ...

    async def count_products_by_department(self, dept_id: str) -> int: ...

    async def delete(self, dept_id: str) -> int: ...

    async def increment_product_count(
        self, dept_id: str, delta: int, conn=None,
    ) -> None: ...
