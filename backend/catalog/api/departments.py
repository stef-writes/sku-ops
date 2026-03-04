"""Department CRUD routes."""
from typing import List

from fastapi import APIRouter, HTTPException, Depends

from identity.application.auth_service import get_current_user, require_role
from catalog.domain.department import Department, DepartmentCreate
from catalog.infrastructure.department_repo import department_repo

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=List[Department])
async def get_departments(current_user: dict = Depends(get_current_user)):
    org_id = current_user.get("organization_id") or "default"
    return await department_repo.list_all(org_id)


@router.post("", response_model=Department)
async def create_department(data: DepartmentCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    org_id = current_user.get("organization_id") or "default"
    existing = await department_repo.get_by_code(data.code, org_id)
    if existing:
        raise HTTPException(status_code=400, detail="Department code already exists")

    dept = Department(
        name=data.name,
        code=data.code.upper(),
        description=data.description or "",
    )
    dept_dict = dept.model_dump()
    dept_dict["organization_id"] = org_id
    await department_repo.insert(dept_dict)
    return dept


@router.put("/{dept_id}", response_model=Department)
async def update_department(dept_id: str, data: DepartmentCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    org_id = current_user.get("organization_id") or "default"
    existing = await department_repo.get_by_id(dept_id, org_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Department not found")
    result = await department_repo.update(dept_id, data.name, data.description or "")
    return result


@router.delete("/{dept_id}")
async def delete_department(dept_id: str, current_user: dict = Depends(require_role("admin"))):
    org_id = current_user.get("organization_id") or "default"
    existing = await department_repo.get_by_id(dept_id, org_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Department not found")
    product_count = await department_repo.count_products_by_department(dept_id)
    if product_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete department with products")

    deleted = await department_repo.delete(dept_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Department not found")
    return {"message": "Department deleted"}
