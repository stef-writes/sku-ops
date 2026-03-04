"""Invoice CRUD and Xero sync routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from identity.application.auth_service import require_role
from models import InvoiceCreate, InvoiceUpdate, InvoiceSyncXeroBulk
from repositories import invoice_repo
from identity.infrastructure.org_settings_repo import get_org_settings
from adapters.xero_factory import get_xero_gateway

router = APIRouter(prefix="/invoices", tags=["invoices"])


async def _sync_one(inv_id: str, org_id: str) -> dict:
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


@router.post("/sync-xero-bulk")
async def sync_invoices_to_xero_bulk(
    data: InvoiceSyncXeroBulk,
    current_user: dict = Depends(require_role("admin")),
):
    """Bulk sync selected invoices to Xero."""
    org_id = current_user.get("organization_id") or "default"
    results = [await _sync_one(inv_id, org_id) for inv_id in data.invoice_ids]
    successes = [r for r in results if r.get("success")]
    errors = [r for r in results if not r.get("success")]
    return {
        "synced": len(successes),
        "errors": errors,
        "results": results,
        "message": f"Bulk Xero sync: {len(successes)} synced, {len(errors)} failed",
    }


@router.get("")
async def get_invoices(
    status: Optional[str] = None,
    billing_entity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(require_role("admin")),
):
    """List invoices with optional filters."""
    org_id = current_user.get("organization_id") or "default"
    return await invoice_repo.list_invoices(
        status=status,
        billing_entity=billing_entity,
        start_date=start_date,
        end_date=end_date,
        limit=1000,
        organization_id=org_id,
    )


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: str, current_user: dict = Depends(require_role("admin"))):
    """Get invoice with line items and linked withdrawals."""
    org_id = current_user.get("organization_id") or "default"
    inv = await invoice_repo.get_by_id(invoice_id, org_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.post("")
async def create_invoice(
    data: InvoiceCreate,
    current_user: dict = Depends(require_role("admin")),
):
    """Create invoice from selected unpaid withdrawals. All must share same billing_entity."""
    org_id = current_user.get("organization_id") or "default"
    try:
        inv = await invoice_repo.create_from_withdrawals(data.withdrawal_ids, organization_id=org_id)
        return inv
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{invoice_id}")
async def update_invoice(
    invoice_id: str,
    data: InvoiceUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    """Update invoice fields and/or line items."""
    org_id = current_user.get("organization_id") or "default"
    inv = await invoice_repo.get_by_id(invoice_id, org_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    line_items_data = [i.model_dump() if hasattr(i, "model_dump") else i for i in (data.line_items or [])]
    updated = await invoice_repo.update(
        invoice_id,
        billing_entity=data.billing_entity,
        contact_name=data.contact_name,
        contact_email=data.contact_email,
        status=data.status,
        notes=data.notes,
        tax=data.tax,
        line_items=line_items_data if data.line_items is not None else None,
    )
    return updated


@router.delete("/{invoice_id}")
async def delete_invoice(invoice_id: str, current_user: dict = Depends(require_role("admin"))):
    """Delete draft invoice and unlink withdrawals."""
    try:
        ok = await invoice_repo.delete_draft(invoice_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return {"deleted": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{invoice_id}/sync-xero")
async def sync_invoice_to_xero(invoice_id: str, current_user: dict = Depends(require_role("admin"))):
    """Sync a single invoice to Xero. Posts invoice + COGS journal."""
    org_id = current_user.get("organization_id") or "default"
    result = await _sync_one(invoice_id, org_id)
    if result.get("error") and not result.get("success"):
        status_code = 404 if result["error"] == "Invoice not found" else 502
        raise HTTPException(status_code=status_code, detail=result["error"])
    return result
