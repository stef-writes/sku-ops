"""Purchasing application queries — safe for cross-context import.

Other bounded contexts import from here, never from purchasing.infrastructure directly.
"""

from datetime import UTC, datetime, timedelta

from catalog.application.queries import get_sku_by_id as _get_product
from purchasing.domain.purchase_order import POItemRow, PORow, VendorPerformance
from purchasing.infrastructure.po_repo import po_repo as _po_repo
from shared.infrastructure.database import get_connection, get_org_id


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


async def list_pos(status: str | None = None) -> list[PORow]:
    return await _po_repo.list_pos(status=status)


async def get_po(po_id: str) -> PORow | None:
    return await _po_repo.get_po(po_id)


async def get_po_items(po_id: str) -> list[POItemRow]:
    items = await _po_repo.get_po_items(po_id)
    product_ids = [i.product_id for i in items if i.product_id]
    if not product_ids:
        return items
    products = {}
    for pid in set(product_ids):
        p = await _get_product(pid)
        if p:
            products[pid] = p
    enriched = []
    for item in items:
        pid = item.product_id
        if pid and pid in products:
            p = products[pid]
            enriched.append(
                item.model_copy(
                    update={
                        "matched_sku": p.sku,
                        "matched_name": p.name,
                        "matched_quantity": p.quantity,
                        "matched_cost": p.cost,
                    }
                )
            )
        else:
            enriched.append(item)
    return enriched


# ── Agent-facing analytics queries ───────────────────────────────────────────


async def vendor_catalog(vendor_id: str) -> list[dict]:
    """SKUs supplied by a vendor with cost, lead time, moq, preferred status."""
    conn = get_connection()
    org_id = get_org_id()
    cursor = await conn.execute(
        """SELECT vi.vendor_sku, vi.cost, vi.lead_time_days, vi.moq,
                  vi.is_preferred, vi.purchase_uom, vi.purchase_pack_qty,
                  s.sku, s.name, s.quantity, s.min_stock, s.sell_uom,
                  s.category_name AS department
           FROM vendor_items vi
           JOIN skus s ON vi.sku_id = s.id AND s.deleted_at IS NULL
           WHERE vi.vendor_id = $1
             AND (vi.organization_id = $2 OR vi.organization_id IS NULL)
             AND vi.deleted_at IS NULL
           ORDER BY vi.is_preferred DESC, s.name""",
        (vendor_id, org_id),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def vendor_performance(
    vendor_id: str, days: int = 90, vendor_name: str = ""
) -> VendorPerformance:
    """PO count, total spend, avg lead time, fill rate for a vendor."""
    conn = get_connection()
    org_id = get_org_id()
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    cursor = await conn.execute(
        """SELECT COUNT(*) AS po_count,
                  ROUND(COALESCE(SUM(total), 0), 2) AS total_spend,
                  SUM(CASE WHEN status = 'received' THEN 1 ELSE 0 END) AS received_count
           FROM purchase_orders
           WHERE vendor_id = $1 AND organization_id = $2 AND created_at >= $3""",
        (vendor_id, org_id, since),
    )
    summary = dict(await cursor.fetchone())

    cursor = await conn.execute(
        """SELECT ROUND(AVG(
                    JULIANDAY(po.received_at) - JULIANDAY(po.created_at)
                  ), 1) AS avg_lead_time_days,
                  ROUND(
                    SUM(poi.delivered_qty) * 1.0
                    / NULLIF(SUM(poi.ordered_qty), 0), 2
                  ) AS fill_rate
           FROM purchase_orders po
           JOIN purchase_order_items poi ON poi.po_id = po.id
           WHERE po.vendor_id = $1 AND po.organization_id = $2
             AND po.created_at >= $3 AND po.received_at IS NOT NULL""",
        (vendor_id, org_id, since),
    )
    perf = dict(await cursor.fetchone())

    return VendorPerformance(
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        days=days,
        po_count=int(summary["po_count"]),
        total_spend=float(summary["total_spend"]),
        received_count=int(summary["received_count"]),
        avg_lead_time_days=perf.get("avg_lead_time_days"),
        fill_rate=perf.get("fill_rate"),
    )


async def purchase_history(vendor_id: str, days: int = 90, limit: int = 20) -> list[dict]:
    """Recent POs for a vendor with item summaries."""
    conn = get_connection()
    org_id = get_org_id()
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    cursor = await conn.execute(
        """SELECT id, vendor_name, document_date, total, status,
                  created_at, received_at
           FROM purchase_orders
           WHERE vendor_id = $1 AND organization_id = $2 AND created_at >= $3
           ORDER BY created_at DESC LIMIT $4""",
        (vendor_id, org_id, since, limit),
    )
    pos = [dict(r) for r in await cursor.fetchall()]

    for po in pos:
        item_cursor = await conn.execute(
            """SELECT name, ordered_qty, delivered_qty, unit_price, cost, status
               FROM purchase_order_items WHERE po_id = $1""",
            (po["id"],),
        )
        po["items"] = [dict(r) for r in await item_cursor.fetchall()]
        po["item_count"] = len(po["items"])

    return pos


async def reorder_with_vendor_context(limit: int = 30) -> list[dict]:
    """Low-stock SKUs enriched with vendor options for procurement planning."""
    conn = get_connection()
    org_id = get_org_id()

    cursor = await conn.execute(
        """SELECT s.id AS sku_id, s.sku, s.name, s.quantity, s.min_stock,
                  s.cost AS current_cost, s.sell_uom, s.category_name AS department
           FROM skus s
           WHERE s.quantity <= s.min_stock
             AND (s.organization_id = $1 OR s.organization_id IS NULL)
             AND s.deleted_at IS NULL
           ORDER BY (s.min_stock - s.quantity) DESC
           LIMIT $2""",
        (org_id, limit),
    )
    low_stock = [dict(r) for r in await cursor.fetchall()]

    for item in low_stock:
        vi_cursor = await conn.execute(
            """SELECT vi.vendor_id, vi.vendor_name, vi.cost, vi.lead_time_days,
                      vi.moq, vi.is_preferred, vi.purchase_uom, vi.purchase_pack_qty
               FROM vendor_items vi
               WHERE vi.sku_id = $1
                 AND (vi.organization_id = $2 OR vi.organization_id IS NULL)
                 AND vi.deleted_at IS NULL
               ORDER BY vi.is_preferred DESC, vi.cost ASC""",
            (item["sku_id"], org_id),
        )
        item["vendor_options"] = [dict(r) for r in await vi_cursor.fetchall()]
        item["deficit"] = round(item["min_stock"] - item["quantity"], 2)

    return low_stock
