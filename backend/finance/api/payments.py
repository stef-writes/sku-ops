"""Payment routes — record and list payments."""
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from finance.application.invoice_service import mark_paid_for_withdrawal
from finance.application.ledger_service import record_payment as _record_ledger_payment
from finance.domain.payment import Payment, PaymentCreate
from finance.infrastructure.payment_repo import payment_repo
from operations.application.queries import get_withdrawal_by_id, mark_withdrawal_paid
from kernel import events
from shared.api.deps import AdminDep, ManagerDep
from shared.infrastructure import event_hub

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("")
async def create_payment(
    data: PaymentCreate,
    current_user: AdminDep,
):
    """Record a payment against withdrawals and/or an invoice."""
    org_id = current_user.organization_id
    now = datetime.now(UTC).isoformat()

    if not data.withdrawal_ids and not data.invoice_id:
        raise HTTPException(status_code=400, detail="Provide withdrawal_ids or invoice_id")

    total_amount = 0.0
    billing_entity = ""
    billing_entity_id = None
    contractor_id = ""

    for wid in data.withdrawal_ids:
        w = await get_withdrawal_by_id(wid, org_id)
        if not w:
            raise HTTPException(status_code=404, detail=f"Withdrawal {wid} not found")
        total_amount += w.get("total", 0)
        billing_entity = billing_entity or w.get("billing_entity", "")
        billing_entity_id = billing_entity_id or w.get("billing_entity_id")
        contractor_id = contractor_id or w.get("contractor_id", "")

    amount = data.amount if data.amount is not None else total_amount

    payment = Payment(
        invoice_id=data.invoice_id,
        billing_entity_id=billing_entity_id,
        amount=amount,
        method=data.method,
        reference=data.reference,
        payment_date=data.payment_date or now,
        notes=data.notes,
        recorded_by_id=current_user.id,
        organization_id=org_id,
    )

    await payment_repo.insert(payment, withdrawal_ids=data.withdrawal_ids)

    paid_at = data.payment_date or now
    for wid in data.withdrawal_ids:
        await mark_withdrawal_paid(wid, paid_at)
        await mark_paid_for_withdrawal(wid)
        w = await get_withdrawal_by_id(wid, org_id)
        if w:
            await _record_ledger_payment(
                withdrawal_id=wid,
                amount=w.get("total", 0),
                billing_entity=w.get("billing_entity", ""),
                contractor_id=w.get("contractor_id", ""),
                organization_id=org_id,
                performed_by_user_id=current_user.id,
            )

    await event_hub.emit(events.WITHDRAWAL_UPDATED, org_id=org_id, ids=data.withdrawal_ids)
    return payment.model_dump()


@router.get("")
async def list_payments(
    current_user: ManagerDep,
    invoice_id: str | None = None,
    billing_entity_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    return await payment_repo.list_payments(
        organization_id=current_user.organization_id,
        invoice_id=invoice_id, billing_entity_id=billing_entity_id,
        start_date=start_date, end_date=end_date,
        limit=limit, offset=offset,
    )


@router.get("/{payment_id}")
async def get_payment(payment_id: str, current_user: ManagerDep):
    p = await payment_repo.get_by_id(payment_id, current_user.organization_id)
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    return p
