"""Product repository port — testable contract for product persistence."""
from typing import List, Optional, Protocol, runtime_checkable

from catalog.domain.product import Product


@runtime_checkable
class ProductRepoPort(Protocol):

    async def list_products(
        self,
        department_id: str | None = None,
        search: str | None = None,
        low_stock: bool = False,
        limit: int | None = None,
        offset: int = 0,
        organization_id: str | None = None,
    ) -> list[dict]: ...

    async def count_products(
        self,
        department_id: str | None = None,
        search: str | None = None,
        low_stock: bool = False,
        organization_id: str | None = None,
    ) -> int: ...

    async def get_by_id(
        self, product_id: str, columns: str | None = "*",
        organization_id: str | None = None, conn=None,
    ) -> dict | None: ...

    async def find_by_barcode(
        self, barcode: str, exclude_product_id: str | None = None,
        organization_id: str | None = None, conn=None,
    ) -> dict | None: ...

    async def find_by_original_sku_and_vendor(
        self, original_sku: str, vendor_id: str,
        organization_id: str | None = None,
    ) -> dict | None: ...

    async def find_by_name_and_vendor(
        self, name: str, vendor_id: str,
        organization_id: str | None = None,
    ) -> dict | None: ...

    async def list_by_vendor(self, vendor_id: str, limit: int = 200) -> list[dict]: ...

    async def insert(self, product: Product, conn=None) -> None: ...

    async def update(self, product_id: str, updates: dict, conn=None) -> dict | None: ...

    async def delete(self, product_id: str, conn=None) -> int: ...

    async def atomic_decrement(
        self, product_id: str, quantity: float, updated_at: str, conn=None,
    ) -> dict | None: ...

    async def increment_quantity(
        self, product_id: str, quantity: float, updated_at: str, conn=None,
    ) -> None: ...

    async def add_quantity(
        self, product_id: str, quantity: float, updated_at: str, conn=None,
    ) -> dict | None: ...

    async def atomic_adjust(
        self, product_id: str, quantity_delta: float, updated_at: str,
    ) -> dict | None: ...

    async def count_all(self, organization_id: str | None = None) -> int: ...

    async def count_low_stock(self, organization_id: str | None = None) -> int: ...

    async def list_low_stock(
        self, limit: int = 10, organization_id: str | None = None,
    ) -> list[dict]: ...
