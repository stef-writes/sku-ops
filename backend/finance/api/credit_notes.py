"""Credit note routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from finance.application.credit_note_service import apply_credit_note
from finance.infrastructure.credit_note_repo import credit_note_repo
from identity.application.auth_service import require_role
from kernel.types import CurrentUser
from shared.infrastructure.middleware.audit import audit_log

router = APIRouter(prefix="/credit-notes", tags=["credit-notes"])


@router.get("")
async def list_credit_notes(
    invoice_id: str | None = None,
    billing_entity: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    org_id = current_user.organization_id
    return await credit_note_repo.list_credit_notes(
        invoice_id=invoice_id,
        billing_entity=billing_entity,
        status=status,
        start_date=start_date,
        end_date=end_date,
        organization_id=org_id,
    )


@router.get("/{credit_note_id}")
async def get_credit_note(
    credit_note_id: str,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    org_id = current_user.organization_id
    cn = await credit_note_repo.get_by_id(credit_note_id, org_id)
    if not cn:
        raise HTTPException(status_code=404, detail="Credit note not found")
    return cn


@router.post("/{credit_note_id}/apply")
async def apply_credit_note_to_invoice(
    credit_note_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Apply a credit note against its linked invoice, reducing the balance due."""
    org_id = current_user.organization_id
    try:
        cn = await apply_credit_note(
            credit_note_id=credit_note_id,
            organization_id=org_id,
            performed_by_user_id=current_user.id,
        )
        await audit_log(
            user_id=current_user.id, action="credit_note.apply",
            resource_type="credit_note", resource_id=credit_note_id,
            details={"invoice_id": cn.get("invoice_id"), "total": cn.get("total")},
            request=request, org_id=org_id,
        )
        return cn
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
