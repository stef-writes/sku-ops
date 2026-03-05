"""Credit note application service — safe for cross-context import."""
from typing import Optional

from finance.infrastructure.credit_note_repo import credit_note_repo as _repo


async def insert_credit_note(
    return_id: str,
    invoice_id: Optional[str],
    items: list,
    subtotal: float = 0,
    tax: float = 0,
    total: float = 0,
    organization_id: Optional[str] = None,
    conn=None,
) -> dict:
    return await _repo.insert_credit_note(
        return_id=return_id,
        invoice_id=invoice_id,
        items=items,
        subtotal=subtotal,
        tax=tax,
        total=total,
        organization_id=organization_id,
        conn=conn,
    )


async def apply_credit_note(
    credit_note_id: str,
    organization_id: Optional[str] = None,
    performed_by_user_id: Optional[str] = None,
) -> dict:
    """Apply a credit note to its linked invoice and write AR ledger entry."""
    cn = await _repo.apply_credit_note(credit_note_id, organization_id)

    from finance.application.ledger_service import record_credit_note_application
    await record_credit_note_application(
        credit_note_id=credit_note_id,
        amount=float(cn.get("total", 0)),
        billing_entity=cn.get("billing_entity", ""),
        contractor_id="",
        organization_id=organization_id or "default",
        performed_by_user_id=performed_by_user_id,
    )
    return cn


async def list_credit_notes(
    invoice_id: Optional[str] = None,
    billing_entity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> list:
    return await _repo.list_credit_notes(
        invoice_id=invoice_id,
        billing_entity=billing_entity,
        start_date=start_date,
        end_date=end_date,
        organization_id=organization_id,
    )


async def get_credit_note_by_id(credit_note_id: str, organization_id: Optional[str] = None) -> Optional[dict]:
    return await _repo.get_by_id(credit_note_id, organization_id=organization_id)
