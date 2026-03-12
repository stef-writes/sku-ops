"""Contractor management routes (admin only)."""

from fastapi import APIRouter, HTTPException, Query

from identity.application.auth_service import hash_password
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
from shared.api.deps import AdminDep

router = APIRouter(prefix="/contractors", tags=["contractors"])


@router.get("")
async def get_contractors(
    current_user: AdminDep,
    search: str | None = Query(
        None, description="Search by name, email, company, billing entity, or phone"
    ),
):
    return await list_contractors(search=search)


@router.post("")
async def create_contractor(data: UserCreate, current_user: AdminDep):
    existing = await get_user_by_email(data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    billing_name = data.billing_entity or data.company or "Independent"
    be = await ensure_billing_entity(billing_name)

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
    contractor_dict["billing_entity_id"] = be.id if be else None

    await insert_user(contractor_dict)

    return {k: v for k, v in contractor_dict.items() if k != "password"}


@router.put("/{contractor_id}")
async def update_contractor(contractor_id: str, data: UserUpdate, current_user: AdminDep):
    contractor = await get_user_by_id(contractor_id)
    if not contractor or contractor.role != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")
    if contractor.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Contractor not found")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    result = await update_user(contractor_id, update_data)
    return result.model_dump(exclude={"password"}) if result else {}


@router.delete("/{contractor_id}")
async def delete_contractor(contractor_id: str, current_user: AdminDep):
    contractor = await get_user_by_id(contractor_id)
    if not contractor or contractor.role != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")
    if contractor.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Contractor not found")

    deleted = await do_delete_contractor(contractor_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Contractor not found")
    return {"message": "Contractor deleted"}
