"""Stock history and adjustment routes - inventory bounded context."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from identity.application.auth_service import get_current_user, require_role
from kernel.types import CurrentUser
from catalog.application.queries import get_product_by_id
from inventory.application.inventory_service import (
    get_stock_history,
    process_adjustment_stock_changes,
)

router = APIRouter(prefix="/stock", tags=["stock"])


class AdjustStockRequest(BaseModel):
    quantity_delta: float
    reason: str = "correction"


@router.get("/{product_id}/history")
async def get_product_stock_history(
    product_id: str,
    limit: int = 50,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    org_id = current_user.organization_id
    product = await get_product_by_id(product_id, organization_id=org_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    history = await get_stock_history(product_id=product_id, limit=limit)
    return {"product_id": product_id, "sku": product.get("sku"), "history": history}


@router.post("/{product_id}/adjust")
async def adjust_stock(
    product_id: str,
    data: AdjustStockRequest,
    current_user: CurrentUser = Depends(require_role("admin", "warehouse_manager")),
):
    try:
        await process_adjustment_stock_changes(
            product_id=product_id,
            quantity_delta=data.quantity_delta,
            reason=data.reason,
            user_id=current_user.id,
            user_name=current_user.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Stock adjusted"}
