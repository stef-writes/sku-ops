"""Vendor CRUD routes."""
from typing import List

from fastapi import APIRouter, HTTPException, Depends

from identity.application.auth_service import get_current_user, require_role
from catalog.domain.vendor import Vendor, VendorCreate
from catalog.infrastructure.vendor_repo import vendor_repo

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("", response_model=List[Vendor])
async def get_vendors(current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    org_id = current_user.get("organization_id") or "default"
    return await vendor_repo.list_all(org_id)


@router.post("", response_model=Vendor)
async def create_vendor(data: VendorCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    org_id = current_user.get("organization_id") or "default"
    vendor = Vendor(**data.model_dump())
    vendor_dict = vendor.model_dump()
    vendor_dict["organization_id"] = org_id
    await vendor_repo.insert(vendor_dict)
    return vendor


@router.put("/{vendor_id}", response_model=Vendor)
async def update_vendor(vendor_id: str, data: VendorCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    org_id = current_user.get("organization_id") or "default"
    existing = await vendor_repo.get_by_id(vendor_id, org_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Vendor not found")
    result = await vendor_repo.update(vendor_id, data.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return result


@router.delete("/{vendor_id}")
async def delete_vendor(vendor_id: str, current_user: dict = Depends(require_role("admin"))):
    org_id = current_user.get("organization_id") or "default"
    existing = await vendor_repo.get_by_id(vendor_id, org_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Vendor not found")
    deleted = await vendor_repo.delete(vendor_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {"message": "Vendor deleted"}
