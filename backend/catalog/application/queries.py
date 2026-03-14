"""Catalog application queries — safe for cross-context import.

Other bounded contexts import from here, never from catalog.infrastructure directly.
Thin delegation layer that decouples consumers from infrastructure details.
"""

from catalog.domain.department import Department
from catalog.domain.product import Sku, SkuUpdate
from catalog.domain.product_family import Product
from catalog.domain.vendor import Vendor
from catalog.domain.vendor_item import VendorItem
from catalog.infrastructure.department_repo import department_repo as _dept_repo
from catalog.infrastructure.product_family_repo import product_family_repo as _prod_repo
from catalog.infrastructure.sku_counter_repo import sku_counter_repo as _counter_repo
from catalog.infrastructure.sku_repo import sku_repo as _sku_repo
from catalog.infrastructure.vendor_item_repo import vendor_item_repo as _vi_repo
from catalog.infrastructure.vendor_repo import vendor_repo as _vendor_repo

# ── Product family (parent) queries ──────────────────────────────────────────


async def list_product_families(
    category_id: str | None = None,
    search: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Product]:
    return await _prod_repo.list_all(
        category_id=category_id,
        search=search,
        limit=limit,
        offset=offset,
    )


async def count_product_families(
    category_id: str | None = None,
    search: str | None = None,
) -> int:
    return await _prod_repo.count(category_id=category_id, search=search)


async def get_product_family_by_id(product_id: str) -> Product | None:
    return await _prod_repo.get_by_id(product_id)


# ── SKU queries ──────────────────────────────────────────────────────────────


async def list_skus(
    category_id: str | None = None,
    search: str | None = None,
    low_stock: bool = False,
    limit: int | None = None,
    offset: int = 0,
    product_id: str | None = None,
) -> list[Sku]:
    return await _sku_repo.list_skus(
        category_id=category_id,
        search=search,
        low_stock=low_stock,
        limit=limit,
        offset=offset,
        product_id=product_id,
    )


async def count_skus(
    category_id: str | None = None,
    search: str | None = None,
    low_stock: bool = False,
    product_id: str | None = None,
) -> int:
    return await _sku_repo.count_skus(
        category_id=category_id,
        search=search,
        low_stock=low_stock,
        product_id=product_id,
    )


async def get_sku_by_id(sku_id: str) -> Sku | None:
    return await _sku_repo.get_by_id(sku_id)


async def find_sku_by_sku_code(sku: str) -> Sku | None:
    return await _sku_repo.find_by_sku(sku)


async def find_sku_by_barcode(
    barcode: str,
    exclude_sku_id: str | None = None,
) -> Sku | None:
    return await _sku_repo.find_by_barcode(barcode, exclude_sku_id=exclude_sku_id)


async def list_skus_by_product(product_id: str) -> list[Sku]:
    return await _sku_repo.find_by_product_id(product_id)


async def count_all_skus() -> int:
    return await _sku_repo.count_all()


async def count_low_stock() -> int:
    return await _sku_repo.count_low_stock()


async def list_low_stock(limit: int = 10) -> list[Sku]:
    return await _sku_repo.list_low_stock(limit=limit)


# ── SKU commands (used by inventory / purchasing / documents) ────────────────


async def update_sku(sku_id: str, updates: SkuUpdate) -> Sku | None:
    return await _sku_repo.update(sku_id, updates.model_dump(exclude_none=True))


async def atomic_decrement_sku(sku_id: str, quantity: float, updated_at: str) -> Sku | None:
    return await _sku_repo.atomic_decrement(sku_id, quantity, updated_at)


async def increment_sku_quantity(sku_id: str, quantity: float, updated_at: str) -> None:
    return await _sku_repo.increment_quantity(sku_id, quantity, updated_at)


async def add_sku_quantity(sku_id: str, quantity: float, updated_at: str) -> Sku | None:
    return await _sku_repo.add_quantity(sku_id, quantity, updated_at)


async def atomic_adjust_sku(sku_id: str, quantity_delta: float, updated_at: str) -> Sku | None:
    return await _sku_repo.atomic_adjust(sku_id, quantity_delta, updated_at)


# ── VendorItem queries ───────────────────────────────────────────────────────


async def get_vendor_items_for_sku(sku_id: str) -> list[VendorItem]:
    return await _vi_repo.list_by_sku(sku_id)


async def find_vendor_item_by_vendor_and_sku_code(
    vendor_id: str, vendor_sku: str
) -> VendorItem | None:
    return await _vi_repo.find_by_vendor_and_vendor_sku(vendor_id, vendor_sku)


async def find_vendor_item_by_sku_and_vendor(sku_id: str, vendor_id: str) -> VendorItem | None:
    return await _vi_repo.find_by_sku_and_vendor(sku_id, vendor_id)


async def find_product_by_original_sku_and_vendor(original_sku: str, vendor_id: str) -> Sku | None:
    """Resolve vendor part number → VendorItem → SKU."""
    vi = await _vi_repo.find_by_vendor_and_vendor_sku(vendor_id, original_sku)
    if not vi:
        return None
    return await _sku_repo.get_by_id(vi.sku_id)


async def find_product_by_name_and_vendor(name: str, vendor_id: str) -> Sku | None:
    """Name-based fallback for PO matching."""
    return await _sku_repo.find_by_name_and_vendor(name, vendor_id)


async def sku_vendor_options(sku_id: str) -> list[dict]:
    """All vendors for a SKU with cost, lead time, moq, preferred, and last PO date."""
    from shared.infrastructure.database import get_connection, get_org_id

    items = await _vi_repo.list_by_sku(sku_id)
    if not items:
        return []

    conn = get_connection()
    org_id = get_org_id()
    result = []
    for vi in items:
        vendor = await _vendor_repo.get_by_id(vi.vendor_id)
        cursor = await conn.execute(
            """SELECT MAX(po.created_at) AS last_po_date
               FROM purchase_orders po
               JOIN purchase_order_items poi ON poi.po_id = po.id
               WHERE po.vendor_id = ? AND po.organization_id = ?
                 AND poi.product_id = ?""",
            (vi.vendor_id, org_id, sku_id),
        )
        row = await cursor.fetchone()
        result.append(
            {
                "vendor_id": vi.vendor_id,
                "vendor_name": vendor.name if vendor else vi.vendor_name,
                "vendor_sku": vi.vendor_sku,
                "cost": vi.cost,
                "lead_time_days": vi.lead_time_days,
                "moq": vi.moq,
                "is_preferred": vi.is_preferred,
                "purchase_uom": vi.purchase_uom,
                "purchase_pack_qty": vi.purchase_pack_qty,
                "last_po_date": row["last_po_date"] if row else None,
            }
        )
    return result


# ── Department queries ───────────────────────────────────────────────────────


async def list_departments() -> list[Department]:
    return await _dept_repo.list_all()


async def get_department_by_id(dept_id: str) -> Department | None:
    return await _dept_repo.get_by_id(dept_id)


async def get_department_by_code(code: str) -> Department | None:
    return await _dept_repo.get_by_code(code)


async def insert_department(department: Department | dict) -> None:
    return await _dept_repo.insert(department)


async def update_department(
    dept_id: str,
    name: str,
    description: str,
) -> Department | None:
    return await _dept_repo.update(dept_id, name, description)


async def delete_department(dept_id: str) -> int:
    return await _dept_repo.delete(dept_id)


async def count_skus_by_department(dept_id: str) -> int:
    return await _dept_repo.count_skus_by_department(dept_id)


# ── Vendor queries ───────────────────────────────────────────────────────────


async def list_vendors() -> list[Vendor]:
    return await _vendor_repo.list_all()


async def get_vendor_by_id(vendor_id: str) -> Vendor | None:
    return await _vendor_repo.get_by_id(vendor_id)


async def find_vendor_by_name(name: str) -> Vendor | None:
    return await _vendor_repo.find_by_name(name)


async def insert_vendor(vendor: Vendor | dict) -> None:
    return await _vendor_repo.insert(vendor)


async def update_vendor(
    vendor_id: str,
    vendor_dict: dict,
) -> Vendor | None:
    return await _vendor_repo.update(vendor_id, vendor_dict)


async def delete_vendor(vendor_id: str) -> int:
    return await _vendor_repo.delete(vendor_id)


async def count_vendors() -> int:
    return await _vendor_repo.count()


# ── SKU counter queries ─────────────────────────────────────────────────────


async def get_sku_counters() -> dict:
    return await _counter_repo.get_all_counters()


async def get_next_sku_number(department_code: str) -> int:
    return await _counter_repo.get_next_number(department_code)
