"""Purchase order API routes."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from identity.application.auth_service import require_role
from purchasing.domain.purchase_order import CreatePORequest, MarkDeliveryRequest, ReceiveItemsRequest
from purchasing.infrastructure.po_repo import get_po, get_po_items, list_pos
from purchasing.application.purchase_order_service import (
    create_purchase_order,
    mark_delivery_received,
    receive_po_items,
    PurchasingDeps,
)
from catalog.application.queries import (
    list_departments, get_department_by_code, find_vendor_by_name, insert_vendor,
    list_products_by_vendor, get_product_by_id, find_product_by_original_sku_and_vendor,
    find_product_by_name_and_vendor, update_product,
)
from catalog.application.product_lifecycle import create_product as lifecycle_create
from inventory.application.inventory_service import process_receiving_stock_changes
from inventory.application.uom_classifier import classify_uom_batch as _classify_uom_batch
from documents.application.import_parser import infer_uom, suggest_department
from documents.application.enrichment_service import enrich_for_import
from shared.infrastructure.config import LLM_AVAILABLE as _LLM_AVAILABLE

logger = logging.getLogger(__name__)


async def _wired_classify_uom_batch(products):
    gen_text = None
    if _LLM_AVAILABLE:
        from assistant.application.llm import generate_text
        gen_text = generate_text
    return await _classify_uom_batch(products, generate_text=gen_text, rule_infer=infer_uom)


def _build_deps() -> PurchasingDeps:
    return PurchasingDeps(
        list_departments=list_departments,
        get_department_by_code=get_department_by_code,
        find_vendor_by_name=find_vendor_by_name,
        insert_vendor=insert_vendor,
        list_products_by_vendor=list_products_by_vendor,
        get_product_by_id=get_product_by_id,
        find_product_by_sku_and_vendor=find_product_by_original_sku_and_vendor,
        find_product_by_name_and_vendor=find_product_by_name_and_vendor,
        update_product=update_product,
        create_product=lambda **kw: lifecycle_create(**kw, on_stock_import=process_receiving_stock_changes),
        process_receiving_stock_changes=process_receiving_stock_changes,
        classify_uom_batch=_wired_classify_uom_batch,
        infer_uom=infer_uom,
        suggest_department=suggest_department,
        enrich_for_import=enrich_for_import,
    )

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


@router.post("")
async def create_po(
    data: CreatePORequest,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Save reviewed receipt items as a pending purchase order (no inventory update)."""
    return await create_purchase_order(
        vendor_name=data.vendor_name,
        products=data.products,
        deps=_build_deps(),
        document_date=data.document_date,
        total=data.total,
        department_id=data.department_id,
        create_vendor_if_missing=data.create_vendor_if_missing,
        current_user=current_user,
    )


@router.get("")
async def list_purchase_orders(
    status: Optional[str] = None,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """List purchase orders, optionally filtered by status (pending/partial/received)."""
    org_id = current_user.get("organization_id") or "default"
    pos = await list_pos(org_id, status=status)
    for po in pos:
        items = await get_po_items(po["id"])
        po["item_count"] = len(items)
        po["ordered_count"] = sum(1 for i in items if i["status"] == "ordered")
        po["pending_count"] = sum(1 for i in items if i["status"] == "pending")
        po["arrived_count"] = sum(1 for i in items if i["status"] == "arrived")
    return pos


@router.get("/{po_id}")
async def get_purchase_order(
    po_id: str,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Get a purchase order with all its items."""
    org_id = current_user.get("organization_id") or "default"
    po = await get_po(po_id, org_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    items = await get_po_items(po_id)
    return {**po, "items": items}


@router.post("/{po_id}/delivery")
async def mark_delivery(
    po_id: str,
    data: MarkDeliveryRequest,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Mark selected 'ordered' items as 'pending' (delivery arrived at dock)."""
    return await mark_delivery_received(
        po_id=po_id,
        item_ids=data.item_ids,
        current_user=current_user,
    )


@router.post("/{po_id}/receive")
async def receive_items(
    po_id: str,
    data: ReceiveItemsRequest,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Mark selected items as arrived and update inventory stock."""
    result = await receive_po_items(
        po_id=po_id,
        item_updates=data.items,
        deps=_build_deps(),
        current_user=current_user,
    )
    if result.get("cost_total", 0) > 0:
        from finance.adapters.invoicing_factory import get_invoicing_gateway
        from identity.application.org_service import get_org_settings
        org_id = current_user.get("organization_id") or "default"
        try:
            settings = await get_org_settings(org_id)
            gateway = get_invoicing_gateway(settings)
            po_data = await get_po(po_id, org_id)
            if po_data:
                await gateway.sync_po_receipt(po_data, result["cost_total"], settings)
        except Exception as e:
            logger.warning("Xero PO receipt sync failed: %s", e)
    return result
