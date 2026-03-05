"""Payment routes — record and list payments."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from kernel.types import CurrentUser
from identity.application.auth_service import require_role, get_current_user
from finance.domain.payment import Payment, PaymentCreate
from finance.infrastructure.payment_repo import payment_repo
from operations.application.queries import get_withdrawal_by_id, mark_withdrawal_paid
from finance.application.ledger_service import record_payment as _record_ledger_payment
from finance.application.invoice_service import mark_paid_for_withdrawal
from shared.infrastructure.middleware.audit import audit_log

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("")
async def create_payment(
    data: PaymentCreate,
    current_user: CurrentUser = Depends(require_role("admin")),
):
    """Record a payment against withdrawals and/or an invoice."""
    org_id = current_user.organization_id
    now = datetime.now(timezone.utc).isoformat()

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

    return payment.model_dump()


@router.get("")
async def list_payments(
    invoice_id: Optional[str] = None,
    billing_entity_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await payment_repo.list_payments(
        organization_id=current_user.organization_id,
        invoice_id=invoice_id, billing_entity_id=billing_entity_id,
        start_date=start_date, end_date=end_date,
        limit=limit, offset=offset,
    )


@router.get("/{payment_id}")
async def get_payment(payment_id: str, current_user: CurrentUser = Depends(get_current_user)):
    p = await payment_repo.get_by_id(payment_id, current_user.organization_id)
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    return p
