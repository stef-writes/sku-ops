"""Vendor CRUD routes."""

from fastapi import APIRouter, HTTPException, Request

from catalog.application import queries as catalog_queries
from catalog.domain.vendor import Vendor, VendorCreate
from shared.api.deps import AdminDep
from shared.infrastructure.middleware.audit import audit_log

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("", response_model=list[Vendor])
async def get_vendors(current_user: AdminDep):
    return await catalog_queries.list_vendors()


@router.post("", response_model=Vendor)
async def create_vendor(data: VendorCreate, current_user: AdminDep):
    vendor = Vendor(**data.model_dump(), organization_id=current_user.organization_id)
    await catalog_queries.insert_vendor(vendor)
    return vendor


@router.put("/{vendor_id}", response_model=Vendor)
async def update_vendor(vendor_id: str, data: VendorCreate, current_user: AdminDep):
    existing = await catalog_queries.get_vendor_by_id(vendor_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Vendor not found")
    result = await catalog_queries.update_vendor(vendor_id, data.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return result


@router.delete("/{vendor_id}")
async def delete_vendor(vendor_id: str, request: Request, current_user: AdminDep):
    existing = await catalog_queries.get_vendor_by_id(vendor_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Vendor not found")
    deleted = await catalog_queries.delete_vendor(vendor_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    await audit_log(
        user_id=current_user.id,
        action="vendor.delete",
        resource_type="vendor",
        resource_id=vendor_id,
        details={"name": existing.get("name")},
        request=request,
        org_id=current_user.organization_id,
    )
    return {"message": "Vendor deleted"}
