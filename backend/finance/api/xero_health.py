"""Xero sync health — surfaces unsynced documents, failures, and mismatches."""
import logging

from fastapi import APIRouter, Depends

from finance.application.po_sync_service import list_failed_po_bills, list_unsynced_po_bills
from finance.infrastructure.credit_note_repo import credit_note_repo
from finance.infrastructure.invoice_repo import invoice_repo
from identity.application.auth_service import require_role
from kernel.types import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/xero", tags=["xero"])


@router.get("/health")
async def get_xero_health(
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Return a snapshot of all Xero sync exceptions for the sync health dashboard."""
    org_id = current_user.organization_id
    unsynced_invoices, unsynced_credits, unsynced_pos, mismatch_invoices, mismatch_credits, failed_invoices, failed_credits, failed_pos = (
        await invoice_repo.list_unsynced_invoices(org_id),
        await credit_note_repo.list_unsynced_credit_notes(org_id),
        await list_unsynced_po_bills(org_id),
        await invoice_repo.list_mismatch_invoices(org_id),
        await credit_note_repo.list_mismatch_credit_notes(org_id),
        await invoice_repo.list_failed_invoices(org_id),
        await credit_note_repo.list_failed_credit_notes(org_id),
        await list_failed_po_bills(org_id),
    )
    return {
        "unsynced_invoices": unsynced_invoices,
        "unsynced_credits": unsynced_credits,
        "unsynced_po_bills": unsynced_pos,
        "mismatch_invoices": mismatch_invoices,
        "mismatch_credits": mismatch_credits,
        "failed_invoices": failed_invoices,
        "failed_credits": failed_credits,
        "failed_po_bills": failed_pos,
        "totals": {
            "unsynced": len(unsynced_invoices) + len(unsynced_credits) + len(unsynced_pos),
            "mismatch": len(mismatch_invoices) + len(mismatch_credits),
            "failed": len(failed_invoices) + len(failed_credits) + len(failed_pos),
        },
    }


@router.post("/sync")
async def trigger_sync(
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Manually trigger a full Xero sync + reconciliation for the org."""
    from finance.application.xero_sync_job import run_sync
    org_id = current_user.organization_id
    try:
        summary = await run_sync(org_id)
        return {"success": True, "summary": summary}
    except Exception as e:
        logger.error("Manual Xero sync failed for org %s: %s", org_id, e)
        return {"success": False, "error": str(e)}
