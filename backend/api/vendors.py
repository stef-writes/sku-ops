"""Vendor CRUD routes."""
from typing import List

from fastapi import APIRouter, HTTPException, Depends

from auth import get_current_user, require_role
from models import Vendor, VendorCreate
from repositories import vendor_repo

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("", response_model=List[Vendor])
async def get_vendors(current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    return await vendor_repo.list_all()


@router.post("", response_model=Vendor)
async def create_vendor(data: VendorCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    vendor = Vendor(**data.model_dump())
    await vendor_repo.insert(vendor.model_dump())
    return vendor


@router.put("/{vendor_id}", response_model=Vendor)
async def update_vendor(vendor_id: str, data: VendorCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    result = await vendor_repo.update(vendor_id, data.model_dump())
    if not result:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return result


@router.delete("/{vendor_id}")
async def delete_vendor(vendor_id: str, current_user: dict = Depends(require_role("admin"))):
    deleted = await vendor_repo.delete(vendor_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return {"message": "Vendor deleted"}
