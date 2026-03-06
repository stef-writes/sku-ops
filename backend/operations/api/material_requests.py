"""Material request routes - contractor pick list, staff processes into withdrawal."""
from datetime import UTC, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from catalog.application.queries import list_products
from finance.application.invoice_service import create_invoice_from_withdrawals
from identity.application.auth_service import get_current_user, require_role
from identity.application.org_service import get_org_settings
from identity.application.user_service import get_user_by_id
from inventory.application.inventory_service import process_withdrawal_stock_changes
from kernel.types import CurrentUser
from operations.application.withdrawal_service import create_withdrawal as _do_create_withdrawal
from operations.domain.material_request import (
    MaterialRequest,
    MaterialRequestCreate,
    MaterialRequestProcess,
)
from operations.domain.withdrawal import MaterialWithdrawalCreate, WithdrawalItem
from operations.infrastructure.material_request_repo import material_request_repo
from shared.infrastructure import event_hub
from shared.infrastructure.database import transaction


async def do_create_withdrawal(data, contractor, current_user: CurrentUser, conn=None):
    settings = await get_org_settings(current_user.organization_id)
    return await _do_create_withdrawal(
        data, contractor, current_user,
        list_products=list_products,
        process_stock_changes=process_withdrawal_stock_changes,
        create_invoice=create_invoice_from_withdrawals,
        tax_rate=settings.default_tax_rate,
        conn=conn,
    )

router = APIRouter(prefix="/material-requests", tags=["material-requests"])


@router.post("")
async def create_material_request(data: MaterialRequestCreate, current_user: CurrentUser = Depends(get_current_user)):
    """Contractor creates a material request (pick list). Staff will process it into a withdrawal."""
    if current_user.role != "contractor":
        raise HTTPException(status_code=403, detail="Only contractors can create material requests")

    if not data.items:
        raise HTTPException(status_code=400, detail="At least one item is required")

    org_id = current_user.organization_id
    mat_request = MaterialRequest(
        contractor_id=current_user.id,
        contractor_name=current_user.name,
        items=data.items,
        job_id=data.job_id,
        service_address=data.service_address,
        notes=data.notes,
        organization_id=org_id,
    )
    await material_request_repo.insert(mat_request)
    req = await material_request_repo.get_by_id(mat_request.id, org_id)
    await event_hub.emit("material_request.created", org_id=org_id, id=mat_request.id)
    return req or mat_request.model_dump()


@router.get("")
async def list_material_requests(current_user: CurrentUser = Depends(get_current_user)):
    """Contractors see own requests; admin/WM see all pending."""
    org_id = current_user.organization_id
    role = current_user.role

    if role == "contractor":
        return await material_request_repo.list_by_contractor(
            contractor_id=current_user.id, organization_id=org_id
        )
    if role in ("admin", "warehouse_manager"):
        return await material_request_repo.list_pending(organization_id=org_id)
    raise HTTPException(status_code=403, detail="Insufficient permissions")


@router.get("/{request_id}")
async def get_material_request(request_id: str, current_user: CurrentUser = Depends(get_current_user)):
    org_id = current_user.organization_id
    req = await material_request_repo.get_by_id(request_id, org_id)
    if not req:
        raise HTTPException(status_code=404, detail="Material request not found")

    if current_user.role == "contractor" and req.get("contractor_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return req


@router.post("/{request_id}/process")
async def process_material_request(
    request_id: str,
    data: MaterialRequestProcess,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    """Convert a pending material request into a withdrawal. Staff supplies job_id and service_address."""
    org_id = current_user.organization_id
    req = await material_request_repo.get_by_id(request_id, org_id)
    if not req:
        raise HTTPException(status_code=404, detail="Material request not found")
    if req.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Request already processed")

    contractor = await get_user_by_id(req["contractor_id"])
    if not contractor or contractor.get("role") != "contractor":
        raise HTTPException(status_code=400, detail="Contractor not found")
    if contractor.get("organization_id") and contractor.get("organization_id") != org_id:
        raise HTTPException(status_code=403, detail="Contractor belongs to different organization")

    job_id = (data.job_id or req.get("job_id") or "").strip()
    service_address = (data.service_address or req.get("service_address") or "").strip()
    if not job_id:
        raise HTTPException(status_code=400, detail="Job ID is required")
    if not service_address:
        raise HTTPException(status_code=400, detail="Service address is required")

    withdrawal_data = MaterialWithdrawalCreate(
        items=[WithdrawalItem(**i) for i in req["items"]],
        job_id=job_id,
        service_address=service_address,
        notes=data.notes,
    )

    async with transaction() as conn:
        withdrawal = await do_create_withdrawal(withdrawal_data, contractor, current_user, conn=conn)
        await material_request_repo.mark_processed(
            request_id=request_id,
            withdrawal_id=withdrawal["id"],
            processed_by_id=current_user.id,
            processed_at=datetime.now(UTC).isoformat(),
            conn=conn,
        )
    await event_hub.emit("material_request.processed", org_id=org_id, id=request_id, withdrawal_id=withdrawal["id"])
    await event_hub.emit("withdrawal.created", org_id=org_id, id=withdrawal["id"])
    await event_hub.emit("inventory.updated", org_id=org_id)
    return withdrawal
