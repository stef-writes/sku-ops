"""Payment service: orchestrates recording payments against withdrawals."""

from __future__ import annotations

from datetime import UTC, datetime

from finance.application.invoice_service import mark_paid_for_withdrawal
from finance.application.ledger_service import record_payment as _record_ledger_payment
from finance.domain.payment import Payment, PaymentCreate
from finance.infrastructure.payment_repo import payment_repo
from operations.application.queries import get_withdrawal_by_id, mark_withdrawal_paid
from shared.infrastructure.database import get_org_id


async def create_payment_for_withdrawals(
    data: PaymentCreate,
    recorded_by_id: str,
) -> Payment:
    """Aggregate withdrawal totals, create payment, mark each withdrawal paid + ledger entry.

    Returns the created Payment domain object.
    """
    now = datetime.now(UTC).isoformat()

    if not data.withdrawal_ids and not data.invoice_id:
        raise ValueError("Provide withdrawal_ids or invoice_id")

    total_amount = 0.0
    billing_entity = ""
    billing_entity_id = None
    contractor_id = ""

    for wid in data.withdrawal_ids:
        w = await get_withdrawal_by_id(wid)
        if not w:
            raise ValueError(f"Withdrawal {wid} not found")
        total_amount += w.total
        billing_entity = billing_entity or w.billing_entity
        billing_entity_id = billing_entity_id or w.billing_entity_id
        contractor_id = contractor_id or w.contractor_id

    amount = data.amount if data.amount is not None else total_amount

    payment = Payment(
        invoice_id=data.invoice_id,
        billing_entity_id=billing_entity_id,
        amount=amount,
        method=data.method,
        reference=data.reference,
        payment_date=data.payment_date or now,
        notes=data.notes,
        recorded_by_id=recorded_by_id,
        organization_id=get_org_id(),
    )

    await payment_repo.insert(payment, withdrawal_ids=data.withdrawal_ids)

    paid_at = data.payment_date or now
    for wid in data.withdrawal_ids:
        await mark_withdrawal_paid(wid, paid_at)
        await mark_paid_for_withdrawal(wid)
        w = await get_withdrawal_by_id(wid)
        if w:
            await _record_ledger_payment(
                withdrawal_id=wid,
                amount=w.total,
                billing_entity=w.billing_entity,
                contractor_id=w.contractor_id,
                performed_by_user_id=recorded_by_id,
            )

    return payment
