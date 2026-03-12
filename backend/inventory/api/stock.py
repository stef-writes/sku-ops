"""Stock history and adjustment routes - inventory bounded context."""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from catalog.application.queries import get_product_by_id
from inventory.application.inventory_service import (
    get_stock_history,
    process_adjustment_stock_changes,
)
from shared.api.deps import AdminDep
from shared.infrastructure import event_hub
from shared.infrastructure.middleware.audit import audit_log
from shared.kernel import events

router = APIRouter(prefix="/stock", tags=["stock"])


class AdjustStockRequest(BaseModel):
    quantity_delta: float
    reason: str = "correction"


@router.get("/{product_id}/history")
async def get_product_stock_history(
    product_id: str,
    current_user: AdminDep,
    limit: int = Query(50, ge=1, le=500),
):
    product = await get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    history = await get_stock_history(product_id=product_id, limit=limit)
    return {"product_id": product_id, "sku": product.sku, "history": history}


@router.post("/{product_id}/adjust")
async def adjust_stock(
    product_id: str,
    data: AdjustStockRequest,
    request: Request,
    current_user: AdminDep,
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
        raise HTTPException(status_code=400, detail=str(e)) from e
    await audit_log(
        user_id=current_user.id,
        action="stock.adjust",
        resource_type="product",
        resource_id=product_id,
        details={"quantity_delta": data.quantity_delta, "reason": data.reason},
        request=request,
        org_id=current_user.organization_id,
    )
    await event_hub.emit(
        events.INVENTORY_UPDATED, org_id=current_user.organization_id, ids=[product_id]
    )
    return {"message": "Stock adjusted"}
