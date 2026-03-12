"""Return routes — process material returns against previous withdrawals."""

from fastapi import APIRouter, HTTPException, Request

from operations.application.queries import get_return_by_id as _get_return_by_id
from operations.application.queries import list_returns as _list_returns
from operations.application.return_service import create_return
from operations.domain.returns import ReturnCreate
from shared.api.deps import AdminDep, CurrentUserDep
from shared.infrastructure import event_hub
from shared.infrastructure.middleware.audit import audit_log
from shared.kernel import events

router = APIRouter(prefix="/returns", tags=["returns"])


@router.post("")
async def create_material_return(
    data: ReturnCreate,
    request: Request,
    current_user: AdminDep,
):
    """Process a return against a previous withdrawal. Restocks inventory and creates credit note."""
    try:
        result = await create_return(data, current_user)
        await audit_log(
            user_id=current_user.id,
            action="return.create",
            resource_type="return",
            resource_id=result.get("id"),
            details={
                "withdrawal_id": data.withdrawal_id,
                "total": result.get("total"),
                "item_count": len(data.items),
            },
            request=request,
            org_id=current_user.organization_id,
        )
        await event_hub.emit(events.INVENTORY_UPDATED, org_id=current_user.organization_id)
        await event_hub.emit(
            events.WITHDRAWAL_UPDATED,
            org_id=current_user.organization_id,
            id=data.withdrawal_id,
        )
        return result
    except (ValueError, RuntimeError, OSError) as e:
        status = getattr(e, "status_hint", 400)
        raise HTTPException(status_code=status, detail=str(e)) from e


@router.get("")
async def list_returns(
    current_user: AdminDep,
    contractor_id: str | None = None,
    withdrawal_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    return await _list_returns(
        contractor_id=contractor_id,
        withdrawal_id=withdrawal_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/{return_id}")
async def get_return(
    return_id: str,
    current_user: CurrentUserDep,
):
    ret = await _get_return_by_id(return_id)
    if not ret:
        raise HTTPException(status_code=404, detail="Return not found")
    return ret
