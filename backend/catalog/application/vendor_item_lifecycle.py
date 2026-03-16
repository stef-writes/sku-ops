"""Vendor item lifecycle: manage vendor-to-SKU relationships.

Each VendorItem links a vendor to a specific SKU with the vendor's
part number, purchase UOM, cost, lead time, and preferred status.
"""

from __future__ import annotations

import logging

from catalog.domain.vendor_item import VendorItem
from catalog.infrastructure.vendor_item_repo import vendor_item_repo
from catalog.infrastructure.vendor_repo import vendor_repo
from shared.infrastructure.database import get_org_id, transaction
from shared.kernel.errors import ResourceNotFoundError

logger = logging.getLogger(__name__)


async def add_vendor_item(
    sku_id: str,
    vendor_id: str,
    vendor_sku: str | None = None,
    purchase_uom: str = "each",
    purchase_pack_qty: int = 1,
    cost: float = 0.0,
    lead_time_days: int | None = None,
    moq: float | None = None,
    is_preferred: bool = False,
    notes: str | None = None,
) -> VendorItem:
    """Add a vendor relationship to a SKU."""
    org_id = get_org_id()

    vendor = await vendor_repo.get_by_id(vendor_id)
    vendor_name = vendor.name if vendor else ""

    item = VendorItem(
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        sku_id=sku_id,
        vendor_sku=vendor_sku,
        purchase_uom=purchase_uom,
        purchase_pack_qty=purchase_pack_qty,
        cost=cost,
        lead_time_days=lead_time_days,
        moq=moq,
        is_preferred=is_preferred,
        notes=notes,
        organization_id=org_id,
    )

    async with transaction():
        if is_preferred:
            await vendor_item_repo.clear_preferred_for_sku(sku_id)
        await vendor_item_repo.insert(item)

    logger.info(
        "vendor_item.added",
        extra={
            "org_id": org_id,
            "vendor_item_id": item.id,
            "sku_id": sku_id,
            "vendor_id": vendor_id,
            "is_preferred": is_preferred,
        },
    )
    return item


async def update_vendor_item(
    item_id: str,
    updates: dict,
) -> VendorItem:
    """Update a vendor item."""
    existing = await vendor_item_repo.get_by_id(item_id)
    if not existing:
        raise ResourceNotFoundError("VendorItem", item_id)

    async with transaction():
        if updates.get("is_preferred"):
            await vendor_item_repo.clear_preferred_for_sku(existing.sku_id)
        result = await vendor_item_repo.update(item_id, updates)
    if not result:
        raise ResourceNotFoundError("VendorItem", item_id)
    logger.info("vendor_item.updated", extra={"org_id": get_org_id(), "vendor_item_id": item_id})
    return result


async def remove_vendor_item(item_id: str) -> None:
    """Soft-delete a vendor item."""
    existing = await vendor_item_repo.get_by_id(item_id)
    if not existing:
        raise ResourceNotFoundError("VendorItem", item_id)
    async with transaction():
        await vendor_item_repo.soft_delete(item_id)
    logger.info(
        "vendor_item.removed",
        extra={"org_id": get_org_id(), "vendor_item_id": item_id, "sku_id": existing.sku_id},
    )


async def set_preferred_vendor(sku_id: str, vendor_item_id: str) -> None:
    """Set a specific vendor item as the preferred supplier for a SKU."""
    item = await vendor_item_repo.get_by_id(vendor_item_id)
    if not item or item.sku_id != sku_id:
        raise ResourceNotFoundError("VendorItem", vendor_item_id)

    async with transaction():
        await vendor_item_repo.clear_preferred_for_sku(sku_id)
        await vendor_item_repo.update(vendor_item_id, {"is_preferred": True})
    logger.info(
        "vendor_item.preferred_set",
        extra={"org_id": get_org_id(), "vendor_item_id": vendor_item_id, "sku_id": sku_id},
    )


async def get_vendor_items_for_sku(sku_id: str) -> list[VendorItem]:
    """Return all vendor items for a SKU."""
    return await vendor_item_repo.list_by_sku(sku_id)
