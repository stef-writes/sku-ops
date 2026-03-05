"""Invoice CRUD and Xero sync routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from identity.application.auth_service import require_role
from kernel.types import CurrentUser
from finance.domain.invoice import InvoiceCreate, InvoiceUpdate, InvoiceSyncXeroBulk
from finance.infrastructure.invoice_repo import invoice_repo
from finance.application.invoice_service import sync_invoice
from shared.infrastructure.middleware.audit import audit_log

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("/sync-xero-bulk")
async def sync_invoices_to_xero_bulk(
    data: InvoiceSyncXeroBulk,
    request: Request,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Bulk sync selected invoices to Xero."""
    org_id = current_user.organization_id
    results = [await sync_invoice(inv_id, org_id) for inv_id in data.invoice_ids]
    successes = [r for r in results if r.get("success")]
    errors = [r for r in results if not r.get("success")]
    await audit_log(
        user_id=current_user.id, action="invoice.sync_xero_bulk",
        resource_type="invoice", resource_id=None,
        details={"count": len(data.invoice_ids), "synced": len(successes), "failed": len(errors)},
        request=request, org_id=org_id,
    )
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
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """List invoices with optional filters."""
    org_id = current_user.organization_id
    return await invoice_repo.list_invoices(
        status=status,
        billing_entity=billing_entity,
        start_date=start_date,
        end_date=end_date,
        limit=1000,
        organization_id=org_id,
    )


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: str, current_user: CurrentUser = Depends(require_role("admin"))):
    """Get invoice with line items and linked withdrawals."""
    org_id = current_user.organization_id
    inv = await invoice_repo.get_by_id(invoice_id, org_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.post("")
async def create_invoice(
    data: InvoiceCreate,
    request: Request,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Create invoice from selected unpaid withdrawals. All must share same billing_entity."""
    org_id = current_user.organization_id
    try:
        inv = await invoice_repo.create_from_withdrawals(data.withdrawal_ids, organization_id=org_id)
        await audit_log(
            user_id=current_user.id, action="invoice.create",
            resource_type="invoice", resource_id=inv.get("id"),
            details={"invoice_number": inv.get("invoice_number"), "total": inv.get("total"),
                      "withdrawal_count": len(data.withdrawal_ids)},
            request=request, org_id=org_id,
        )
        return inv
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{invoice_id}")
async def update_invoice(
    invoice_id: str,
    data: InvoiceUpdate,
    request: Request,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Update invoice fields and/or line items."""
    org_id = current_user.organization_id
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
        tax_rate=data.tax_rate,
        invoice_date=data.invoice_date,
        due_date=data.due_date,
        payment_terms=data.payment_terms,
        billing_address=data.billing_address,
        po_reference=data.po_reference,
        line_items=line_items_data if data.line_items is not None else None,
    )
    changes = {k: v for k, v in data.model_dump(exclude_none=True).items() if k != "line_items"}
    if data.line_items is not None:
        changes["line_items_updated"] = True
    await audit_log(
        user_id=current_user.id, action="invoice.update",
        resource_type="invoice", resource_id=invoice_id,
        details=changes, request=request, org_id=org_id,
    )
    return updated


@router.delete("/{invoice_id}")
async def delete_invoice(invoice_id: str, request: Request, current_user: CurrentUser = Depends(require_role("admin"))):
    """Delete draft invoice and unlink withdrawals."""
    org_id = current_user.organization_id
    inv = await invoice_repo.get_by_id(invoice_id, org_id)
    try:
        ok = await invoice_repo.delete_draft(invoice_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Invoice not found")
        await audit_log(
            user_id=current_user.id, action="invoice.delete",
            resource_type="invoice", resource_id=invoice_id,
            details={"invoice_number": inv.get("invoice_number") if inv else None,
                      "total": inv.get("total") if inv else None},
            request=request, org_id=org_id,
        )
        return {"deleted": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{invoice_id}/approve")
async def approve_invoice(
    invoice_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Approve a draft invoice, locking it for Xero sync."""
    org_id = current_user.organization_id
    inv = await invoice_repo.get_by_id(invoice_id, org_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.get("status") != "draft":
        raise HTTPException(status_code=400, detail=f"Cannot approve invoice in '{inv.get('status')}' status")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    updated = await invoice_repo.update(
        invoice_id,
        status="approved",
    )

    from shared.infrastructure.database import get_connection
    conn = get_connection()
    await conn.execute(
        "UPDATE invoices SET approved_by_id = ?, approved_at = ? WHERE id = ?",
        (current_user.id, now, invoice_id),
    )
    await conn.commit()

    await audit_log(
        user_id=current_user.id, action="invoice.approve",
        resource_type="invoice", resource_id=invoice_id,
        details={"invoice_number": inv.get("invoice_number")},
        request=request, org_id=org_id,
    )
    return await invoice_repo.get_by_id(invoice_id, org_id)


@router.post("/{invoice_id}/sync-xero")
async def sync_invoice_to_xero(invoice_id: str, request: Request, current_user: CurrentUser = Depends(require_role("admin"))):
    """Sync a single invoice to Xero. Requires approved or sent status."""
    org_id = current_user.organization_id
    inv = await invoice_repo.get_by_id(invoice_id, org_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.get("status") not in ("approved", "sent", "paid"):
        raise HTTPException(status_code=400, detail="Invoice must be approved before syncing to Xero")

    result = await sync_invoice(invoice_id, org_id)
    if result.get("error") and not result.get("success"):
        status_code = 404 if result["error"] == "Invoice not found" else 502
        raise HTTPException(status_code=status_code, detail=result["error"])
    await audit_log(
        user_id=current_user.id, action="invoice.sync_xero",
        resource_type="invoice", resource_id=invoice_id,
        details={"success": result.get("success", False)},
        request=request, org_id=org_id,
    )
    return result
