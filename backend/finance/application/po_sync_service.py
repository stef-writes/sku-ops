"""PO → Xero Bill sync service.

Decouples the purchasing API from the Xero integration.
The route calls queue_po_for_sync(); the nightly job calls sync_pending_po_bills().
"""

import logging
from datetime import UTC, datetime

from finance.adapters.invoicing_factory import get_invoicing_gateway
from finance.application.org_settings_service import get_xero_settings
from finance.application.sync_results import POBillSyncResult
from purchasing.application.queries import (
    get_po_with_cost,
    set_xero_bill_id,
    set_xero_sync_status,
)

logger = logging.getLogger(__name__)


async def queue_po_for_sync(po_id: str) -> None:
    """Mark a PO as pending Xero sync. Called after stock is received."""
    now = datetime.now(UTC).isoformat()
    await set_xero_sync_status(po_id, "pending", now)


async def sync_po_bill(po_id: str, cost_total: float | None = None) -> POBillSyncResult:
    """Sync a single PO to Xero as a Bill."""
    po = await get_po_with_cost(po_id)
    if not po:
        return POBillSyncResult(po_id=po_id, success=False, error="PO not found")

    if cost_total is None:
        cost_total = po.get("cost_total", 0.0)

    if cost_total <= 0:
        now = datetime.now(UTC).isoformat()
        await set_xero_sync_status(po_id, "skipped", now)
        return POBillSyncResult(po_id=po_id, success=True, skipped=True, reason="zero cost")

    xero_settings = await get_xero_settings()
    gateway = get_invoicing_gateway(xero_settings)

    try:
        result = await gateway.sync_po_receipt(po, cost_total, xero_settings)
    except Exception as e:
        now = datetime.now(UTC).isoformat()
        await set_xero_sync_status(po_id, "failed", now)
        logger.exception("PO bill sync failed for %s", po_id)
        return POBillSyncResult(po_id=po_id, success=False, error=str(e))

    now = datetime.now(UTC).isoformat()
    if result.success and result.external_id:
        await set_xero_bill_id(po_id, result.external_id, now)
    elif not result.success:
        await set_xero_sync_status(po_id, "failed", now)

    return POBillSyncResult(
        po_id=po_id,
        success=result.success,
        xero_bill_id=result.external_id,
        error=result.error,
    )
