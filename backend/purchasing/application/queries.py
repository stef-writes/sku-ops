"""Purchasing application queries — safe for cross-context import.

Other bounded contexts import from here, never from purchasing.infrastructure directly.
"""

from catalog.application.queries import get_product_by_id as _get_product
from purchasing.infrastructure.po_repo import po_repo as _po_repo


async def get_po_with_cost(po_id: str) -> dict | None:
    return await _po_repo.get_po_with_cost(po_id)


async def list_unsynced_po_bills() -> list[dict]:
    return await _po_repo.list_unsynced_po_bills()


async def list_failed_po_bills() -> list[dict]:
    return await _po_repo.list_failed_po_bills()


async def set_xero_sync_status(po_id: str, status: str, updated_at: str) -> None:
    await _po_repo.set_xero_sync_status(po_id, status, updated_at)


async def set_xero_bill_id(po_id: str, xero_bill_id: str, updated_at: str) -> None:
    await _po_repo.set_xero_bill_id(po_id, xero_bill_id, updated_at)


async def po_summary_by_status() -> dict[str, dict]:
    """PO count and total grouped by status. Used by dashboard."""
    return await _po_repo.summary_by_status()


async def list_pos(status: str | None = None) -> list:
    return await _po_repo.list_pos(status=status)


async def get_po(po_id: str) -> dict | None:
    return await _po_repo.get_po(po_id)


async def get_po_items(po_id: str) -> list:
    items = await _po_repo.get_po_items(po_id)
    product_ids = [i["product_id"] for i in items if i.get("product_id")]
    if not product_ids:
        return items
    products = {}
    for pid in set(product_ids):
        p = await _get_product(pid)
        if p:
            products[pid] = p
    for item in items:
        pid = item.get("product_id")
        if pid and pid in products:
            p = products[pid]
            item["matched_sku"] = p.sku
            item["matched_name"] = p.name
            item["matched_quantity"] = p.quantity
            item["matched_cost"] = p.cost
    return items
