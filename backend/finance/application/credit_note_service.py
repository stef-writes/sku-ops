"""Credit note application service — orchestrates cross-context interactions."""

from datetime import UTC, datetime

from finance.application.ledger_service import record_credit_note_application
from finance.domain.credit_note import CreditNote
from finance.infrastructure.credit_note_repo import credit_note_repo as _repo
from operations.application.queries import (
    link_credit_note_to_return,
    mark_withdrawals_paid_by_invoice,
)


async def insert_credit_note(
    return_id: str,
    invoice_id: str | None,
    items: list,
    subtotal: float = 0,
    tax: float = 0,
    total: float = 0,
) -> CreditNote:
    """Create a credit note and link it to the return (operations-owned mutation)."""
    cn = await _repo.insert_credit_note(
        return_id=return_id,
        invoice_id=invoice_id,
        items=items,
        subtotal=subtotal,
        tax=tax,
        total=total,
    )
    await link_credit_note_to_return(return_id, cn.id)
    return cn


async def apply_credit_note(
    credit_note_id: str,
    performed_by_user_id: str | None = None,
) -> CreditNote:
    """Apply a credit note to its linked invoice and write AR ledger entry.

    If the invoice balance reaches zero, marks linked withdrawals as paid
    via the operations facade.
    """
    result = await _repo.apply_credit_note(credit_note_id)

    if result.auto_paid and result.invoice_id:
        now = datetime.now(UTC).isoformat()
        await mark_withdrawals_paid_by_invoice(result.invoice_id, now)

    await record_credit_note_application(
        credit_note_id=credit_note_id,
        amount=float(result.credit_note.total),
        billing_entity=result.credit_note.billing_entity,
        contractor_id="",
        performed_by_user_id=performed_by_user_id,
    )

    return result.credit_note


async def list_credit_notes(
    invoice_id: str | None = None,
    billing_entity: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[CreditNote]:
    return await _repo.list_credit_notes(
        invoice_id=invoice_id,
        billing_entity=billing_entity,
        start_date=start_date,
        end_date=end_date,
    )


async def get_credit_note_by_id(
    credit_note_id: str,
) -> CreditNote | None:
    return await _repo.get_by_id(credit_note_id)
