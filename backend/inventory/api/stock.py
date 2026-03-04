"""Stock history and adjustment routes — inventory bounded context."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from identity.application.auth_service import get_current_user, require_role
from catalog.application.queries import get_product_by_id
from inventory.application.inventory_service import (
    get_stock_history,
    process_adjustment_stock_changes,
)

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/{product_id}/history")
async def get_product_stock_history(
    product_id: str,
    limit: int = 50,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Get stock transaction history for a product (stock ledger)."""
    org_id = current_user.get("organization_id") or "default"
    product = await get_product_by_id(product_id, organization_id=org_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    history = await get_stock_history(product_id=product_id, limit=limit)
    return {"product_id": product_id, "sku": product.get("sku"), "history": history}
