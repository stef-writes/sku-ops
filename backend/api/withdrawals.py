"""Material withdrawal (POS) routes."""
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from auth import get_current_user, require_role
from models import MaterialWithdrawal, MaterialWithdrawalCreate
from repositories import user_repo, withdrawal_repo
from services.withdrawal_service import create_withdrawal as do_create_withdrawal

router = APIRouter(prefix="/withdrawals", tags=["withdrawals"])


@router.post("", response_model=MaterialWithdrawal)
async def create_withdrawal(data: MaterialWithdrawalCreate, current_user: dict = Depends(get_current_user)):
    """Create a material withdrawal - Contractors withdraw materials charged to their account"""
    contractor = current_user if current_user.get("role") == "contractor" else current_user
    return await do_create_withdrawal(data, contractor, current_user)


@router.post("/for-contractor")
async def create_withdrawal_for_contractor(
    contractor_id: str,
    data: MaterialWithdrawalCreate,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Warehouse manager creates withdrawal on behalf of a contractor"""
    contractor = await user_repo.get_by_id(contractor_id)
    if not contractor or contractor.get("role") != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")
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
    cid = current_user["id"] if current_user.get("role") == "contractor" else contractor_id
    return await withdrawal_repo.list_withdrawals(
        contractor_id=cid,
        payment_status=payment_status,
        billing_entity=billing_entity,
        start_date=start_date,
        end_date=end_date,
        limit=1000,
    )


@router.get("/{withdrawal_id}")
async def get_withdrawal(withdrawal_id: str, current_user: dict = Depends(get_current_user)):
    withdrawal = await withdrawal_repo.get_by_id(withdrawal_id)
    if not withdrawal:
        raise HTTPException(status_code=404, detail="Withdrawal not found")

    if current_user.get("role") == "contractor" and withdrawal.get("contractor_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return withdrawal


@router.put("/{withdrawal_id}/mark-paid")
async def mark_withdrawal_paid(withdrawal_id: str, current_user: dict = Depends(require_role("admin"))):
    from datetime import datetime, timezone

    paid_at = datetime.now(timezone.utc).isoformat()
    result = await withdrawal_repo.mark_paid(withdrawal_id, paid_at)
    if not result:
        raise HTTPException(status_code=404, detail="Withdrawal not found")
    await invoice_repo.mark_paid_for_withdrawal(withdrawal_id)
    return result


@router.put("/bulk-mark-paid")
async def bulk_mark_paid(withdrawal_ids: List[str] = Body(...), current_user: dict = Depends(require_role("admin"))):
    from datetime import datetime, timezone

    paid_at = datetime.now(timezone.utc).isoformat()
    updated = await withdrawal_repo.bulk_mark_paid(withdrawal_ids, paid_at)
    for wid in withdrawal_ids:
        await invoice_repo.mark_paid_for_withdrawal(wid)
    return {"updated": updated}
