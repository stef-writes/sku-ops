"""Invoice sync — Xero synchronization and COGS repost."""

import logging

from finance.adapters.invoicing_factory import get_invoicing_gateway
from finance.application.org_settings_service import get_org_settings
from finance.domain.invoice import InvoiceWithDetails
from finance.domain.xero_settings import XeroSettings
from finance.infrastructure.invoice_repo import (
    invoice_repo as _default_invoice_repo,
)
from finance.ports.invoice_repo_port import InvoiceRepoPort

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Xero sync
# ---------------------------------------------------------------------------


async def sync_invoice(
    inv_id: str,
    invoice_repo: InvoiceRepoPort = _default_invoice_repo,
) -> dict:
    """Sync a single invoice to Xero. Returns a result dict."""
    inv = await invoice_repo.get_by_id(inv_id)
    if not inv:
        return {"invoice_id": inv_id, "error": "Invoice not found", "success": False}

    if inv.xero_sync_status == "syncing":
        try:
            existing = await _gateway_fetch_existing(inv, invoice_repo)
            if existing:
                return existing
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning("Idempotency check failed for %s: %s", inv_id, e)

    await invoice_repo.set_xero_sync_status(inv_id, "syncing")

    org_settings = await get_org_settings()
    xero_settings = XeroSettings.model_validate(org_settings.model_dump())
    gateway = get_invoicing_gateway(xero_settings)

    try:
        result = await gateway.sync_invoice(inv, xero_settings)
    except (RuntimeError, OSError, ValueError) as e:
        await invoice_repo.set_xero_sync_status(inv_id, "failed")
        return {
            "invoice_id": inv_id,
            "invoice_number": inv.invoice_number,
            "error": str(e),
            "success": False,
        }

    if result.success and result.external_id:
        await invoice_repo.set_xero_invoice_id(
            inv_id,
            result.external_id,
            xero_cogs_journal_id=result.external_journal_id,
        )
    else:
        await invoice_repo.set_xero_sync_status(inv_id, "failed")

    return {
        "invoice_id": inv_id,
        "invoice_number": inv.invoice_number,
        "xero_invoice_id": result.external_id,
        "xero_journal_id": result.external_journal_id,
        "success": result.success,
        "error": result.error,
    }


async def _gateway_fetch_existing(
    inv: InvoiceWithDetails,
    invoice_repo: InvoiceRepoPort,
) -> dict | None:
    """Check Xero for an existing invoice matching our number (idempotency guard)."""
    org_settings = await get_org_settings()
    xero_settings = XeroSettings.model_validate(org_settings.model_dump())
    gateway = get_invoicing_gateway(xero_settings)
    existing = await gateway.fetch_invoice_by_number(inv.invoice_number, xero_settings)
    if existing:
        xero_id = existing["InvoiceID"]
        await invoice_repo.set_xero_invoice_id(inv.id, xero_id)
        return {"invoice_id": inv.id, "xero_invoice_id": xero_id, "success": True}
    return None


# ---------------------------------------------------------------------------
# COGS repost
# ---------------------------------------------------------------------------


async def repost_cogs_for_invoice(
    inv_id: str,
    invoice_repo: InvoiceRepoPort = _default_invoice_repo,
) -> dict:
    """Re-post the COGS manual journal for an invoice whose line items changed after sync."""
    inv = await invoice_repo.get_by_id(inv_id)
    if not inv:
        return {"invoice_id": inv_id, "error": "Invoice not found", "success": False}
    if not inv.xero_invoice_id:
        return {"invoice_id": inv_id, "error": "Invoice not yet synced to Xero", "success": False}

    org_settings = await get_org_settings()
    xero_settings = XeroSettings.model_validate(org_settings.model_dump())
    gateway = get_invoicing_gateway(xero_settings)

    try:
        new_journal_id = await gateway.repost_cogs_journal(
            inv, xero_settings, old_journal_id=inv.xero_cogs_journal_id
        )
        await invoice_repo.set_xero_invoice_id(
            inv_id,
            inv.xero_invoice_id,
            xero_cogs_journal_id=new_journal_id,
        )
        return {"invoice_id": inv_id, "xero_cogs_journal_id": new_journal_id, "success": True}
    except (RuntimeError, OSError, ValueError) as e:
        await invoice_repo.set_xero_sync_status(inv_id, "failed")
        return {"invoice_id": inv_id, "error": str(e), "success": False}
