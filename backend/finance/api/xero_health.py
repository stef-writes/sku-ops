"""Xero sync health — surfaces unsynced documents, failures, and mismatches."""
import asyncio
import logging

from fastapi import APIRouter

from finance.application.po_sync_service import list_failed_po_bills, list_unsynced_po_bills
from finance.infrastructure.credit_note_repo import credit_note_repo
from finance.infrastructure.invoice_repo import invoice_repo
from shared.api.deps import AdminDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/xero", tags=["xero"])

_sync_tasks: dict[str, asyncio.Task] = {}
_LOCK_PREFIX = "sku_ops:xero_sync:"
_LOCK_TTL = 3600


def _use_redis() -> bool:
    from shared.infrastructure.redis import is_redis_available
    return is_redis_available()


@router.get("/health")
async def get_xero_health(
    current_user: AdminDep,
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
async def trigger_sync(current_user: AdminDep):
    """Manually trigger a full Xero sync + reconciliation for the org (background)."""
    from finance.application.xero_sync_job import run_sync

    org_id = current_user.organization_id

    if _use_redis():
        from shared.infrastructure.redis import get_redis
        r = get_redis()
        lock_key = f"{_LOCK_PREFIX}{org_id}"
        acquired = await r.set(lock_key, "1", nx=True, ex=_LOCK_TTL)
        if not acquired:
            return {"success": True, "status": "in_progress"}

        async def _run():
            try:
                return await run_sync(org_id)
            except Exception:
                logger.exception("Xero sync failed for org %s", org_id)
            finally:
                await r.delete(lock_key)

        asyncio.create_task(_run())
        return {"success": True, "status": "started"}

    existing = _sync_tasks.get(org_id)
    if existing and not existing.done():
        return {"success": True, "status": "in_progress"}

    async def _run():
        try:
            return await run_sync(org_id)
        except Exception:
            logger.exception("Xero sync failed for org %s", org_id)
        finally:
            _sync_tasks.pop(org_id, None)

    _sync_tasks[org_id] = asyncio.create_task(_run())
    return {"success": True, "status": "started"}


@router.get("/sync-status")
async def get_sync_status(current_user: AdminDep):
    """Check if a background Xero sync is running."""
    org_id = current_user.organization_id

    if _use_redis():
        from shared.infrastructure.redis import get_redis
        exists = await get_redis().exists(f"{_LOCK_PREFIX}{org_id}")
        return {"status": "in_progress" if exists else "idle"}

    task = _sync_tasks.get(org_id)
    if task and not task.done():
        return {"status": "in_progress"}
    return {"status": "idle"}
