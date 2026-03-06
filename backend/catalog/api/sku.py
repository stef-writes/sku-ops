"""SKU generation and preview routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from catalog.application.sku_service import slug_from_name
from catalog.infrastructure.department_repo import department_repo
from catalog.infrastructure.sku_repo import sku_repo
from identity.application.auth_service import get_current_user
from kernel.types import CurrentUser

router = APIRouter(tags=["sku"])

SKU_FORMAT = "DEPT-SLUG-XXXXX"


@router.get("/sku/preview")
async def get_sku_preview(
    department_id: str,
    product_name: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Preview the next SKU for a department (without consuming it)."""
    department = await department_repo.get_by_id(department_id)
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")
    code = department["code"]
    next_num = await sku_repo.get_next_number(code)
    slug = slug_from_name(product_name or "", max_len=6) if product_name else "ITM"
    next_sku = f"{code}-{slug}-{str(next_num).zfill(6)}"
    return {"next_sku": next_sku, "department_code": code, "format": SKU_FORMAT, "slug": slug}


@router.get("/sku/overview")
async def get_sku_overview(
    product_name: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """SKU system overview: format, departments with next available SKU."""
    departments = await department_repo.list_all()
    counters = await sku_repo.get_all_counters()
    slug = slug_from_name(product_name or "", max_len=6) if product_name else "ITM"
    depts_with_next = []
    for d in departments:
        code = d["code"]
        next_num = (counters.get(code, 0) + 1)
        depts_with_next.append({
            **d,
            "next_sku": f"{code}-{slug}-{str(next_num).zfill(6)}",
        })
    return {"format": SKU_FORMAT, "departments": depts_with_next}
