"""Catalog application queries — safe for cross-context import.

Other bounded contexts import from here, never from catalog.infrastructure directly.
Thin delegation layer that decouples consumers from infrastructure details.
"""
from typing import Optional

from catalog.infrastructure.department_repo import department_repo as _dept_repo
from catalog.infrastructure.product_repo import product_repo as _prod_repo
from catalog.infrastructure.sku_repo import sku_repo as _sku_repo
from catalog.infrastructure.vendor_repo import vendor_repo as _vendor_repo

# ── Product queries ──────────────────────────────────────────────────────────

async def list_products(
    department_id: str | None = None,
    search: str | None = None,
    low_stock: bool = False,
    limit: int | None = None,
    offset: int = 0,
    organization_id: str | None = None,
) -> list:
    return await _prod_repo.list_products(
        department_id=department_id, search=search, low_stock=low_stock,
        limit=limit, offset=offset, organization_id=organization_id,
    )


async def count_products(
    department_id: str | None = None,
    search: str | None = None,
    low_stock: bool = False,
    organization_id: str | None = None,
) -> int:
    return await _prod_repo.count_products(
        department_id=department_id, search=search,
        low_stock=low_stock, organization_id=organization_id,
    )


async def get_product_by_id(
    product_id: str, columns: str | None = "*",
    organization_id: str | None = None, conn=None,
) -> dict | None:
    return await _prod_repo.get_by_id(product_id, columns=columns, organization_id=organization_id, conn=conn)


async def find_product_by_barcode(
    barcode: str, exclude_product_id: str | None = None,
    organization_id: str | None = None, conn=None,
) -> dict | None:
    return await _prod_repo.find_by_barcode(barcode, exclude_product_id=exclude_product_id, organization_id=organization_id, conn=conn)


async def find_product_by_original_sku_and_vendor(
    original_sku: str, vendor_id: str, organization_id: str | None = None,
) -> dict | None:
    return await _prod_repo.find_by_original_sku_and_vendor(original_sku, vendor_id, organization_id=organization_id)


async def find_product_by_name_and_vendor(
    name: str, vendor_id: str, organization_id: str | None = None,
) -> dict | None:
    return await _prod_repo.find_by_name_and_vendor(name, vendor_id, organization_id=organization_id)


async def list_products_by_vendor(vendor_id: str, limit: int = 200) -> list:
    return await _prod_repo.list_by_vendor(vendor_id, limit=limit)


async def count_all_products(organization_id: str | None = None) -> int:
    return await _prod_repo.count_all(organization_id=organization_id)


async def count_low_stock(organization_id: str | None = None) -> int:
    return await _prod_repo.count_low_stock(organization_id=organization_id)


async def list_low_stock(limit: int = 10, organization_id: str | None = None) -> list:
    return await _prod_repo.list_low_stock(limit=limit, organization_id=organization_id)


# ── Product commands (used by inventory / purchasing / documents) ────────────

async def update_product(product_id: str, updates: dict, conn=None) -> dict | None:
    return await _prod_repo.update(product_id, updates, conn=conn)


async def atomic_decrement_product(product_id: str, quantity: float, updated_at: str, conn=None) -> dict | None:
    return await _prod_repo.atomic_decrement(product_id, quantity, updated_at, conn=conn)


async def increment_product_quantity(product_id: str, quantity: float, updated_at: str, conn=None) -> None:
    return await _prod_repo.increment_quantity(product_id, quantity, updated_at, conn=conn)


async def add_product_quantity(product_id: str, quantity: float, updated_at: str, conn=None) -> dict | None:
    return await _prod_repo.add_quantity(product_id, quantity, updated_at, conn=conn)


async def atomic_adjust_product(product_id: str, quantity_delta: float, updated_at: str, conn=None) -> dict | None:
    return await _prod_repo.atomic_adjust(product_id, quantity_delta, updated_at, conn=conn)


# ── Department queries ───────────────────────────────────────────────────────

async def list_departments(organization_id: str | None = None) -> list:
    return await _dept_repo.list_all(organization_id=organization_id)


async def get_department_by_id(dept_id: str, organization_id: str | None = None) -> dict | None:
    return await _dept_repo.get_by_id(dept_id, organization_id=organization_id)


async def get_department_by_code(code: str, organization_id: str | None = None) -> dict | None:
    return await _dept_repo.get_by_code(code, organization_id=organization_id)


async def insert_department(dept_dict: dict) -> None:
    return await _dept_repo.insert(dept_dict)


# ── Vendor queries ───────────────────────────────────────────────────────────

async def list_vendors(organization_id: str | None = None) -> list:
    return await _vendor_repo.list_all(organization_id=organization_id)


async def find_vendor_by_name(name: str, organization_id: str | None = None) -> dict | None:
    return await _vendor_repo.find_by_name(name, organization_id=organization_id)


async def insert_vendor(vendor_dict: dict) -> None:
    return await _vendor_repo.insert(vendor_dict)


async def count_vendors(organization_id: str | None = None) -> int:
    return await _vendor_repo.count(organization_id=organization_id)


# ── SKU queries ──────────────────────────────────────────────────────────────

async def get_sku_counters(organization_id: str | None = None) -> dict:
    return await _sku_repo.get_all_counters(organization_id=organization_id)
