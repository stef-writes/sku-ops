"""Invoice CRUD and Xero sync routes."""

import logging

from fastapi import APIRouter, HTTPException, Request

from finance.application.invoice_service import (
    approve_invoice,
    create_invoice_from_withdrawals,
    delete_draft_invoice,
    get_invoice,
    list_invoices,
    update_invoice,
)
from finance.application.invoice_sync import sync_invoice
from finance.domain.invoice import InvoiceCreate, InvoiceSyncXeroBulk, InvoiceUpdate
from shared.api.deps import AdminDep
from shared.infrastructure.middleware.audit import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("/sync-xero-bulk")
async def sync_invoices_to_xero_bulk(
    data: InvoiceSyncXeroBulk,
    request: Request,
    current_user: AdminDep,
):
    """Bulk sync selected invoices to Xero."""
    results = [await sync_invoice(inv_id) for inv_id in data.invoice_ids]
    successes = [r for r in results if r.get("success")]
    errors = [r for r in results if not r.get("success")]
    await audit_log(
        user_id=current_user.id,
        action="invoice.sync_xero_bulk",
        resource_type="invoice",
        resource_id=None,
        details={"count": len(data.invoice_ids), "synced": len(successes), "failed": len(errors)},
        request=request,
        org_id=current_user.organization_id,
    )
    return {
        "synced": len(successes),
        "errors": errors,
        "results": results,
        "message": f"Bulk Xero sync: {len(successes)} synced, {len(errors)} failed",
    }


@router.get("")
async def get_invoices(
    current_user: AdminDep,
    status: str | None = None,
    billing_entity: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """List invoices with optional filters."""
    return await list_invoices(
        status=status,
        billing_entity=billing_entity,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/{invoice_id}")
async def get_invoice_by_id(invoice_id: str, current_user: AdminDep):
    """Get invoice with line items and linked withdrawals."""
    inv = await get_invoice(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.post("")
async def create_invoice(
    data: InvoiceCreate,
    request: Request,
    current_user: AdminDep,
):
    """Create invoice from selected unpaid withdrawals."""
    try:
        inv = await create_invoice_from_withdrawals(data.withdrawal_ids)
        await audit_log(
            user_id=current_user.id,
            action="invoice.create",
            resource_type="invoice",
            resource_id=inv.id,
            details={
                "invoice_number": inv.invoice_number,
                "total": inv.total,
                "withdrawal_count": len(data.withdrawal_ids),
            },
            request=request,
            org_id=current_user.organization_id,
        )
        return inv
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/{invoice_id}")
async def update_invoice_route(
    invoice_id: str,
    data: InvoiceUpdate,
    request: Request,
    current_user: AdminDep,
):
    """Update invoice fields and/or line items."""
    inv = await get_invoice(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    try:
        updated = await update_invoice(
            invoice_id,
            billing_entity=data.billing_entity,
            contact_name=data.contact_name,
            contact_email=data.contact_email,
            status=data.status,
            notes=data.notes,
            tax=data.tax,
            tax_rate=data.tax_rate,
            invoice_date=data.invoice_date,
            due_date=data.due_date,
            payment_terms=data.payment_terms,
            billing_address=data.billing_address,
            po_reference=data.po_reference,
            line_items=data.line_items,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    changes = {k: v for k, v in data.model_dump(exclude_none=True).items() if k != "line_items"}
    if data.line_items is not None:
        changes["line_items_updated"] = True
    await audit_log(
        user_id=current_user.id,
        action="invoice.update",
        resource_type="invoice",
        resource_id=invoice_id,
        details=changes,
        request=request,
        org_id=current_user.organization_id,
    )
    return updated


@router.delete("/{invoice_id}")
async def delete_invoice(invoice_id: str, request: Request, current_user: AdminDep):
    """Delete draft invoice and unlink withdrawals."""
    inv = await get_invoice(invoice_id)
    try:
        ok = await delete_draft_invoice(invoice_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Invoice not found")
        await audit_log(
            user_id=current_user.id,
            action="invoice.delete",
            resource_type="invoice",
            resource_id=invoice_id,
            details={
                "invoice_number": inv.invoice_number if inv else None,
                "total": inv.total if inv else None,
            },
            request=request,
            org_id=current_user.organization_id,
        )
        return {"deleted": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{invoice_id}/approve")
async def approve_invoice_route(
    invoice_id: str,
    request: Request,
    current_user: AdminDep,
):
    """Approve a draft invoice, locking it for Xero sync."""
    inv = await get_invoice(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    try:
        result = await approve_invoice(invoice_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await audit_log(
        user_id=current_user.id,
        action="invoice.approve",
        resource_type="invoice",
        resource_id=invoice_id,
        details={"invoice_number": inv.invoice_number},
        request=request,
        org_id=current_user.organization_id,
    )
    return result


@router.post("/{invoice_id}/sync-xero")
async def sync_invoice_to_xero(invoice_id: str, request: Request, current_user: AdminDep):
    """Sync a single invoice to Xero. Requires approved or sent status."""
    inv = await get_invoice(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status not in ("approved", "sent", "paid"):
        raise HTTPException(
            status_code=400, detail="Invoice must be approved before syncing to Xero"
        )

    result = await sync_invoice(invoice_id)
    if result.get("error") and not result.get("success"):
        status_code = 404 if result["error"] == "Invoice not found" else 502
        raise HTTPException(status_code=status_code, detail=result["error"])
    await audit_log(
        user_id=current_user.id,
        action="invoice.sync_xero",
        resource_type="invoice",
        resource_id=invoice_id,
        details={"success": result.get("success", False)},
        request=request,
        org_id=current_user.organization_id,
    )
    return result
