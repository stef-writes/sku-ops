"""Material withdrawal (POS) routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request

from identity.application.user_service import get_user_by_id
from operations.application.queries import get_withdrawal_by_id, list_withdrawals
from operations.application.withdrawal_service import (
    bulk_mark_withdrawals_paid,
    create_withdrawal_wired,
    mark_single_withdrawal_paid,
)
from operations.domain.withdrawal import MaterialWithdrawal, MaterialWithdrawalCreate
from shared.api.deps import AdminDep, CurrentUserDep
from shared.infrastructure import event_hub
from shared.infrastructure.middleware.audit import audit_log
from shared.kernel import events

router = APIRouter(prefix="/withdrawals", tags=["withdrawals"])


@router.post("", response_model=MaterialWithdrawal)
async def create_withdrawal(
    data: MaterialWithdrawalCreate, request: Request, current_user: CurrentUserDep
):
    """Create a material withdrawal - Contractors withdraw materials charged to their account"""
    contractor = current_user.model_dump()
    result = await create_withdrawal_wired(data, contractor, current_user)
    await audit_log(
        user_id=current_user.id,
        action="withdrawal.create",
        resource_type="withdrawal",
        resource_id=result.get("id"),
        details={"total": result.get("total"), "job_id": data.job_id},
        request=request,
        org_id=current_user.organization_id,
    )
    await event_hub.emit(
        events.WITHDRAWAL_CREATED, org_id=current_user.organization_id, id=result.get("id")
    )
    await event_hub.emit(events.INVENTORY_UPDATED, org_id=current_user.organization_id)
    return result


@router.post("/for-contractor")
async def create_withdrawal_for_contractor(
    contractor_id: str,
    data: MaterialWithdrawalCreate,
    request: Request,
    current_user: AdminDep,
):
    """Admin creates withdrawal on behalf of a contractor."""
    contractor = await get_user_by_id(contractor_id)
    if not contractor or contractor.role != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")
    if contractor.organization_id and contractor.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Contractor belongs to different organization")
    result = await create_withdrawal_wired(data, contractor.model_dump(), current_user)
    await audit_log(
        user_id=current_user.id,
        action="withdrawal.create_for_contractor",
        resource_type="withdrawal",
        resource_id=result.get("id"),
        details={"contractor_id": contractor_id, "total": result.get("total")},
        request=request,
        org_id=current_user.organization_id,
    )
    await event_hub.emit(
        events.WITHDRAWAL_CREATED,
        org_id=current_user.organization_id,
        id=result.get("id"),
    )
    await event_hub.emit(events.INVENTORY_UPDATED, org_id=current_user.organization_id)
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
    cid = current_user.id if current_user.role == "contractor" else contractor_id
    return await list_withdrawals(
        contractor_id=cid,
        payment_status=payment_status,
        billing_entity=billing_entity,
        start_date=start_date,
        end_date=end_date,
        limit=1000,
    )


@router.get("/{withdrawal_id}")
async def get_withdrawal(withdrawal_id: str, current_user: CurrentUserDep):
    withdrawal = await get_withdrawal_by_id(withdrawal_id)
    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")

    if current_user.role == "contractor" and withdrawal.contractor_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return withdrawal.model_dump()


@router.put("/{withdrawal_id}/mark-paid")
async def mark_withdrawal_paid(withdrawal_id: str, request: Request, current_user: AdminDep):
    try:
        result = await mark_single_withdrawal_paid(
            withdrawal_id=withdrawal_id,
            performed_by_user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await audit_log(
        user_id=current_user.id,
        action="payment.mark_paid",
        resource_type="withdrawal",
        resource_id=withdrawal_id,
        details={},
        request=request,
        org_id=current_user.organization_id,
    )
    await event_hub.emit(
        events.WITHDRAWAL_UPDATED, org_id=current_user.organization_id, id=withdrawal_id
    )
    return result.model_dump()


@router.put("/bulk-mark-paid")
async def bulk_mark_paid(
    request: Request, withdrawal_ids: Annotated[list[str], Body(...)], current_user: AdminDep
):
    try:
        updated = await bulk_mark_withdrawals_paid(
            withdrawal_ids=withdrawal_ids,
            performed_by_user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await audit_log(
        user_id=current_user.id,
        action="payment.bulk_mark_paid",
        resource_type="withdrawal",
        resource_id=None,
        details={"withdrawal_ids": withdrawal_ids, "count": len(withdrawal_ids)},
        request=request,
        org_id=current_user.organization_id,
    )
    await event_hub.emit(
        events.WITHDRAWAL_UPDATED, org_id=current_user.organization_id, ids=withdrawal_ids
    )
    return {"updated": updated}
