"""Invoice application services."""
import logging

from finance.infrastructure.invoice_repo import invoice_repo
from identity.infrastructure.org_settings_repo import get_org_settings
from finance.adapters.xero_factory import get_xero_gateway

logger = logging.getLogger(__name__)


async def sync_invoice(inv_id: str, org_id: str) -> dict:
    """Sync a single invoice to Xero. Returns a result dict."""
    inv = await invoice_repo.get_by_id(inv_id, org_id)
    if not inv:
        return {"invoice_id": inv_id, "error": "Invoice not found", "success": False}

    settings = await get_org_settings(org_id)
    gateway = get_xero_gateway(settings)

    try:
        result = await gateway.sync_invoice(inv, settings)
    except Exception as e:
        return {"invoice_id": inv_id, "invoice_number": inv.get("invoice_number"), "error": str(e), "success": False}

    if result.success and result.xero_invoice_id:
        await invoice_repo.set_xero_invoice_id(inv_id, result.xero_invoice_id)

    return {
        "invoice_id": inv_id,
        "invoice_number": inv.get("invoice_number"),
        "xero_invoice_id": result.xero_invoice_id,
        "xero_journal_id": result.xero_journal_id,
        "success": result.success,
        "error": result.error,
    }
