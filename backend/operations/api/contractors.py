"""Contractor management routes (admin only)."""
from fastapi import APIRouter, HTTPException, Depends

from identity.application.auth_service import hash_password, require_role
from identity.domain.user import User, UserCreate, UserUpdate
from identity.application.user_service import (
    get_user_by_id,
    get_user_by_email,
    list_contractors,
    insert_user,
    update_user,
    delete_contractor as do_delete_contractor,
)

router = APIRouter(prefix="/contractors", tags=["contractors"])


@router.get("")
async def get_contractors(current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    org_id = current_user.get("organization_id") or "default"
    return await list_contractors(org_id)


@router.post("")
async def create_contractor(data: UserCreate, current_user: dict = Depends(require_role("admin"))):
    existing = await get_user_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    contractor = User(
        email=data.email,
        name=data.name,
        role="contractor",
        company=data.company or "Independent",
        billing_entity=data.billing_entity or data.company or "Independent",
        phone=data.phone,
    )
    contractor_dict = contractor.model_dump()
    contractor_dict["password"] = hash_password(data.password)
    contractor_dict["organization_id"] = current_user.get("organization_id") or "default"

    await insert_user(contractor_dict)

    return {k: v for k, v in contractor_dict.items() if k != "password"}


@router.put("/{contractor_id}")
async def update_contractor(contractor_id: str, data: UserUpdate, current_user: dict = Depends(require_role("admin"))):
    org_id = current_user.get("organization_id") or "default"
    contractor = await get_user_by_id(contractor_id)
    if not contractor or contractor.get("role") != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")
    if contractor.get("organization_id") != org_id:
        raise HTTPException(status_code=404, detail="Contractor not found")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    result = await update_user(contractor_id, update_data)
    return {k: v for k, v in result.items() if k != "password"}


@router.delete("/{contractor_id}")
async def delete_contractor(contractor_id: str, current_user: dict = Depends(require_role("admin"))):
    org_id = current_user.get("organization_id") or "default"
    contractor = await get_user_by_id(contractor_id)
    if not contractor or contractor.get("role") != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")
    if contractor.get("organization_id") != org_id:
        raise HTTPException(status_code=404, detail="Contractor not found")

    deleted = await do_delete_contractor(contractor_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Contractor not found")
    return {"message": "Contractor deleted"}
