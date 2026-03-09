"""Material withdrawal (POS) routes."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request

from catalog.application.queries import list_products
from finance.application.invoice_service import (
    create_invoice_from_withdrawals,
    mark_paid_for_withdrawal,
)
from finance.application.ledger_service import record_payment as _record_payment
from identity.application.org_service import get_org_settings
from identity.application.user_service import get_user_by_id
from inventory.application.inventory_service import process_withdrawal_stock_changes
from kernel.types import CurrentUser
from operations.application.withdrawal_service import create_withdrawal as _do_create_withdrawal
from operations.domain.withdrawal import MaterialWithdrawal, MaterialWithdrawalCreate
from operations.infrastructure.withdrawal_repo import withdrawal_repo
from kernel import events
from shared.api.deps import AdminDep, CurrentUserDep, ManagerDep
from shared.infrastructure import event_hub
from shared.infrastructure.middleware.audit import audit_log


async def do_create_withdrawal(data, contractor, current_user: CurrentUser):
    settings = await get_org_settings(current_user.organization_id)
    return await _do_create_withdrawal(
        data, contractor, current_user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
        create_invoice=create_invoice_from_withdrawals,
        tax_rate=settings.default_tax_rate,
    )

router = APIRouter(prefix="/withdrawals", tags=["withdrawals"])


@router.post("", response_model=MaterialWithdrawal)
async def create_withdrawal(data: MaterialWithdrawalCreate, request: Request, current_user: CurrentUserDep):
    """Create a material withdrawal - Contractors withdraw materials charged to their account"""
    contractor = current_user.model_dump()
    result = await do_create_withdrawal(data, contractor, current_user)
    await audit_log(
        user_id=current_user.id, action="withdrawal.create",
        resource_type="withdrawal", resource_id=result.get("id"),
        details={"total": result.get("total"), "job_id": data.job_id},
        request=request, org_id=current_user.organization_id,
    )
    await event_hub.emit(events.WITHDRAWAL_CREATED, org_id=current_user.organization_id, id=result.get("id"))
    await event_hub.emit(events.INVENTORY_UPDATED, org_id=current_user.organization_id)
    return result


@router.post("/for-contractor")
async def create_withdrawal_for_contractor(
    contractor_id: str,
    data: MaterialWithdrawalCreate,
    request: Request,
    current_user: ManagerDep,
):
    """Warehouse manager creates withdrawal on behalf of a contractor"""
    org_id = current_user.organization_id
    contractor = await get_user_by_id(contractor_id)
    if not contractor or contractor.get("role") != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")
    if contractor.get("organization_id") and contractor.get("organization_id") != org_id:
        raise HTTPException(status_code=403, detail="Contractor belongs to different organization")
    result = await do_create_withdrawal(data, contractor, current_user)
    await audit_log(
        user_id=current_user.id, action="withdrawal.create_for_contractor",
        resource_type="withdrawal", resource_id=result.get("id"),
        details={"contractor_id": contractor_id, "total": result.get("total")},
        request=request, org_id=org_id,
    )
    await event_hub.emit(events.WITHDRAWAL_CREATED, org_id=org_id, id=result.get("id"))
    await event_hub.emit(events.INVENTORY_UPDATED, org_id=org_id)
    return result


@router.get("")
async def get_withdrawals(
    current_user: CurrentUserDep,
    contractor_id: str | None = None,
    payment_status: str | None = None,
    billing_entity: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    org_id = current_user.organization_id
    cid = current_user.id if current_user.role == "contractor" else contractor_id
    return await withdrawal_repo.list_withdrawals(
        contractor_id=cid,
        payment_status=payment_status,
        billing_entity=billing_entity,
        start_date=start_date,
        end_date=end_date,
        limit=1000,
        organization_id=org_id,
    )


@router.get("/{withdrawal_id}")
async def get_withdrawal(withdrawal_id: str, current_user: CurrentUserDep):
    org_id = current_user.organization_id
    withdrawal = await withdrawal_repo.get_by_id(withdrawal_id, org_id)
    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")

    if current_user.role == "contractor" and withdrawal.get("contractor_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return withdrawal


@router.put("/{withdrawal_id}/mark-paid")
async def mark_withdrawal_paid(withdrawal_id: str, request: Request, current_user: AdminDep):
    org_id = current_user.organization_id
    withdrawal = await withdrawal_repo.get_by_id(withdrawal_id, org_id)
    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    paid_at = datetime.now(UTC).isoformat()
    result = await withdrawal_repo.mark_paid(withdrawal_id, paid_at)
    await mark_paid_for_withdrawal(withdrawal_id)
    await _record_payment(
        withdrawal_id=withdrawal_id,
        amount=withdrawal.get("total", 0),
        billing_entity=withdrawal.get("billing_entity", ""),
        contractor_id=withdrawal.get("contractor_id", ""),
        organization_id=org_id,
        performed_by_user_id=current_user.id,
    )
    await audit_log(
        user_id=current_user.id, action="payment.mark_paid",
        resource_type="withdrawal", resource_id=withdrawal_id,
        details={"total": withdrawal.get("total")},
        request=request, org_id=org_id,
    )
    await event_hub.emit(events.WITHDRAWAL_UPDATED, org_id=org_id, id=withdrawal_id)
    return result


@router.put("/bulk-mark-paid")
async def bulk_mark_paid(request: Request, withdrawal_ids: Annotated[list[str], Body(...)], current_user: AdminDep):
    if len(withdrawal_ids) > 200:
        raise HTTPException(status_code=400, detail="Cannot mark more than 200 withdrawals at once")
    org_id = current_user.organization_id
    paid_at = datetime.now(UTC).isoformat()
    try:
        updated = await withdrawal_repo.bulk_mark_paid(withdrawal_ids, paid_at, organization_id=org_id)
        for wid in withdrawal_ids:
            await mark_paid_for_withdrawal(wid)
            w = await withdrawal_repo.get_by_id(wid, org_id)
            if w:
                await _record_payment(
                    withdrawal_id=wid,
                    amount=w.get("total", 0),
                    billing_entity=w.get("billing_entity", ""),
                    contractor_id=w.get("contractor_id", ""),
                    organization_id=org_id,
                    performed_by_user_id=current_user.id,
                )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await audit_log(
        user_id=current_user.id, action="payment.bulk_mark_paid",
        resource_type="withdrawal", resource_id=None,
        details={"withdrawal_ids": withdrawal_ids, "count": len(withdrawal_ids)},
        request=request, org_id=org_id,
    )
    await event_hub.emit(events.WITHDRAWAL_UPDATED, org_id=org_id, ids=withdrawal_ids)
    return {"updated": updated}
