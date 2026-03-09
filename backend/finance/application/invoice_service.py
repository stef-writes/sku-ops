"""Invoice application services — safe for cross-context import."""
import logging
from typing import Any

from finance.adapters.invoicing_factory import get_invoicing_gateway
from finance.infrastructure.invoice_repo import invoice_repo as _default_invoice_repo
from finance.ports.invoice_repo_port import InvoiceRepoPort
from identity.application.org_service import get_org_settings

logger = logging.getLogger(__name__)


async def sync_invoice(
    inv_id: str, org_id: str,
    invoice_repo: InvoiceRepoPort = _default_invoice_repo,
) -> dict:
    """Sync a single invoice to Xero. Returns a result dict."""
    inv = await invoice_repo.get_by_id(inv_id, org_id)
    if not inv:
        return {"invoice_id": inv_id, "error": "Invoice not found", "success": False}

    settings = await get_org_settings(org_id)
    gateway = get_invoicing_gateway(settings)

    # Recovery: if a previous sync attempt was interrupted after calling Xero but
    # before persisting the xero_invoice_id locally, check Xero by invoice number.
    if inv.get("xero_sync_status") == "syncing":
        try:
            existing = await gateway.fetch_invoice_by_number(
                inv.get("invoice_number"), settings
            )
            if existing:
                xero_id = existing["InvoiceID"]
                await invoice_repo.set_xero_invoice_id(inv_id, xero_id)
                return {"invoice_id": inv_id, "xero_invoice_id": xero_id, "success": True}
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning("Idempotency check failed for %s: %s", inv_id, e)

    await invoice_repo.set_xero_sync_status(inv_id, "syncing")

    try:
        result = await gateway.sync_invoice(inv, settings)
    except (RuntimeError, OSError, ValueError) as e:
        await invoice_repo.set_xero_sync_status(inv_id, "failed")
        return {"invoice_id": inv_id, "invoice_number": inv.get("invoice_number"), "error": str(e), "success": False}

    if result.success and result.xero_invoice_id:
        await invoice_repo.set_xero_invoice_id(
            inv_id,
            result.xero_invoice_id,
            xero_cogs_journal_id=result.xero_journal_id,
        )
    else:
        await invoice_repo.set_xero_sync_status(inv_id, "failed")

    return {
        "invoice_id": inv_id,
        "invoice_number": inv.get("invoice_number"),
        "xero_invoice_id": result.xero_invoice_id,
        "xero_journal_id": result.xero_journal_id,
        "success": result.success,
        "error": result.error,
    }


async def mark_paid_for_withdrawal(
    withdrawal_id: str,
    invoice_repo: InvoiceRepoPort = _default_invoice_repo,
) -> None:
    await invoice_repo.mark_paid_for_withdrawal(withdrawal_id)


async def create_invoice_from_withdrawals(
    withdrawal_ids: list, organization_id: str | None = None, conn: Any = None,
    invoice_repo: InvoiceRepoPort = _default_invoice_repo,
) -> dict:
    return await invoice_repo.create_from_withdrawals(withdrawal_ids, organization_id=organization_id, conn=conn)


async def list_invoices(
    organization_id: str,
    invoice_repo: InvoiceRepoPort = _default_invoice_repo,
    **kwargs,
):
    return await invoice_repo.list_invoices(organization_id=organization_id, **kwargs)


async def get_invoice(
    invoice_id: str, org_id: str,
    invoice_repo: InvoiceRepoPort = _default_invoice_repo,
):
    return await invoice_repo.get_by_id(invoice_id, org_id)


async def repost_cogs_for_invoice(
    inv_id: str, org_id: str,
    invoice_repo: InvoiceRepoPort = _default_invoice_repo,
) -> dict:
    """Re-post the COGS manual journal for an invoice whose line items changed after sync.

    Voids the old Xero journal (if we have its ID), posts a fresh one with current
    line item costs, and marks the invoice as synced again.
    """
    inv = await invoice_repo.get_by_id(inv_id, org_id)
    if not inv:
        return {"invoice_id": inv_id, "error": "Invoice not found", "success": False}
    if not inv.get("xero_invoice_id"):
        return {"invoice_id": inv_id, "error": "Invoice not yet synced to Xero", "success": False}

    settings = await get_org_settings(org_id)
    gateway = get_invoicing_gateway(settings)

    try:
        new_journal_id = await gateway.repost_cogs_journal(
            inv, settings, old_journal_id=inv.get("xero_cogs_journal_id")
        )
        await invoice_repo.set_xero_invoice_id(
            inv_id,
            inv["xero_invoice_id"],
            xero_cogs_journal_id=new_journal_id,
        )
        return {"invoice_id": inv_id, "xero_cogs_journal_id": new_journal_id, "success": True}
    except (RuntimeError, OSError, ValueError) as e:
        await invoice_repo.set_xero_sync_status(inv_id, "failed")
        return {"invoice_id": inv_id, "error": str(e), "success": False}
