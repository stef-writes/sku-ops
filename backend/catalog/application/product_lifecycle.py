"""
Product lifecycle service: single source of truth for create, update, delete.

All product creation (API, CSV import, document import) flows through this service.
Uses transactions to ensure product_count and stock ledger stay in sync.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from catalog.application.sku_service import generate_sku
from catalog.domain.errors import DuplicateBarcodeError, InvalidBarcodeError
from catalog.domain.product import Product
from catalog.infrastructure.department_repo import department_repo
from catalog.infrastructure.product_repo import product_repo
from catalog.infrastructure.vendor_repo import vendor_repo
from shared.infrastructure.database import get_org_id, transaction
from shared.kernel.barcode import validate_barcode
from shared.kernel.errors import ResourceNotFoundError

StockChangesFn = Callable[..., Awaitable[None]] | None


async def create_product(
    department_id: str,
    department_name: str,
    name: str,
    description: str = "",
    price: float = 0,
    cost: float = 0,
    quantity: float = 0,
    min_stock: int = 5,
    vendor_id: str | None = None,
    vendor_name: str = "",
    original_sku: str | None = None,
    barcode: str | None = None,
    base_unit: str = "each",
    sell_uom: str = "each",
    pack_qty: int = 1,
    product_group: str | None = None,
    user_id: str | None = None,
    user_name: str = "",
    *,
    on_stock_import: StockChangesFn = None,
) -> Product:
    """
    Create a product with SKU generation, product_count updates, and stock ledger.
    All operations run in a single transaction.
    Caller must resolve department and vendor before calling.
    """
    org_id = get_org_id()
    department = await department_repo.get_by_id(department_id)
    if not department:
        raise ResourceNotFoundError("Department", department_id)

    sku = await generate_sku(department.code, name)
    barcode_val = (barcode or "").strip() or sku

    if barcode_val and barcode_val.isdigit():
        valid, _ = validate_barcode(barcode_val)
        if not valid:
            raise InvalidBarcodeError(
                barcode_val,
                "Invalid UPC (12 digits) or EAN-13 (13 digits) check digit",
            )
    existing = await product_repo.find_by_barcode(barcode_val)
    if existing:
        raise DuplicateBarcodeError(barcode_val, existing.name)

    product = Product(
        sku=sku,
        name=name,
        description=description,
        price=price,
        cost=cost,
        quantity=quantity,
        min_stock=min_stock,
        department_id=department_id,
        department_name=department_name,
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        original_sku=original_sku,
        barcode=barcode_val,
        base_unit=base_unit,
        sell_uom=sell_uom,
        pack_qty=pack_qty,
        product_group=product_group,
    )

    product.organization_id = org_id
    async with transaction():
        await product_repo.insert(product)
        await department_repo.increment_product_count(department_id, 1)
        if vendor_id:
            await vendor_repo.increment_product_count(vendor_id, 1)
        if quantity > 0 and user_id and on_stock_import:
            await on_stock_import(
                product_id=product.id,
                sku=product.sku,
                product_name=product.name,
                quantity=quantity,
                user_id=user_id,
                user_name=user_name,
            )

    return product


async def update_product(
    product_id: str,
    updates: dict[str, Any],
    current_product: Product | None = None,
) -> Product:
    """
    Update a product. Resolves department/vendor name and product_count changes.
    Runs in a transaction.
    """
    product = current_product or await product_repo.get_by_id(product_id)
    if not product:
        raise ResourceNotFoundError("Product", product_id)

    update_data = {k: v for k, v in updates.items() if v is not None}
    update_data["updated_at"] = datetime.now(UTC).isoformat()

    if "barcode" in update_data:
        barcode_raw = update_data["barcode"]
        barcode_val = (barcode_raw or "").strip() or product.sku
        update_data["barcode"] = barcode_val or product.sku
        current_barcode = (product.barcode or "").strip()
        if update_data["barcode"] != current_barcode:
            if update_data["barcode"] and update_data["barcode"].isdigit():
                valid, _ = validate_barcode(update_data["barcode"])
                if not valid:
                    raise InvalidBarcodeError(
                        update_data["barcode"],
                        "Invalid UPC (12 digits) or EAN-13 (13 digits) check digit",
                    )
            existing = await product_repo.find_by_barcode(
                update_data["barcode"], exclude_product_id=product_id
            )
            if existing:
                raise DuplicateBarcodeError(update_data["barcode"], existing.name)

    if "department_id" in update_data:
        department = await department_repo.get_by_id(update_data["department_id"])
        if department:
            update_data["department_name"] = department.name
    if "vendor_id" in update_data:
        if update_data["vendor_id"]:
            vendor = await vendor_repo.get_by_id(update_data["vendor_id"])
            update_data["vendor_name"] = vendor.name if vendor else ""
        else:
            update_data["vendor_name"] = ""

    async with transaction():
        if "department_id" in update_data:
            old_dept: str | None = product.department_id
            new_dept: str | None = update_data["department_id"]
            if old_dept != new_dept:
                if old_dept:
                    await department_repo.increment_product_count(old_dept, -1)
                if new_dept:
                    await department_repo.increment_product_count(new_dept, 1)

        if "vendor_id" in update_data:
            old_vendor = product.vendor_id or ""
            new_vendor = update_data.get("vendor_id") or ""
            if old_vendor != new_vendor:
                if old_vendor:
                    await vendor_repo.increment_product_count(old_vendor, -1)
                if new_vendor:
                    await vendor_repo.increment_product_count(new_vendor, 1)

        result = await product_repo.update(product_id, update_data)
    if not result:
        raise ResourceNotFoundError("Product", product_id)
    return result


async def delete_product(product_id: str) -> None:
    """Delete a product and update department/vendor product_count."""
    product = await product_repo.get_by_id(product_id)
    if not product:
        raise ResourceNotFoundError("Product", product_id)

    async with transaction():
        await product_repo.delete(product_id)
        await department_repo.increment_product_count(product.department_id, -1)
        if product.vendor_id:
            await vendor_repo.increment_product_count(product.vendor_id, -1)


# ---------------------------------------------------------------------------
# Product group operations
# ---------------------------------------------------------------------------


async def bulk_assign_product_group(
    product_ids: list[str],
    product_group: str | None,
) -> int:
    """Assign or clear product_group for multiple products. Returns count updated."""
    group_val = product_group.strip() if product_group else None
    updated = 0
    for pid in product_ids:
        product = await product_repo.get_by_id(pid)
        if not product:
            continue
        await product_repo.update(
            pid,
            {"product_group": group_val, "updated_at": ""},
        )
        updated += 1
    return updated


async def rename_product_group(
    old_name: str,
    new_name: str,
) -> int:
    """Rename a product group across all products that have it. Returns count updated."""
    old = old_name.strip()
    new = new_name.strip()
    if not old or not new:
        raise ValueError("Both old_name and new_name are required")
    products = await product_repo.list_products(product_group=old)
    updated = 0
    for p in products:
        await product_repo.update(
            p.id,
            {"product_group": new, "updated_at": ""},
        )
        updated += 1
    return updated
