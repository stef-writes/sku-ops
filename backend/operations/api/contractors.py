"""Contractor management routes (admin only)."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from operations.application.contractor_service import (
    UpdateContractorCommand,
    create_contractor,
    delete_contractor,
    list_contractors,
    update_contractor,
)
from shared.api.deps import AdminDep

router = APIRouter(prefix="/contractors", tags=["contractors"])


class ContractorCreate(BaseModel):
    email: str
    password: str
    name: str
    company: str | None = None
    billing_entity: str | None = None
    phone: str | None = None


@router.get("")
async def get_contractors(
    current_user: AdminDep,
    search: str | None = Query(
        None, description="Search by name, email, company, billing entity, or phone"
    ),
):
    return await list_contractors(search=search)


@router.post("")
async def create_contractor_route(data: ContractorCreate, current_user: AdminDep):
    try:
        result = await create_contractor(
            email=data.email,
            password=data.password,
            name=data.name,
            company=data.company,
            billing_entity_name=data.billing_entity,
            phone=data.phone,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.model_dump()


@router.put("/{contractor_id}")
async def update_contractor_route(
    contractor_id: str,
    data: UpdateContractorCommand,
    current_user: AdminDep,
):
    result = await update_contractor(contractor_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Contractor not found")
    return result.model_dump()


@router.delete("/{contractor_id}")
async def delete_contractor_route(contractor_id: str, current_user: AdminDep):
    deleted = await delete_contractor(contractor_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Contractor not found")
    return {"message": "Contractor deleted"}
