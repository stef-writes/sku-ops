"""Return routes — process material returns against previous withdrawals."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from finance.application.credit_note_service import insert_credit_note
from identity.application.auth_service import get_current_user, require_role
from identity.application.org_service import get_org_settings
from inventory.application.inventory_service import process_receiving_stock_changes
from kernel.types import CurrentUser
from operations.application.queries import get_return_by_id as _get_return_by_id
from operations.application.queries import get_withdrawal_by_id
from operations.application.queries import list_returns as _list_returns
from operations.application.return_service import create_return
from operations.domain.returns import ReturnCreate
from shared.infrastructure import event_hub
from shared.infrastructure.middleware.audit import audit_log

router = APIRouter(prefix="/returns", tags=["returns"])


@router.post("")
async def create_material_return(
    data: ReturnCreate,
    request: Request,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    """Process a return against a previous withdrawal. Restocks inventory and creates credit note."""
    settings = await get_org_settings(current_user.organization_id)
    try:
        result = await create_return(
            data,
            current_user,
            get_withdrawal=get_withdrawal_by_id,
            restock=process_receiving_stock_changes,
            create_credit_note=insert_credit_note,
            tax_rate=settings.default_tax_rate,
        )
        await audit_log(
            user_id=current_user.id, action="return.create",
            resource_type="return", resource_id=result.get("id"),
            details={"withdrawal_id": data.withdrawal_id, "total": result.get("total"),
                      "item_count": len(data.items)},
            request=request, org_id=current_user.organization_id,
        )
        org_id = current_user.organization_id
        await event_hub.emit("inventory.updated", org_id=org_id)
        await event_hub.emit("withdrawal.updated", org_id=org_id, id=data.withdrawal_id)
        return result
    except Exception as e:
        status = getattr(e, "status_hint", 400)
        raise HTTPException(status_code=status, detail=str(e))


@router.get("")
async def list_returns(
    contractor_id: str | None = None,
    withdrawal_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id
    return await _list_returns(
        contractor_id=contractor_id,
        withdrawal_id=withdrawal_id,
        start_date=start_date,
        end_date=end_date,
        organization_id=org_id,
    )


@router.get("/{return_id}")
async def get_return(
    return_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    org_id = current_user.organization_id
    ret = await _get_return_by_id(return_id, org_id)
    if not ret:
        raise HTTPException(status_code=404, detail="Return not found")
    return ret
