"""Purchase order repository — typed implementation of PORepoPort."""

from purchasing.domain.purchase_order import (
    POItemRow,
    POItemStatus,
    PORow,
    PurchaseOrder,
    PurchaseOrderItem,
)
from purchasing.ports.po_repo_port import PORepoPort
from shared.infrastructure.database import get_connection, get_org_id


def _row(row) -> dict | None:
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
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)""",
            (
                d["id"],
                d["vendor_id"],
                d["vendor_name"],
                d.get("document_date"),
                d.get("total"),
                d["status"],
                d.get("notes"),
                d["created_by_id"],
                d["created_by_name"],
                d.get("received_at"),
                d.get("received_by_id"),
                d.get("received_by_name"),
                d["created_at"],
                d["updated_at"],
                d["organization_id"],
            ),
        )
        await conn.commit()

    async def insert_items(self, items: list[PurchaseOrderItem]) -> None:
        conn = get_connection()
        for item in items:
            d = item.model_dump()
            await conn.execute(
                """INSERT INTO purchase_order_items
                   (id, po_id, name, original_sku, ordered_qty, delivered_qty, unit_price, cost,
                    base_unit, sell_uom, pack_qty, purchase_uom, purchase_pack_qty,
                    suggested_department, status, product_id, organization_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)""",
                (
                    d["id"],
                    d["po_id"],
                    d["name"],
                    d.get("original_sku"),
                    d["ordered_qty"],
                    d["delivered_qty"],
                    d["unit_price"],
                    d["cost"],
                    d["base_unit"],
                    d["sell_uom"],
                    d["pack_qty"],
                    d.get("purchase_uom", "each"),
                    d.get("purchase_pack_qty", 1),
                    d["suggested_department"],
                    d["status"],
                    d.get("product_id"),
                    d["organization_id"],
                ),
            )
        await conn.commit()

    async def list_pos(self, status: str | None = None) -> list[PORow]:
        conn = get_connection()
        org_id = get_org_id()
        if status:
            cursor = await conn.execute(
                "SELECT * FROM purchase_orders WHERE organization_id = $1 AND status = $2 ORDER BY created_at DESC",
                (org_id, status),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM purchase_orders WHERE organization_id = $1 ORDER BY created_at DESC",
                (org_id,),
            )
        rows = await cursor.fetchall()
        return [PORow.model_validate(dict(r)) for r in rows]

    async def get_po(self, po_id: str) -> PORow | None:
        conn = get_connection()
        org_id = get_org_id()
        cursor = await conn.execute(
            "SELECT * FROM purchase_orders WHERE id = $1 AND organization_id = $2",
            (po_id, org_id),
        )
        row = await cursor.fetchone()
        return PORow.model_validate(dict(row)) if row else None

    async def get_po_items(self, po_id: str) -> list[POItemRow]:
        conn = get_connection()
        org_id = get_org_id()
        cursor = await conn.execute(
            "SELECT * FROM purchase_order_items WHERE po_id = $1 AND organization_id = $2 ORDER BY id",
            (po_id, org_id),
        )
        rows = await cursor.fetchall()
        return [POItemRow.model_validate(dict(r)) for r in rows]

    async def update_po_item(
        self,
        item_id: str,
        status: POItemStatus,
        product_id: str | None = None,
        delivered_qty: float | None = None,
    ) -> bool:
        conn = get_connection()
        org_id = get_org_id()
        cursor = await conn.execute(
            """UPDATE purchase_order_items
               SET status = $1, product_id = COALESCE($2, product_id),
                   delivered_qty = COALESCE($3, delivered_qty)
               WHERE id = $4 AND status != $5 AND organization_id = $6""",
            (status.value, product_id, delivered_qty, item_id, POItemStatus.ARRIVED.value, org_id),
        )
        await conn.commit()
        return cursor.rowcount > 0

    async def update_po_status(
        self,
        po_id: str,
        status: str,
        received_at: str | None = None,
        received_by_id: str | None = None,
        received_by_name: str | None = None,
    ) -> None:
        conn = get_connection()
        org_id = get_org_id()
        await conn.execute(
            """UPDATE purchase_orders
               SET status = $1,
                   received_at = COALESCE($2, received_at),
                   received_by_id = COALESCE($3, received_by_id),
                   received_by_name = COALESCE($4, received_by_name)
               WHERE id = $5 AND organization_id = $6""",
            (status, received_at, received_by_id, received_by_name, po_id, org_id),
        )
        await conn.commit()

    async def list_unsynced_po_bills(self) -> list[dict]:
        """Return received POs with pending Xero sync."""
        conn = get_connection()
        org_id = get_org_id()
        cursor = await conn.execute(
            """SELECT id, vendor_name, total, document_date, created_at
               FROM purchase_orders
               WHERE organization_id = $1
                 AND status = 'received'
                 AND xero_bill_id IS NULL
                 AND xero_sync_status = 'pending'
               ORDER BY created_at""",
            (org_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def list_failed_po_bills(self) -> list[dict]:
        conn = get_connection()
        org_id = get_org_id()
        cursor = await conn.execute(
            """SELECT id, vendor_name, total, document_date, created_at
               FROM purchase_orders
               WHERE organization_id = $1
                 AND xero_sync_status = 'failed'
               ORDER BY created_at""",
            (org_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_po_with_cost(self, po_id: str) -> dict | None:
        """Get PO with computed cost_total and items for Xero sync."""
        conn = get_connection()
        org_id = get_org_id()
        cursor = await conn.execute(
            "SELECT * FROM purchase_orders WHERE id = $1 AND organization_id = $2",
            (po_id, org_id),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        po = dict(row)
        cursor = await conn.execute(
            "SELECT SUM(cost * COALESCE(delivered_qty, ordered_qty)) FROM purchase_order_items WHERE po_id = $1",
            (po_id,),
        )
        total_row = await cursor.fetchone()
        po["cost_total"] = float(total_row[0] or 0) if total_row else 0.0
        cursor = await conn.execute(
            """SELECT name, COALESCE(delivered_qty, ordered_qty) AS qty, cost
               FROM purchase_order_items WHERE po_id = $1""",
            (po_id,),
        )
        item_rows = await cursor.fetchall()
        po["items"] = [dict(r) for r in item_rows]
        return po

    async def set_xero_sync_status(self, po_id: str, status: str, updated_at: str) -> None:
        conn = get_connection()
        org_id = get_org_id()
        await conn.execute(
            "UPDATE purchase_orders SET xero_sync_status = $1, updated_at = $2 WHERE id = $3 AND organization_id = $4",
            (status, updated_at, po_id, org_id),
        )
        await conn.commit()

    async def summary_by_status(self) -> dict[str, dict]:
        """Return {status: {count, total}} for all POs in the org."""
        conn = get_connection()
        org_id = get_org_id()
        cursor = await conn.execute(
            """SELECT status, COUNT(*) as cnt, COALESCE(SUM(total), 0) as total
               FROM purchase_orders WHERE organization_id = $1
               GROUP BY status""",
            (org_id,),
        )
        rows = await cursor.fetchall()
        return {r["status"]: {"count": r["cnt"], "total": float(r["total"])} for r in rows}

    async def set_xero_bill_id(self, po_id: str, xero_bill_id: str, updated_at: str) -> None:
        conn = get_connection()
        org_id = get_org_id()
        await conn.execute(
            "UPDATE purchase_orders SET xero_bill_id = $1, xero_sync_status = 'synced', updated_at = $2 WHERE id = $3 AND organization_id = $4",
            (xero_bill_id, updated_at, po_id, org_id),
        )
        await conn.commit()


po_repo = PgPORepo()
