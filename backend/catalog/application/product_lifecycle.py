"""
Product lifecycle service: single source of truth for create, update, delete.

All product creation (API, CSV import, document import) flows through this service.
Uses transactions to ensure product_count and stock ledger stay in sync.
"""
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable, Optional

from shared.infrastructure.database import transaction
from catalog.domain.barcode import validate_barcode
from kernel.errors import ResourceNotFoundError
from catalog.domain.errors import DuplicateBarcodeError, InvalidBarcodeError
from catalog.domain.product import Product
from catalog.infrastructure.department_repo import department_repo
from catalog.infrastructure.product_repo import product_repo
from catalog.infrastructure.vendor_repo import vendor_repo
from catalog.application.sku_service import generate_sku

StockChangesFn = Optional[Callable[..., Awaitable[None]]]


async def create_product(
    department_id: str,
    department_name: str,
    name: str,
    description: str = "",
    price: float = 0,
    cost: float = 0,
    quantity: float = 0,
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
    organization_id: Optional[str] = None,
    *,
    on_stock_import: StockChangesFn = None,
) -> Product:
    """
    Create a product with SKU generation, product_count updates, and stock ledger.
    All operations run in a single transaction.
    Caller must resolve department and vendor before calling.
    """
    org_id = organization_id or "default"
    department = await department_repo.get_by_id(department_id, org_id)
    if not department:
        raise ResourceNotFoundError("Department", department_id)

    sku = await generate_sku(department["code"], name, org_id)
    barcode_val = (barcode or "").strip() or sku

    # Validate UPC/EAN if value looks numeric
    if barcode_val and barcode_val.isdigit():
        valid, _ = validate_barcode(barcode_val)
        if not valid:
            raise InvalidBarcodeError(
                barcode_val,
                "Invalid UPC (12 digits) or EAN-13 (13 digits) check digit",
            )
    # Check uniqueness (org-scoped)
    existing = await product_repo.find_by_barcode(barcode_val, organization_id=org_id)
    if existing:
        raise DuplicateBarcodeError(barcode_val, existing.get("name", "Unknown"))

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

    product.organization_id = org_id
    async with transaction() as conn:
        await product_repo.insert(product, conn=conn)
        await department_repo.increment_product_count(department_id, 1, conn=conn)
        if vendor_id:
            await vendor_repo.increment_product_count(vendor_id, 1, conn=conn)
        if quantity > 0 and user_id and on_stock_import:
            await on_stock_import(
                product_id=product.id,
                sku=product.sku,
                product_name=product.name,
                quantity=quantity,
                user_id=user_id,
                user_name=user_name,
                organization_id=org_id,
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

    # Normalize and validate barcode on update
    if "barcode" in update_data:
        barcode_raw = update_data["barcode"]
        barcode_val = (barcode_raw or "").strip() or product.get("sku", "")
        update_data["barcode"] = barcode_val if barcode_val else product.get("sku", "")
        current_barcode = (product.get("barcode") or "").strip()
        if update_data["barcode"] != current_barcode:
            if update_data["barcode"] and update_data["barcode"].isdigit():
                valid, _ = validate_barcode(update_data["barcode"])
                if not valid:
                    raise InvalidBarcodeError(
                        update_data["barcode"],
                        "Invalid UPC (12 digits) or EAN-13 (13 digits) check digit",
                    )
            org_id = product.get("organization_id") or "default"
            existing = await product_repo.find_by_barcode(
                update_data["barcode"], exclude_product_id=product_id, organization_id=org_id
            )
            if existing:
                raise DuplicateBarcodeError(
                    update_data["barcode"], existing.get("name", "Unknown")
                )

    org_id = product.get("organization_id") or "default"
    if "department_id" in update_data:
        department = await department_repo.get_by_id(update_data["department_id"], org_id)
        if department:
            update_data["department_name"] = department["name"]
    if "vendor_id" in update_data:
        if update_data["vendor_id"]:
            vendor = await vendor_repo.get_by_id(update_data["vendor_id"], org_id)
            update_data["vendor_name"] = vendor.get("name", "") if vendor else ""
        else:
            update_data["vendor_name"] = ""

    async with transaction() as conn:
        if "department_id" in update_data:
            old_dept: str | None = product.get("department_id")
            new_dept: str | None = update_data["department_id"]
            if old_dept != new_dept:
                if old_dept:
                    await department_repo.increment_product_count(old_dept, -1, conn=conn)
                if new_dept:
                    await department_repo.increment_product_count(new_dept, 1, conn=conn)

        if "vendor_id" in update_data:
            old_vendor = product.get("vendor_id") or ""
            new_vendor = update_data.get("vendor_id") or ""
            if old_vendor != new_vendor:
                if old_vendor:
                    await vendor_repo.increment_product_count(old_vendor, -1, conn=conn)
                if new_vendor:
                    await vendor_repo.increment_product_count(new_vendor, 1, conn=conn)

        result = await product_repo.update(product_id, update_data, conn=conn)
    if not result:
        raise ResourceNotFoundError("Product", product_id)
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
