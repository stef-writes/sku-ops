"""Nightly Xero sync job.

Three passes in order:
  1. Outbound sync — push unsynced invoices, credit notes, and PO bills to Xero.
  2. Reconciliation — fetch synced documents back from Xero and verify totals + line counts.
  3. Exception summary — return counts of every problem category for the health dashboard.

Call run_sync() from a scheduler or manually via the /api/xero/sync endpoint.
"""

import logging

from finance.adapters.invoicing_factory import get_invoicing_gateway
from finance.application.invoice_sync import repost_cogs_for_invoice, sync_invoice
from finance.application.org_settings_service import get_org_settings
from finance.application.po_sync_service import sync_po_bill
from finance.application.sync_results import (
    ReconcilePassResult,
    SyncError,
    SyncPassResult,
    XeroSyncSummary,
)
from finance.domain.xero_settings import XeroSettings
from finance.infrastructure.credit_note_repo import credit_note_repo
from finance.infrastructure.invoice_repo import invoice_repo
from purchasing.application.queries import list_unsynced_po_bills
from shared.infrastructure.database import get_org_id

logger = logging.getLogger(__name__)

_TOTAL_TOLERANCE = 0.02  # allow 2 cent rounding drift before flagging mismatch


async def _sync_outbound_invoices() -> SyncPassResult:
    unsynced = await invoice_repo.list_unsynced_invoices()
    result = SyncPassResult()
    for inv in unsynced:
        inv_id = inv.id
        try:
            r = await sync_invoice(inv_id)
            if r.success:
                result.synced += 1
                logger.info("Invoice %s synced to Xero: %s", inv_id, r.xero_invoice_id)
            else:
                await invoice_repo.set_xero_sync_status(inv_id, "failed")
                result.failed += 1
                result.errors.append(
                    SyncError(type="invoice", id=inv_id, number=inv.invoice_number, error=r.error)
                )
                logger.warning("Invoice %s sync failed: %s", inv_id, r.error)
        except Exception as e:
            await invoice_repo.set_xero_sync_status(inv_id, "failed")
            result.failed += 1
            result.errors.append(SyncError(type="invoice", id=inv_id, error=str(e)))
            logger.exception("Invoice %s sync exception", inv_id)
    return result


async def _sync_outbound_credit_notes(gateway, settings) -> SyncPassResult:
    unsynced = await credit_note_repo.list_unsynced_credit_notes()
    result = SyncPassResult()
    for cn in unsynced:
        cn_id = cn.id
        try:
            full_cn = await credit_note_repo.get_by_id(cn_id)
            if not full_cn:
                continue
            r = await gateway.sync_credit_note(full_cn, settings)
            if r.success and r.external_id:
                await credit_note_repo.set_xero_credit_note_id(cn_id, r.external_id)
                result.synced += 1
                logger.info("Credit note %s synced to Xero: %s", cn_id, r.external_id)
            else:
                await credit_note_repo.set_credit_note_sync_status(cn_id, "failed")
                result.failed += 1
                result.errors.append(
                    SyncError(
                        type="credit_note", id=cn_id, number=cn.credit_note_number, error=r.error
                    )
                )
                logger.warning("Credit note %s sync failed: %s", cn_id, r.error)
        except Exception as e:
            await credit_note_repo.set_credit_note_sync_status(cn_id, "failed")
            result.failed += 1
            result.errors.append(SyncError(type="credit_note", id=cn_id, error=str(e)))
            logger.exception("Credit note %s sync exception", cn_id)
    return result


async def _sync_outbound_po_bills() -> SyncPassResult:
    unsynced = await list_unsynced_po_bills()
    result = SyncPassResult()
    for po in unsynced:
        po_id = po["id"]
        try:
            r = await sync_po_bill(po_id)
            if r.success and not r.skipped:
                result.synced += 1
                logger.info("PO %s synced to Xero as bill: %s", po_id, r.xero_bill_id)
            elif not r.skipped:
                result.failed += 1
                result.errors.append(
                    SyncError(type="po_bill", id=po_id, vendor=po.get("vendor_name"), error=r.error)
                )
        except Exception as e:
            result.failed += 1
            result.errors.append(SyncError(type="po_bill", id=po_id, error=str(e)))
            logger.exception("PO %s bill sync exception", po_id)
    return result


async def _repost_stale_cogs() -> SyncPassResult:
    """Pass 1b — re-post COGS journals for invoices whose line items changed after sync."""
    stale = await invoice_repo.list_stale_cogs_invoices()
    result = SyncPassResult()
    for inv in stale:
        inv_id = inv.id
        try:
            r = await repost_cogs_for_invoice(inv_id)
            if r.success:
                result.reposted += 1
                logger.info(
                    "COGS re-posted for invoice %s: new journal %s",
                    inv_id,
                    r.xero_journal_id,
                )
            else:
                result.failed += 1
                result.errors.append(
                    SyncError(
                        type="cogs_repost", id=inv_id, number=inv.invoice_number, error=r.error
                    )
                )
                logger.warning("COGS re-post failed for invoice %s: %s", inv_id, r.error)
        except Exception as e:
            result.failed += 1
            result.errors.append(SyncError(type="cogs_repost", id=inv_id, error=str(e)))
            logger.exception("COGS re-post exception for invoice %s", inv_id)
    return result


async def _reconcile_invoices(gateway, settings) -> ReconcilePassResult:
    to_reconcile = await invoice_repo.list_invoices_needing_reconciliation()
    result = ReconcilePassResult()
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
                result.verified += 1
            else:
                await invoice_repo.set_xero_sync_status(inv_id, "mismatch")
                result.mismatch += 1
                result.errors.append(
                    SyncError(type="invoice_mismatch", id=inv_id, number=inv.invoice_number)
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
            result.errors.append(SyncError(type="invoice_reconcile_error", id=inv_id, error=str(e)))
            logger.exception("Invoice %s reconcile exception", inv_id)
    return result


async def _reconcile_credit_notes(gateway, settings) -> ReconcilePassResult:
    to_reconcile = await credit_note_repo.list_credit_notes_needing_reconciliation()
    result = ReconcilePassResult()
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
                result.verified += 1
            else:
                await credit_note_repo.set_credit_note_sync_status(cn_id, "mismatch")
                result.mismatch += 1
                result.errors.append(
                    SyncError(type="credit_note_mismatch", id=cn_id, number=cn.credit_note_number)
                )
                logger.warning(
                    "Credit note %s mismatch: local=%.2f xero=%.2f",
                    cn_id,
                    cn.total,
                    xero_data.get("total", 0),
                )
        except Exception as e:
            result.errors.append(SyncError(type="cn_reconcile_error", id=cn_id, error=str(e)))
            logger.exception("Credit note %s reconcile exception", cn_id)
    return result


async def run_sync(reconcile: bool = True) -> XeroSyncSummary:
    """Run the full outbound sync + reconciliation for an org.

    Returns a typed summary suitable for logging or returning from an API endpoint.
    Safe to call repeatedly — idempotency is enforced per document via xero_invoice_id guards.
    """
    org_settings = await get_org_settings()
    xero_settings = XeroSettings.model_validate(org_settings.model_dump())
    gateway = get_invoicing_gateway(xero_settings)

    # Pass 1 — outbound sync
    invoice_sync = await _sync_outbound_invoices()
    cogs_repost = await _repost_stale_cogs()
    cn_sync = await _sync_outbound_credit_notes(gateway, xero_settings)
    po_sync = await _sync_outbound_po_bills()

    # Pass 2 — reconciliation
    invoice_reconcile = ReconcilePassResult()
    cn_reconcile = ReconcilePassResult()
    if reconcile:
        xero_settings = XeroSettings.model_validate((await get_org_settings()).model_dump())
        gateway = get_invoicing_gateway(xero_settings)
        invoice_reconcile = await _reconcile_invoices(gateway, xero_settings)
        cn_reconcile = await _reconcile_credit_notes(gateway, xero_settings)

    org_id = get_org_id()
    summary = XeroSyncSummary(
        org_id=org_id,
        invoices_synced=invoice_sync.synced,
        invoices_failed=invoice_sync.failed,
        cogs_reposted=cogs_repost.reposted,
        cogs_repost_failed=cogs_repost.failed,
        credit_notes_synced=cn_sync.synced,
        credit_notes_failed=cn_sync.failed,
        po_bills_synced=po_sync.synced,
        po_bills_failed=po_sync.failed,
        invoices_verified=invoice_reconcile.verified,
        invoices_mismatch=invoice_reconcile.mismatch,
        credit_notes_verified=cn_reconcile.verified,
        credit_notes_mismatch=cn_reconcile.mismatch,
        errors=(
            invoice_sync.errors
            + cogs_repost.errors
            + cn_sync.errors
            + po_sync.errors
            + invoice_reconcile.errors
            + cn_reconcile.errors
        ),
    )
    logger.info(
        "Xero sync complete for org %s: synced=%d failed=%d verified=%d mismatch=%d",
        org_id,
        summary.invoices_synced + summary.credit_notes_synced + summary.po_bills_synced,
        summary.invoices_failed + summary.credit_notes_failed + summary.po_bills_failed,
        summary.invoices_verified + summary.credit_notes_verified,
        summary.invoices_mismatch + summary.credit_notes_mismatch,
    )
    return summary
