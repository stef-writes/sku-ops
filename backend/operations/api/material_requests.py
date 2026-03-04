"""Material request routes - contractor pick list, staff processes into withdrawal."""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from identity.application.auth_service import get_current_user, require_role
from operations.domain.material_request import MaterialRequestCreate, MaterialRequestProcess
from operations.domain.withdrawal import MaterialWithdrawalCreate, WithdrawalItem
from operations.infrastructure.material_request_repo import material_request_repo
from identity.infrastructure.user_repo import user_repo
from operations.infrastructure.withdrawal_repo import withdrawal_repo
from operations.application.withdrawal_service import create_withdrawal as do_create_withdrawal
from shared.infrastructure.database import transaction

router = APIRouter(prefix="/material-requests", tags=["material-requests"])


@router.post("")
async def create_material_request(data: MaterialRequestCreate, current_user: dict = Depends(get_current_user)):
    """Contractor creates a material request (pick list). Staff will process it into a withdrawal."""
    if current_user.get("role") != "contractor":
        raise HTTPException(status_code=403, detail="Only contractors can create material requests")

    if not data.items:
        raise HTTPException(status_code=400, detail="At least one item is required")

    org_id = current_user.get("organization_id") or "default"
    request_id = str(uuid4())
    request_dict = {
        "id": request_id,
        "contractor_id": current_user["id"],
        "contractor_name": current_user.get("name", ""),
        "items": [i.model_dump() if hasattr(i, "model_dump") else i for i in data.items],
        "status": "pending",
        "job_id": data.job_id,
        "service_address": data.service_address,
        "notes": data.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "organization_id": org_id,
    }
    await material_request_repo.insert(request_dict)
    req = await material_request_repo.get_by_id(request_id, org_id)
    return req or request_dict


@router.get("")
async def list_material_requests(current_user: dict = Depends(get_current_user)):
    """Contractors see own requests; admin/WM see all pending."""
    org_id = current_user.get("organization_id") or "default"
    role = current_user.get("role")

    if role == "contractor":
        return await material_request_repo.list_by_contractor(
            contractor_id=current_user["id"], organization_id=org_id
        )
    if role in ("admin", "warehouse_manager"):
        return await material_request_repo.list_pending(organization_id=org_id)
    raise HTTPException(status_code=403, detail="Insufficient permissions")


@router.get("/{request_id}")
async def get_material_request(request_id: str, current_user: dict = Depends(get_current_user)):
    org_id = current_user.get("organization_id") or "default"
    req = await material_request_repo.get_by_id(request_id, org_id)
    if not req:
        raise HTTPException(status_code=404, detail="Material request not found")

    if current_user.get("role") == "contractor" and req.get("contractor_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return req


@router.post("/{request_id}/process")
async def process_material_request(
    request_id: str,
    data: MaterialRequestProcess,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Convert a pending material request into a withdrawal. Staff supplies job_id and service_address."""
    org_id = current_user.get("organization_id") or "default"
    req = await material_request_repo.get_by_id(request_id, org_id)
    if not req:
        raise HTTPException(status_code=404, detail="Material request not found")
    if req.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Request already processed")

    contractor = await user_repo.get_by_id(req["contractor_id"])
    if not contractor or contractor.get("role") != "contractor":
        raise HTTPException(status_code=400, detail="Contractor not found")
    if contractor.get("organization_id") and contractor.get("organization_id") != org_id:
        raise HTTPException(status_code=403, detail="Contractor belongs to different organization")

    withdrawal_data = MaterialWithdrawalCreate(
        items=[WithdrawalItem(**i) for i in req["items"]],
        job_id=data.job_id.strip(),
        service_address=data.service_address.strip(),
        notes=data.notes,
    )

    async with transaction() as conn:
        withdrawal = await do_create_withdrawal(withdrawal_data, contractor, current_user, conn=conn)
        await material_request_repo.mark_processed(
            request_id=request_id,
            withdrawal_id=withdrawal["id"],
            processed_by_id=current_user["id"],
            processed_at=datetime.now(timezone.utc).isoformat(),
            conn=conn,
        )
    return withdrawal
