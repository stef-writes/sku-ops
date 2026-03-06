"""PO → Xero Bill sync service.

Decouples the purchasing API from the Xero integration.
The route calls queue_po_for_sync(); the nightly job calls sync_pending_po_bills().
"""
import logging
from datetime import UTC
from typing import Optional

from finance.adapters.invoicing_factory import get_invoicing_gateway
from identity.application.org_service import get_org_settings
from shared.infrastructure.database import get_connection

logger = logging.getLogger(__name__)


async def queue_po_for_sync(po_id: str) -> None:
    """Mark a PO as pending Xero sync. Called after stock is received."""
    conn = get_connection()
    from datetime import datetime, timezone
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        "UPDATE purchase_orders SET xero_sync_status = 'pending', updated_at = ? WHERE id = ?",
        (now, po_id),
    )
    await conn.commit()


async def set_po_xero_bill_id(po_id: str, xero_bill_id: str) -> None:
    conn = get_connection()
    from datetime import datetime, timezone
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        "UPDATE purchase_orders SET xero_bill_id = ?, xero_sync_status = 'synced', updated_at = ? WHERE id = ?",
        (xero_bill_id, now, po_id),
    )
    await conn.commit()


async def set_po_sync_status(po_id: str, status: str) -> None:
    conn = get_connection()
    from datetime import datetime, timezone
    now = datetime.now(UTC).isoformat()
    await conn.execute(
        "UPDATE purchase_orders SET xero_sync_status = ?, updated_at = ? WHERE id = ?",
        (status, now, po_id),
    )
    await conn.commit()


async def list_unsynced_po_bills(org_id: str) -> list[dict]:
    """Return POs pending Xero Bill sync for this org."""
    conn = get_connection()
    cursor = await conn.execute(
        """SELECT * FROM purchase_orders
           WHERE organization_id = ? AND xero_sync_status = 'pending'
             AND xero_bill_id IS NULL
           ORDER BY created_at""",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def list_failed_po_bills(org_id: str) -> list[dict]:
    """Return POs whose Xero Bill sync has failed."""
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM purchase_orders WHERE organization_id = ? AND xero_sync_status = 'failed' ORDER BY updated_at DESC",
        (org_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def sync_po_bill(po_id: str, org_id: str, cost_total: float | None = None) -> dict:
    """Sync a single PO to Xero as a Bill. Returns a result dict."""
    conn = get_connection()
    cursor = await conn.execute(
        "SELECT * FROM purchase_orders WHERE id = ? AND organization_id = ?",
        (po_id, org_id),
    )
    row = await cursor.fetchone()
    if not row:
        return {"po_id": po_id, "success": False, "error": "PO not found"}

    po = dict(row)

    if cost_total is None:
        cursor = await conn.execute(
            "SELECT SUM(cost * COALESCE(delivered_qty, ordered_qty)) FROM purchase_order_items WHERE po_id = ?",
            (po_id,),
        )
        total_row = await cursor.fetchone()
        cost_total = float(total_row[0] or 0)

    if cost_total <= 0:
        await set_po_sync_status(po_id, "skipped")
        return {"po_id": po_id, "success": True, "skipped": True, "reason": "zero cost"}

    cursor = await conn.execute(
        """SELECT name, COALESCE(delivered_qty, ordered_qty) AS qty, cost
           FROM purchase_order_items WHERE po_id = ?""",
        (po_id,),
    )
    item_rows = await cursor.fetchall()
    po["items"] = [dict(r) for r in item_rows]

    settings = await get_org_settings(org_id)
    gateway = get_invoicing_gateway(settings)

    try:
        result = await gateway.sync_po_receipt(po, cost_total, settings)
    except Exception as e:
        await set_po_sync_status(po_id, "failed")
        logger.error("PO bill sync failed for %s: %s", po_id, e)
        return {"po_id": po_id, "success": False, "error": str(e)}

    if result.success and result.xero_invoice_id:
        await set_po_xero_bill_id(po_id, result.xero_invoice_id)
    elif not result.success:
        await set_po_sync_status(po_id, "failed")

    return {
        "po_id": po_id,
        "xero_bill_id": result.xero_invoice_id,
        "success": result.success,
        "error": result.error,
    }
