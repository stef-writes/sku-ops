"""SKU generation and preview routes."""

from fastapi import APIRouter, HTTPException

from catalog.application.sku_service import preview_sku, sku_overview
from shared.api.deps import CurrentUserDep
from shared.kernel.errors import ResourceNotFoundError

router = APIRouter(tags=["sku"])


@router.get("/sku/preview")
async def get_sku_preview(
    _current_user: CurrentUserDep,
    department_id: str,
    product_name: str | None = None,
):
    """Preview the next SKU for a department (without consuming it)."""
    try:
        return await preview_sku(department_id, product_name)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/sku/overview")
async def get_sku_overview(
    _current_user: CurrentUserDep,
    product_name: str | None = None,
):
    """SKU system overview: format, departments with next available SKU."""
    return await sku_overview(product_name)
