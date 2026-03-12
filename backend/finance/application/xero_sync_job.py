"""Nightly Xero sync job.

Three passes in order:
  1. Outbound sync — push unsynced invoices, credit notes, and PO bills to Xero.
  2. Reconciliation — fetch synced documents back from Xero and verify totals + line counts.
  3. Exception summary — return counts of every problem category for the health dashboard.

Call run_sync() from a scheduler or manually via the /api/xero/sync endpoint.
"""

import logging

from finance.adapters.invoicing_factory import get_invoicing_gateway
from finance.application.invoice_service import repost_cogs_for_invoice, sync_invoice
from finance.application.org_settings_service import get_org_settings
from finance.application.po_sync_service import sync_po_bill
from finance.domain.xero_settings import XeroSettings
from finance.infrastructure.credit_note_repo import credit_note_repo
from finance.infrastructure.invoice_repo import invoice_repo
from purchasing.application.queries import list_unsynced_po_bills
from shared.infrastructure.database import get_org_id

logger = logging.getLogger(__name__)

_TOTAL_TOLERANCE = 0.02  # allow 2 cent rounding drift before flagging mismatch


async def _sync_outbound_invoices() -> dict:
    unsynced = await invoice_repo.list_unsynced_invoices()
    results = {"synced": 0, "failed": 0, "errors": []}
    for inv in unsynced:
        inv_id = inv.id
        try:
            result = await sync_invoice(inv_id)
            if result.get("success"):
                results["synced"] += 1
                logger.info("Invoice %s synced to Xero: %s", inv_id, result.get("xero_invoice_id"))
            else:
                await invoice_repo.set_xero_sync_status(inv_id, "failed")
                results["failed"] += 1
                results["errors"].append(
                    {
                        "type": "invoice",
                        "id": inv_id,
                        "number": inv.invoice_number,
                        "error": result.get("error"),
                    }
                )
                logger.warning("Invoice %s sync failed: %s", inv_id, result.get("error"))
        except Exception as e:
            await invoice_repo.set_xero_sync_status(inv_id, "failed")
            results["failed"] += 1
            results["errors"].append({"type": "invoice", "id": inv_id, "error": str(e)})
            logger.exception("Invoice %s sync exception", inv_id)
    return results


async def _sync_outbound_credit_notes(gateway, settings) -> dict:
    unsynced = await credit_note_repo.list_unsynced_credit_notes()
    results = {"synced": 0, "failed": 0, "errors": []}
    for cn in unsynced:
        cn_id = cn.id
        try:
            full_cn = await credit_note_repo.get_by_id(cn_id)
            if not full_cn:
                continue
            result = await gateway.sync_credit_note(full_cn, settings)
            if result.success and result.external_id:
                await credit_note_repo.set_xero_credit_note_id(cn_id, result.external_id)
                results["synced"] += 1
                logger.info("Credit note %s synced to Xero: %s", cn_id, result.external_id)
            else:
                await credit_note_repo.set_credit_note_sync_status(cn_id, "failed")
                results["failed"] += 1
                results["errors"].append(
                    {
                        "type": "credit_note",
                        "id": cn_id,
                        "number": cn.credit_note_number,
                        "error": result.error,
                    }
                )
                logger.warning("Credit note %s sync failed: %s", cn_id, result.error)
        except Exception as e:
            await credit_note_repo.set_credit_note_sync_status(cn_id, "failed")
            results["failed"] += 1
            results["errors"].append({"type": "credit_note", "id": cn_id, "error": str(e)})
            logger.exception("Credit note %s sync exception", cn_id)
    return results


async def _sync_outbound_po_bills() -> dict:
    unsynced = await list_unsynced_po_bills()
    results = {"synced": 0, "failed": 0, "errors": []}
    for po in unsynced:
        po_id = po["id"]
        try:
            result = await sync_po_bill(po_id)
            if result.get("success") and not result.get("skipped"):
                results["synced"] += 1
                logger.info("PO %s synced to Xero as bill: %s", po_id, result.get("xero_bill_id"))
            elif not result.get("skipped"):
                results["failed"] += 1
                results["errors"].append(
                    {
                        "type": "po_bill",
                        "id": po_id,
                        "vendor": po.get("vendor_name"),
                        "error": result.get("error"),
                    }
                )
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"type": "po_bill", "id": po_id, "error": str(e)})
            logger.exception("PO %s bill sync exception", po_id)
    return results


async def _repost_stale_cogs() -> dict:
    """Pass 1b — re-post COGS journals for invoices whose line items changed after sync."""
    stale = await invoice_repo.list_stale_cogs_invoices()
    results = {"reposted": 0, "failed": 0, "errors": []}
    for inv in stale:
        inv_id = inv.id
        try:
            result = await repost_cogs_for_invoice(inv_id)
            if result.get("success"):
                results["reposted"] += 1
                logger.info(
                    "COGS re-posted for invoice %s: new journal %s",
                    inv_id,
                    result.get("xero_cogs_journal_id"),
                )
            else:
                results["failed"] += 1
                results["errors"].append(
                    {
                        "type": "cogs_repost",
                        "id": inv_id,
                        "number": inv.invoice_number,
                        "error": result.get("error"),
                    }
                )
                logger.warning(
                    "COGS re-post failed for invoice %s: %s", inv_id, result.get("error")
                )
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"type": "cogs_repost", "id": inv_id, "error": str(e)})
            logger.exception("COGS re-post exception for invoice %s", inv_id)
    return results


async def _reconcile_invoices(gateway, settings) -> dict:
    to_reconcile = await invoice_repo.list_invoices_needing_reconciliation()
    results = {"verified": 0, "mismatch": 0, "errors": []}
    for inv in to_reconcile:
        inv_id = inv.id
        xero_id = inv.xero_invoice_id
        try:
            xero_data = await gateway.fetch_invoice(xero_id, settings)
            if not xero_data or xero_data.get("status") == "STUB":
                continue
            total_ok = abs(float(xero_data.get("total", 0)) - float(inv.total)) <= _TOTAL_TOLERANCE
            line_ok = xero_data.get("line_count", 0) == inv.line_count
            if total_ok and line_ok:
                results["verified"] += 1
            else:
                await invoice_repo.set_xero_sync_status(inv_id, "mismatch")
                results["mismatch"] += 1
                results["errors"].append(
                    {
                        "type": "invoice_mismatch",
                        "id": inv_id,
                        "number": inv.invoice_number,
                        "local_total": inv.total,
                        "xero_total": xero_data.get("total"),
                        "local_lines": inv.line_count,
                        "xero_lines": xero_data.get("line_count"),
                    }
                )
                logger.warning(
                    "Invoice %s mismatch: local total=%.2f xero total=%.2f lines=%s/%s",
                    inv_id,
                    inv.total,
                    xero_data.get("total", 0),
                    inv.line_count,
                    xero_data.get("line_count"),
                )
        except Exception as e:
            results["errors"].append(
                {"type": "invoice_reconcile_error", "id": inv_id, "error": str(e)}
            )
            logger.exception("Invoice %s reconcile exception", inv_id)
    return results


async def _reconcile_credit_notes(gateway, settings) -> dict:
    to_reconcile = await credit_note_repo.list_credit_notes_needing_reconciliation()
    results = {"verified": 0, "mismatch": 0, "errors": []}
    for cn in to_reconcile:
        cn_id = cn.id
        xero_id = cn.xero_credit_note_id
        try:
            xero_data = await gateway.fetch_credit_note(xero_id, settings)
            if not xero_data or xero_data.get("status") == "STUB":
                continue
            total_ok = abs(float(xero_data.get("total", 0)) - float(cn.total)) <= _TOTAL_TOLERANCE
            line_ok = xero_data.get("line_count", 0) == cn.line_count
            if total_ok and line_ok:
                results["verified"] += 1
            else:
                await credit_note_repo.set_credit_note_sync_status(cn_id, "mismatch")
                results["mismatch"] += 1
                results["errors"].append(
                    {
                        "type": "credit_note_mismatch",
                        "id": cn_id,
                        "number": cn.credit_note_number,
                        "local_total": cn.total,
                        "xero_total": xero_data.get("total"),
                    }
                )
                logger.warning(
                    "Credit note %s mismatch: local=%.2f xero=%.2f",
                    cn_id,
                    cn.total,
                    xero_data.get("total", 0),
                )
        except Exception as e:
            results["errors"].append({"type": "cn_reconcile_error", "id": cn_id, "error": str(e)})
            logger.exception("Credit note %s reconcile exception", cn_id)
    return results


async def run_sync(reconcile: bool = True) -> dict:
    """Run the full outbound sync + reconciliation for an org.

    Returns a summary dict suitable for logging or returning from an API endpoint.
    Safe to call repeatedly — idempotency is enforced per document via xero_invoice_id guards.
    """
    org_settings = await get_org_settings(get_org_id())
    xero_settings = XeroSettings.model_validate(org_settings.model_dump())
    gateway = get_invoicing_gateway(xero_settings)

    # Pass 1 — outbound sync
    invoice_sync = await _sync_outbound_invoices()
    cogs_repost = await _repost_stale_cogs()
    cn_sync = await _sync_outbound_credit_notes(gateway, xero_settings)
    po_sync = await _sync_outbound_po_bills()

    # Pass 2 — reconciliation
    invoice_reconcile: dict = {"verified": 0, "mismatch": 0, "errors": []}
    cn_reconcile: dict = {"verified": 0, "mismatch": 0, "errors": []}
    if reconcile:
        xero_settings = XeroSettings.model_validate((await get_org_settings(get_org_id())).model_dump())
        gateway = get_invoicing_gateway(xero_settings)
        invoice_reconcile = await _reconcile_invoices(gateway, xero_settings)
        cn_reconcile = await _reconcile_credit_notes(gateway, xero_settings)

    org_id = get_org_id()
    summary = {
        "org_id": org_id,
        "invoices_synced": invoice_sync["synced"],
        "invoices_failed": invoice_sync["failed"],
        "cogs_reposted": cogs_repost["reposted"],
        "cogs_repost_failed": cogs_repost["failed"],
        "credit_notes_synced": cn_sync["synced"],
        "credit_notes_failed": cn_sync["failed"],
        "po_bills_synced": po_sync["synced"],
        "po_bills_failed": po_sync["failed"],
        "invoices_verified": invoice_reconcile["verified"],
        "invoices_mismatch": invoice_reconcile["mismatch"],
        "credit_notes_verified": cn_reconcile["verified"],
        "credit_notes_mismatch": cn_reconcile["mismatch"],
        "errors": (
            invoice_sync["errors"]
            + cogs_repost["errors"]
            + cn_sync["errors"]
            + po_sync["errors"]
            + invoice_reconcile["errors"]
            + cn_reconcile["errors"]
        ),
    }
    logger.info(
        "Xero sync complete for org %s: %s",
        org_id,
        {k: v for k, v in summary.items() if k != "errors"},
    )
    return summary
