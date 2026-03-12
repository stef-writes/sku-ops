"""Payment routes — record and list payments."""

from fastapi import APIRouter, HTTPException

from finance.application import queries as finance_queries
from finance.application.payment_service import create_payment_for_withdrawals
from finance.domain.payment import PaymentCreate
from shared.api.deps import AdminDep
from shared.infrastructure import event_hub
from shared.kernel import events

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("")
async def create_payment(
    data: PaymentCreate,
    current_user: AdminDep,
):
    """Record a payment against withdrawals and/or an invoice."""
    try:
        payment = await create_payment_for_withdrawals(
            data=data,
            recorded_by_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await event_hub.emit(
        events.WITHDRAWAL_UPDATED, org_id=current_user.organization_id, ids=data.withdrawal_ids
    )
    return payment.model_dump()


@router.get("")
async def list_payments(
    current_user: AdminDep,
    invoice_id: str | None = None,
    billing_entity_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    return await finance_queries.list_payments(
        invoice_id=invoice_id,
        billing_entity_id=billing_entity_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.get("/{payment_id}")
async def get_payment(payment_id: str, current_user: AdminDep):
    p = await finance_queries.get_payment_by_id(payment_id)
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    return p
