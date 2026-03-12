"""Department CRUD routes."""

from fastapi import APIRouter, HTTPException, Request

from catalog.application import queries as catalog_queries
from catalog.domain.department import Department, DepartmentCreate
from shared.api.deps import AdminDep, CurrentUserDep
from shared.infrastructure.middleware.audit import audit_log

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=list[Department])
async def get_departments(current_user: CurrentUserDep):
    return await catalog_queries.list_departments()


@router.post("", response_model=Department)
async def create_department(data: DepartmentCreate, current_user: AdminDep):
    existing = await catalog_queries.get_department_by_code(data.code)
    if existing:
        raise HTTPException(status_code=400, detail="Department code already exists")

    dept = Department(
        name=data.name,
        code=data.code.upper(),
        description=data.description or "",
        organization_id=current_user.organization_id,
    )
    await catalog_queries.insert_department(dept)
    return dept


@router.put("/{dept_id}", response_model=Department)
async def update_department(dept_id: str, data: DepartmentCreate, current_user: AdminDep):
    existing = await catalog_queries.get_department_by_id(dept_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Department not found")
    result = await catalog_queries.update_department(
        dept_id,
        data.name,
        data.description or "",
    )
    return result


@router.delete("/{dept_id}")
async def delete_department(dept_id: str, request: Request, current_user: AdminDep):
    existing = await catalog_queries.get_department_by_id(dept_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Department not found")
    product_count = await catalog_queries.count_products_by_department(dept_id)
    if product_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete department with products")

    deleted = await catalog_queries.delete_department(dept_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Department not found")
    await audit_log(
        user_id=current_user.id,
        action="department.delete",
        resource_type="department",
        resource_id=dept_id,
        details={"name": existing.name, "code": existing.code},
        request=request,
        org_id=current_user.organization_id,
    )
    return {"message": "Department deleted"}
