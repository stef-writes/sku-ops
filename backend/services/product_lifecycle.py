"""
Product lifecycle service: single source of truth for create, update, delete.

All product creation (API, CSV import, document import) flows through this service.
Uses transactions to ensure product_count and stock ledger stay in sync.
"""
from datetime import datetime, timezone
from typing import Any, Optional

from db import transaction
from domain.exceptions import ResourceNotFoundError
from models import Product
from repositories import department_repo, product_repo, vendor_repo
from services.inventory import process_import_stock_changes
from services.sku_service import generate_sku


async def create_product(
    department_id: str,
    department_name: str,
    name: str,
    description: str = "",
    price: float = 0,
    cost: float = 0,
    quantity: int = 0,
    min_stock: int = 5,
    vendor_id: Optional[str] = None,
    vendor_name: str = "",
    original_sku: Optional[str] = None,
    barcode: Optional[str] = None,
    base_unit: str = "each",
    sell_uom: str = "each",
    pack_qty: int = 1,
    user_id: Optional[str] = None,
    user_name: str = "",
) -> Product:
    """
    Create a product with SKU generation, product_count updates, and stock ledger.
    All operations run in a single transaction.
    Caller must resolve department and vendor before calling.
    """
    department = await department_repo.get_by_id(department_id)
    if not department:
        raise ResourceNotFoundError("Department", department_id)

    sku = await generate_sku(department["code"], name)
    barcode_val = (barcode or "").strip() or sku

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
    )

    async with transaction() as conn:
        await product_repo.insert(product.model_dump(), conn=conn)
        await department_repo.increment_product_count(department_id, 1, conn=conn)
        if vendor_id:
            await vendor_repo.increment_product_count(vendor_id, 1, conn=conn)
        if quantity > 0 and user_id:
            await process_import_stock_changes(
                product_id=product.id,
                sku=product.sku,
                product_name=product.name,
                quantity=quantity,
                user_id=user_id,
                user_name=user_name,
                conn=conn,
            )

    return product


async def update_product(
    product_id: str,
    updates: dict[str, Any],
    current_product: Optional[dict] = None,
) -> dict:
    """
    Update a product. Resolves department/vendor name and product_count changes.
    Runs in a transaction.
    """
    product = current_product or await product_repo.get_by_id(product_id)
    if not product:
        raise ResourceNotFoundError("Product", product_id)

    update_data = {k: v for k, v in updates.items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    if "department_id" in update_data:
        department = await department_repo.get_by_id(update_data["department_id"])
        if department:
            update_data["department_name"] = department["name"]
    if "vendor_id" in update_data:
        if update_data["vendor_id"]:
            vendor = await vendor_repo.get_by_id(update_data["vendor_id"])
            update_data["vendor_name"] = vendor.get("name", "") if vendor else ""
        else:
            update_data["vendor_name"] = ""

    async with transaction() as conn:
        # Adjust department product_count if department changed
        if "department_id" in update_data:
            old_dept = product.get("department_id")
            new_dept = update_data["department_id"]
            if old_dept != new_dept:
                await department_repo.increment_product_count(old_dept, -1, conn=conn)
                await department_repo.increment_product_count(new_dept, 1, conn=conn)

        # Adjust vendor product_count if vendor changed
        if "vendor_id" in update_data:
            old_vendor = product.get("vendor_id") or ""
            new_vendor = update_data.get("vendor_id") or ""
            if old_vendor != new_vendor:
                if old_vendor:
                    await vendor_repo.increment_product_count(old_vendor, -1, conn=conn)
                if new_vendor:
                    await vendor_repo.increment_product_count(new_vendor, 1, conn=conn)

        result = await product_repo.update(product_id, update_data, conn=conn)
    return result


async def delete_product(product_id: str) -> None:
    """
    Delete a product and update department/vendor product_count.
    Runs in a transaction.
    """
    product = await product_repo.get_by_id(product_id)
    if not product:
        raise ResourceNotFoundError("Product", product_id)

    async with transaction() as conn:
        await product_repo.delete(product_id, conn=conn)
        await department_repo.increment_product_count(product["department_id"], -1, conn=conn)
        if product.get("vendor_id"):
            await vendor_repo.increment_product_count(product["vendor_id"], -1, conn=conn)
