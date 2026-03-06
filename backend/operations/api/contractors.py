"""Contractor management routes (admin only)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from identity.application.auth_service import hash_password, require_role
from identity.application.billing_entity_service import ensure_billing_entity
from identity.application.user_service import (
    User,
    UserCreate,
    UserUpdate,
    get_user_by_email,
    get_user_by_id,
    insert_user,
    list_contractors,
    update_user,
)
from identity.application.user_service import (
    delete_contractor as do_delete_contractor,
)
from kernel.types import CurrentUser

router = APIRouter(prefix="/contractors", tags=["contractors"])


@router.get("")
async def get_contractors(
    search: str | None = Query(None, description="Search by name, email, company, billing entity, or phone"),
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id
    return await list_contractors(org_id, search=search)


@router.post("")
async def create_contractor(data: UserCreate, current_user: CurrentUser = Depends(require_role("admin"))):
    existing = await get_user_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    billing_name = data.billing_entity or data.company or "Independent"
    be = await ensure_billing_entity(billing_name, current_user.organization_id)

    contractor = User(
        email=data.email,
        name=data.name,
        role="contractor",
        company=data.company or "Independent",
        billing_entity=billing_name,
        phone=data.phone,
    )
    contractor_dict = contractor.model_dump()
    contractor_dict["password"] = hash_password(data.password)
    contractor_dict["organization_id"] = current_user.organization_id
    contractor_dict["billing_entity_id"] = be.get("id") if be else None

    await insert_user(contractor_dict)

    return {k: v for k, v in contractor_dict.items() if k != "password"}


@router.put("/{contractor_id}")
async def update_contractor(contractor_id: str, data: UserUpdate, current_user: CurrentUser = Depends(require_role("admin"))):
    org_id = current_user.organization_id
    contractor = await get_user_by_id(contractor_id)
    if not contractor or contractor.get("role") != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")
    if contractor.get("organization_id") != org_id:
        raise HTTPException(status_code=404, detail="Contractor not found")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    result = await update_user(contractor_id, update_data, organization_id=org_id)
    return {k: v for k, v in result.items() if k != "password"}


@router.delete("/{contractor_id}")
async def delete_contractor(contractor_id: str, current_user: CurrentUser = Depends(require_role("admin"))):
    org_id = current_user.organization_id
    contractor = await get_user_by_id(contractor_id)
    if not contractor or contractor.get("role") != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")
    if contractor.get("organization_id") != org_id:
        raise HTTPException(status_code=404, detail="Contractor not found")

    deleted = await do_delete_contractor(contractor_id, organization_id=org_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Contractor not found")
    return {"message": "Contractor deleted"}
