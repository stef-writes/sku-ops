"""Purchase order repository — typed implementation of PORepoPort."""
from typing import List, Optional

from shared.infrastructure.database import get_connection
from purchasing.domain.purchase_order import PurchaseOrder, PurchaseOrderItem, POItemStatus
from purchasing.ports.po_repo_port import PORepoPort


def _row(row) -> Optional[dict]:
    return dict(row) if row is not None else None


class PgPORepo(PORepoPort):

    async def insert_po(self, po: PurchaseOrder) -> None:
        conn = get_connection()
        d = po.model_dump()
        await conn.execute(
            """INSERT INTO purchase_orders
               (id, vendor_id, vendor_name, document_date, total, status, notes,
                created_by_id, created_by_name, received_at, received_by_id, received_by_name,
                created_at, updated_at, organization_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                d["id"], d["vendor_id"], d["vendor_name"], d.get("document_date"),
                d.get("total"), d["status"], d.get("notes"),
                d["created_by_id"], d["created_by_name"],
                d.get("received_at"), d.get("received_by_id"), d.get("received_by_name"),
                d["created_at"], d["updated_at"], d["organization_id"],
            ),
        )
        await conn.commit()

    async def insert_items(self, items: List[PurchaseOrderItem]) -> None:
        conn = get_connection()
        for item in items:
            d = item.model_dump()
            await conn.execute(
                """INSERT INTO purchase_order_items
                   (id, po_id, name, original_sku, ordered_qty, delivered_qty, unit_price, cost,
                    base_unit, sell_uom, pack_qty, suggested_department, status, product_id, organization_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    d["id"], d["po_id"], d["name"], d.get("original_sku"),
                    d["ordered_qty"], d["delivered_qty"],
                    d["unit_price"], d["cost"],
                    d["base_unit"], d["sell_uom"],
                    d["pack_qty"], d["suggested_department"],
                    d["status"], d.get("product_id"),
                    d["organization_id"],
                ),
            )
        await conn.commit()

    async def list_pos(self, org_id: str, status: Optional[str] = None) -> List[dict]:
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

    async def get_po(self, po_id: str, org_id: str) -> Optional[dict]:
        conn = get_connection()
        cursor = await conn.execute(
            "SELECT * FROM purchase_orders WHERE id = ? AND organization_id = ?",
            (po_id, org_id),
        )
        row = await cursor.fetchone()
        return _row(row)

    async def get_po_items(self, po_id: str) -> List[dict]:
        conn = get_connection()
        cursor = await conn.execute(
            """SELECT poi.*,
                      p.quantity AS matched_quantity,
                      p.sku      AS matched_sku,
                      p.name     AS matched_name,
                      p.cost     AS matched_cost
               FROM purchase_order_items poi
               LEFT JOIN products p ON p.id = poi.product_id
               WHERE poi.po_id = ?
               ORDER BY poi.id""",
            (po_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def update_po_item(
        self,
        item_id: str,
        status: POItemStatus,
        product_id: Optional[str] = None,
        delivered_qty: Optional[float] = None,
    ) -> None:
        conn = get_connection()
        await conn.execute(
            """UPDATE purchase_order_items
               SET status = ?, product_id = COALESCE(?, product_id),
                   delivered_qty = COALESCE(?, delivered_qty)
               WHERE id = ?""",
            (status.value, product_id, delivered_qty, item_id),
        )
        await conn.commit()

    async def update_po_status(
        self,
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


po_repo = PgPORepo()
