"""Credit note routes."""

from fastapi import APIRouter, HTTPException, Request

from finance.application import queries as finance_queries
from finance.application.credit_note_service import apply_credit_note
from shared.api.deps import AdminDep
from shared.infrastructure.middleware.audit import audit_log

router = APIRouter(prefix="/credit-notes", tags=["credit-notes"])


@router.get("")
async def list_credit_notes(
    current_user: AdminDep,
    invoice_id: str | None = None,
    billing_entity: str | None = None,
    status: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    return await finance_queries.list_credit_notes(
        invoice_id=invoice_id,
        billing_entity=billing_entity,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/{credit_note_id}")
async def get_credit_note(
    credit_note_id: str,
    current_user: AdminDep,
):
    cn = await finance_queries.get_credit_note_by_id(credit_note_id)
    if not cn:
        raise HTTPException(status_code=404, detail="Credit note not found")
    return cn


@router.post("/{credit_note_id}/apply")
async def apply_credit_note_to_invoice(
    credit_note_id: str,
    request: Request,
    current_user: AdminDep,
):
    """Apply a credit note against its linked invoice, reducing the balance due."""
    try:
        cn = await apply_credit_note(
            credit_note_id=credit_note_id,
            performed_by_user_id=current_user.id,
        )
        await audit_log(
            user_id=current_user.id,
            action="credit_note.apply",
            resource_type="credit_note",
            resource_id=credit_note_id,
            details={"invoice_id": cn.invoice_id, "total": cn.total},
            request=request,
            org_id=current_user.organization_id,
        )
        return cn
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
