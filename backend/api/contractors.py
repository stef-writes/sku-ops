"""Contractor management routes (admin only)."""
from fastapi import APIRouter, HTTPException, Depends

from auth import hash_password, require_role
from models import User, UserCreate, UserUpdate
from repositories import user_repo

router = APIRouter(prefix="/contractors", tags=["contractors"])


@router.get("")
async def get_contractors(current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    return await user_repo.list_contractors()


@router.post("")
async def create_contractor(data: UserCreate, current_user: dict = Depends(require_role("admin"))):
    existing = await user_repo.get_by_email(data.email)
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

    await user_repo.insert(contractor_dict)

    return {k: v for k, v in contractor_dict.items() if k != "password"}


@router.put("/{contractor_id}")
async def update_contractor(contractor_id: str, data: UserUpdate, current_user: dict = Depends(require_role("admin"))):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    contractor = await user_repo.get_by_id(contractor_id)
    if not contractor or contractor.get("role") != "contractor":
        raise HTTPException(status_code=404, detail="Contractor not found")

    result = await user_repo.update(contractor_id, update_data)
    return {k: v for k, v in result.items() if k != "password"}


@router.delete("/{contractor_id}")
async def delete_contractor(contractor_id: str, current_user: dict = Depends(require_role("admin"))):
    deleted = await user_repo.delete_contractor(contractor_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Contractor not found")
    return {"message": "Contractor deleted"}
