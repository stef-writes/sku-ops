"""Purchase order repository."""
from typing import Optional

from db import get_connection


def _row(row) -> Optional[dict]:
    return dict(row) if row is not None else None


async def create_po(po: dict) -> None:
    conn = get_connection()
    await conn.execute(
        """INSERT INTO purchase_orders
           (id, vendor_id, vendor_name, document_date, total, status, notes,
            created_by_id, created_by_name, received_at, received_by_id, received_by_name,
            created_at, organization_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            po["id"], po.get("vendor_id"), po["vendor_name"], po.get("document_date"),
            po.get("total"), po["status"], po.get("notes"),
            po.get("created_by_id", ""), po.get("created_by_name", ""),
            po.get("received_at"), po.get("received_by_id"), po.get("received_by_name"),
            po["created_at"], po.get("organization_id", "default"),
        ),
    )
    await conn.commit()


async def create_po_items(items: list) -> None:
    conn = get_connection()
    for item in items:
        await conn.execute(
            """INSERT INTO purchase_order_items
               (id, po_id, name, original_sku, ordered_qty, delivered_qty, price, cost,
                base_unit, sell_uom, pack_qty, suggested_department, status, product_id, organization_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item["id"], item["po_id"], item["name"], item.get("original_sku"),
                item.get("ordered_qty", 1), item.get("delivered_qty"),
                item.get("price", 0), item.get("cost", 0),
                item.get("base_unit", "each"), item.get("sell_uom", "each"),
                item.get("pack_qty", 1), item.get("suggested_department", "HDW"),
                item.get("status", "pending"), item.get("product_id"),
                item.get("organization_id", "default"),
            ),
        )
    await conn.commit()


async def list_pos(org_id: str, status: Optional[str] = None) -> list:
    conn = get_connection()
    if status:
        cursor = await conn.execute(
            "SELECT * FROM purchase_orders WHERE organization_id = ? AND status = ? ORDER BY created_at DESC",
            (org_id, status),
        )
    else:
        cursor = await conn.execute(
            "SELECT * FROM purchase_orders WHERE organization_id = ? ORDER BY created_at DESC",
            (org_id,),
        )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_po(po_id: str, org_id: str) -> Optional[dict]:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM purchase_orders WHERE id = ? AND organization_id = ?",
        (po_id, org_id),
    )
    row = await cursor.fetchone()
    return _row(row)


async def get_po_items(po_id: str) -> list:
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM purchase_order_items WHERE po_id = ? ORDER BY rowid",
        (po_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def update_po_item(
    item_id: str,
    status: str,
    product_id: Optional[str] = None,
    delivered_qty: Optional[int] = None,
) -> None:
    conn = get_connection()
    await conn.execute(
        """UPDATE purchase_order_items
           SET status = ?, product_id = COALESCE(?, product_id),
               delivered_qty = COALESCE(?, delivered_qty)
           WHERE id = ?""",
        (status, product_id, delivered_qty, item_id),
    )
    await conn.commit()


async def update_po_status(
    po_id: str,
    status: str,
    received_at: Optional[str] = None,
    received_by_id: Optional[str] = None,
    received_by_name: Optional[str] = None,
) -> None:
    conn = get_connection()
    await conn.execute(
        """UPDATE purchase_orders
           SET status = ?,
               received_at = COALESCE(?, received_at),
               received_by_id = COALESCE(?, received_by_id),
               received_by_name = COALESCE(?, received_by_name)
           WHERE id = ?""",
        (status, received_at, received_by_id, received_by_name, po_id),
    )
    await conn.commit()
