"""Material withdrawal (POS) routes."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from identity.application.auth_service import get_current_user, require_role
from operations.domain.withdrawal import MaterialWithdrawal, MaterialWithdrawalCreate
from finance.infrastructure.invoice_repo import invoice_repo
from identity.infrastructure.user_repo import user_repo
from operations.infrastructure.withdrawal_repo import withdrawal_repo
from operations.application.withdrawal_service import create_withdrawal as do_create_withdrawal

router = APIRouter(prefix="/withdrawals", tags=["withdrawals"])


@router.post("", response_model=MaterialWithdrawal)
async def create_withdrawal(data: MaterialWithdrawalCreate, current_user: dict = Depends(get_current_user)):
    """Create a material withdrawal - Contractors withdraw materials charged to their account"""
    return await do_create_withdrawal(data, current_user, current_user)


@router.post("/for-contractor")
async def create_withdrawal_for_contractor(
    contractor_id: str,
    data: MaterialWithdrawalCreate,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Warehouse manager creates withdrawal on behalf of a contractor"""
    org_id = current_user.get("organization_id") or "default"
    contractor = await user_repo.get_by_id(contractor_id)
    if not contractor or contractor.get("role") != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")
    if contractor.get("organization_id") and contractor.get("organization_id") != org_id:
        raise HTTPException(status_code=403, detail="Contractor belongs to different organization")
    return await do_create_withdrawal(data, contractor, current_user)


@router.get("")
async def get_withdrawals(
    contractor_id: Optional[str] = None,
    payment_status: Optional[str] = None,
    billing_entity: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    org_id = current_user.get("organization_id") or "default"
    cid = current_user["id"] if current_user.get("role") == "contractor" else contractor_id
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
async def get_withdrawal(withdrawal_id: str, current_user: dict = Depends(get_current_user)):
    org_id = current_user.get("organization_id") or "default"
    withdrawal = await withdrawal_repo.get_by_id(withdrawal_id, org_id)
    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")

    if current_user.get("role") == "contractor" and withdrawal.get("contractor_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return withdrawal


@router.put("/{withdrawal_id}/mark-paid")
async def mark_withdrawal_paid(withdrawal_id: str, current_user: dict = Depends(require_role("admin"))):
    org_id = current_user.get("organization_id") or "default"
    withdrawal = await withdrawal_repo.get_by_id(withdrawal_id, org_id)
    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    paid_at = datetime.now(timezone.utc).isoformat()
    result = await withdrawal_repo.mark_paid(withdrawal_id, paid_at)
    await invoice_repo.mark_paid_for_withdrawal(withdrawal_id)
    return result


@router.put("/bulk-mark-paid")
async def bulk_mark_paid(withdrawal_ids: List[str] = Body(...), current_user: dict = Depends(require_role("admin"))):
    org_id = current_user.get("organization_id") or "default"
    paid_at = datetime.now(timezone.utc).isoformat()
    updated = await withdrawal_repo.bulk_mark_paid(withdrawal_ids, paid_at, organization_id=org_id)
    for wid in withdrawal_ids:
        await invoice_repo.mark_paid_for_withdrawal(wid)
    return {"updated": updated}
