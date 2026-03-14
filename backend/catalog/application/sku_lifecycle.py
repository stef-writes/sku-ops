"""
SKU lifecycle service: single source of truth for create, update, delete.

All SKU creation (API, CSV import, document import, PO receiving) flows
through this service. Uses transactions to ensure sku_count and stock
ledger stay in sync.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from catalog.application.product_family_lifecycle import create_product as create_product_parent
from catalog.application.sku_service import generate_sku
from catalog.domain.errors import DuplicateBarcodeError, InvalidBarcodeError
from catalog.domain.product import Sku, SkuUpdate
from catalog.infrastructure.department_repo import department_repo
from catalog.infrastructure.product_family_repo import product_family_repo
from catalog.infrastructure.sku_repo import sku_repo
from catalog.infrastructure.vendor_item_repo import vendor_item_repo
from shared.infrastructure.database import get_org_id, transaction
from shared.infrastructure.domain_events import dispatch
from shared.kernel.barcode import validate_barcode
from shared.kernel.domain_events import CatalogChanged
from shared.kernel.errors import ResourceNotFoundError

StockChangesFn = Callable[..., Awaitable[None]] | None


async def create_sku(
    product_id: str,
    category_id: str,
    category_name: str,
    name: str,
    description: str = "",
    price: float = 0,
    cost: float = 0,
    quantity: float = 0,
    min_stock: int = 5,
    barcode: str | None = None,
    base_unit: str = "each",
    sell_uom: str = "each",
    pack_qty: int = 1,
    purchase_uom: str = "each",
    purchase_pack_qty: int = 1,
    user_id: str | None = None,
    user_name: str = "",
    *,
    on_stock_import: StockChangesFn = None,
) -> Sku:
    """Create a SKU under an existing product parent.

    Generates the SKU code, validates/derives barcode, increments counters,
    and optionally records initial stock. All in a single transaction.
    """
    org_id = get_org_id()
    department = await department_repo.get_by_id(category_id)
    if not department:
        raise ResourceNotFoundError("Department", category_id)

    sku_code = await generate_sku(department.code, name)
    barcode_val = (barcode or "").strip() or sku_code

    if barcode_val and barcode_val.isdigit():
        valid, _ = validate_barcode(barcode_val)
        if not valid:
            raise InvalidBarcodeError(
                barcode_val,
                "Invalid UPC (12 digits) or EAN-13 (13 digits) check digit",
            )
    existing = await sku_repo.find_by_barcode(barcode_val)
    if existing:
        raise DuplicateBarcodeError(barcode_val, existing.name)

    sku = Sku(
        sku=sku_code,
        product_id=product_id,
        name=name,
        description=description,
        price=price,
        cost=cost,
        quantity=quantity,
        min_stock=min_stock,
        category_id=category_id,
        category_name=category_name,
        barcode=barcode_val,
        base_unit=base_unit,
        sell_uom=sell_uom,
        pack_qty=pack_qty,
        purchase_uom=purchase_uom,
        purchase_pack_qty=purchase_pack_qty,
    )
    sku.organization_id = org_id

    async with transaction():
        await sku_repo.insert(sku)
        await department_repo.increment_sku_count(category_id, 1)
        await product_family_repo.increment_sku_count(product_id, 1)
        if quantity > 0 and user_id and on_stock_import:
            await on_stock_import(
                product_id=sku.id,
                sku=sku.sku,
                product_name=sku.name,
                quantity=quantity,
                user_id=user_id,
                user_name=user_name,
            )

    await dispatch(CatalogChanged(org_id=org_id, product_ids=(sku.id,), change_type="created"))
    return sku


async def create_product_with_sku(
    category_id: str,
    category_name: str,
    name: str,
    description: str = "",
    price: float = 0,
    cost: float = 0,
    quantity: float = 0,
    min_stock: int = 5,
    barcode: str | None = None,
    base_unit: str = "each",
    sell_uom: str = "each",
    pack_qty: int = 1,
    purchase_uom: str = "each",
    purchase_pack_qty: int = 1,
    user_id: str | None = None,
    user_name: str = "",
    *,
    on_stock_import: StockChangesFn = None,
) -> Sku:
    """Convenience: create a Product parent and its first SKU atomically.

    Used by the API create endpoint and PO receiving when creating new items.
    """
    product = await create_product_parent(
        name=name,
        category_id=category_id,
        category_name=category_name,
        description=description,
    )
    return await create_sku(
        product_id=product.id,
        category_id=category_id,
        category_name=category_name,
        name=name,
        description=description,
        price=price,
        cost=cost,
        quantity=quantity,
        min_stock=min_stock,
        barcode=barcode,
        base_unit=base_unit,
        sell_uom=sell_uom,
        pack_qty=pack_qty,
        purchase_uom=purchase_uom,
        purchase_pack_qty=purchase_pack_qty,
        user_id=user_id,
        user_name=user_name,
        on_stock_import=on_stock_import,
    )


async def update_sku(
    sku_id: str,
    updates: SkuUpdate,
    current_sku: Sku | None = None,
) -> Sku:
    """Update a SKU. Resolves category name changes and adjusts counters."""
    sku = current_sku or await sku_repo.get_by_id(sku_id)
    if not sku:
        raise ResourceNotFoundError("Sku", sku_id)

    update_data = updates.model_dump(exclude_none=True)
    update_data["updated_at"] = datetime.now(UTC).isoformat()

    if "barcode" in update_data:
        barcode_raw = update_data["barcode"]
        barcode_val = (barcode_raw or "").strip() or sku.sku
        update_data["barcode"] = barcode_val or sku.sku
        current_barcode = (sku.barcode or "").strip()
        if update_data["barcode"] != current_barcode:
            if update_data["barcode"] and update_data["barcode"].isdigit():
                valid, _ = validate_barcode(update_data["barcode"])
                if not valid:
                    raise InvalidBarcodeError(
                        update_data["barcode"],
                        "Invalid UPC (12 digits) or EAN-13 (13 digits) check digit",
                    )
            existing = await sku_repo.find_by_barcode(update_data["barcode"], exclude_sku_id=sku_id)
            if existing:
                raise DuplicateBarcodeError(update_data["barcode"], existing.name)

    if "category_id" in update_data:
        department = await department_repo.get_by_id(update_data["category_id"])
        if department:
            update_data["category_name"] = department.name

    async with transaction():
        if "category_id" in update_data:
            old_cat = sku.category_id
            new_cat = update_data["category_id"]
            if old_cat != new_cat:
                if old_cat:
                    await department_repo.increment_sku_count(old_cat, -1)
                if new_cat:
                    await department_repo.increment_sku_count(new_cat, 1)

        result = await sku_repo.update(sku_id, update_data)
    if not result:
        raise ResourceNotFoundError("Sku", sku_id)

    await dispatch(
        CatalogChanged(org_id=get_org_id(), product_ids=(sku_id,), change_type="updated")
    )
    return result


async def delete_sku(sku_id: str) -> None:
    """Delete a SKU, update counters, and soft-delete associated vendor items."""
    sku = await sku_repo.get_by_id(sku_id)
    if not sku:
        raise ResourceNotFoundError("Sku", sku_id)

    async with transaction():
        await vendor_item_repo.soft_delete_by_sku(sku_id)
        await sku_repo.delete(sku_id)
        await department_repo.increment_sku_count(sku.category_id, -1)
        if sku.product_id:
            await product_family_repo.increment_sku_count(sku.product_id, -1)

    await dispatch(
        CatalogChanged(org_id=get_org_id(), product_ids=(sku_id,), change_type="deleted")
    )
