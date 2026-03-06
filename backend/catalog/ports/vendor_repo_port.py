"""Vendor repository port — testable contract for vendor persistence."""
from typing import List, Optional, Protocol, runtime_checkable

from catalog.domain.vendor import Vendor


@runtime_checkable
class VendorRepoPort(Protocol):

    async def list_all(self, organization_id: str | None = None) -> list[dict]: ...

    async def get_by_id(
        self, vendor_id: str, organization_id: str | None = None,
    ) -> dict | None: ...

    async def find_by_name(
        self, name: str, organization_id: str | None = None,
    ) -> dict | None: ...

    async def insert(self, vendor: Vendor, conn=None) -> None: ...

    async def update(
        self, vendor_id: str, updates: dict, conn=None,
    ) -> dict | None: ...

    async def delete(self, vendor_id: str) -> int: ...

    async def count(self, organization_id: str | None = None) -> int: ...

    async def increment_product_count(
        self, vendor_id: str, delta: int, conn=None,
    ) -> None: ...
