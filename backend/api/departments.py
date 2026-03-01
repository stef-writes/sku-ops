"""Department CRUD routes."""
from typing import List

from fastapi import APIRouter, HTTPException, Depends

from auth import get_current_user, require_role
from models import Department, DepartmentCreate
from repositories import department_repo

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=List[Department])
async def get_departments(current_user: dict = Depends(get_current_user)):
    return await department_repo.list_all()


@router.post("", response_model=Department)
async def create_department(data: DepartmentCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    existing = await department_repo.get_by_code(data.code)
    if existing:
        raise HTTPException(status_code=400, detail="Department code already exists")

    dept = Department(
        name=data.name,
        code=data.code.upper(),
        description=data.description or "",
    )
    await department_repo.insert(dept.model_dump())
    return dept


@router.put("/{dept_id}", response_model=Department)
async def update_department(dept_id: str, data: DepartmentCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    result = await department_repo.update(dept_id, data.name, data.description or "")
    if not result:
        raise HTTPException(status_code=404, detail="Department not found")
    return result


@router.delete("/{dept_id}")
async def delete_department(dept_id: str, current_user: dict = Depends(require_role("admin"))):
    product_count = await department_repo.count_products_by_department(dept_id)
    if product_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete department with products")

    deleted = await department_repo.delete(dept_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Department not found")
    return {"message": "Department deleted"}
