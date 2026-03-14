"""Purchase order API routes."""

import logging

from fastapi import APIRouter, HTTPException, Request

from catalog.application.queries import (
    find_product_by_name_and_vendor,
    find_vendor_by_name,
    find_vendor_item_by_vendor_and_sku_code,
    get_department_by_code,
    get_sku_by_id,
    insert_vendor,
    list_departments,
    update_sku,
)
from catalog.application.sku_lifecycle import create_product_with_sku as lifecycle_create
from catalog.application.vendor_item_lifecycle import add_vendor_item
from documents.application.enrichment_service import enrich_for_import
from documents.application.import_parser import infer_uom, suggest_department
from finance.application.po_sync_service import queue_po_for_sync
from inventory.application.inventory_service import process_receiving_stock_changes
from inventory.application.uom_classifier import classify_uom_batch as _classify_uom_batch
from purchasing.application.purchase_order_service import (
    PurchasingDeps,
    create_purchase_order,
    mark_delivery_received,
    receive_po_items,
)
from purchasing.application.queries import get_po, get_po_items, list_pos
from purchasing.domain.purchase_order import (
    CreatePORequest,
    MarkDeliveryRequest,
    ReceiveItemsRequest,
)
from shared.api.deps import AdminDep
from shared.infrastructure.config import ANTHROPIC_AVAILABLE as _LLM_AVAILABLE
from shared.infrastructure.middleware.audit import audit_log

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
        get_sku_by_id=get_sku_by_id,
        find_vendor_item_by_vendor_and_sku_code=find_vendor_item_by_vendor_and_sku_code,
        find_sku_by_name_and_vendor=find_product_by_name_and_vendor,
        update_sku=update_sku,
        create_product_with_sku=lambda **kw: lifecycle_create(
            **kw, on_stock_import=process_receiving_stock_changes
        ),
        add_vendor_item=add_vendor_item,
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
    request: Request,
    current_user: AdminDep,
):
    """Save reviewed receipt items as a pending purchase order (no inventory update)."""
    result = await create_purchase_order(
        vendor_name=data.vendor_name,
        products=data.products,
        deps=_build_deps(),
        current_user=current_user,
        document_date=data.document_date,
        total=data.total,
        category_id=data.category_id,
        create_vendor_if_missing=data.create_vendor_if_missing,
    )
    await audit_log(
        user_id=current_user.id,
        action="po.create",
        resource_type="purchase_order",
        resource_id=result.id,
        details={"vendor": data.vendor_name, "item_count": len(data.products)},
        request=request,
        org_id=current_user.organization_id,
    )
    return result


@router.get("")
async def list_purchase_orders(
    current_user: AdminDep,
    status: str | None = None,
):
    """List purchase orders, optionally filtered by status (ordered/received)."""
    pos = await list_pos(status=status)
    result = []
    for po in pos:
        items = await get_po_items(po.id)
        result.append(
            po.model_copy(
                update={
                    "item_count": len(items),
                    "ordered_count": sum(1 for i in items if i.status == "ordered"),
                    "pending_count": sum(1 for i in items if i.status == "pending"),
                    "arrived_count": sum(1 for i in items if i.status == "arrived"),
                }
            )
        )
    return result


@router.get("/{po_id}")
async def get_purchase_order(
    po_id: str,
    current_user: AdminDep,
):
    """Get a purchase order with all its items."""
    po = await get_po(po_id)
    if not po:
        raise HTTPException(status_code=404, detail=f"Purchase order not found: {po_id}")
    items = await get_po_items(po_id)
    return po.model_copy(update={"items": items})


@router.post("/{po_id}/delivery")
async def mark_delivery(
    po_id: str,
    data: MarkDeliveryRequest,
    current_user: AdminDep,
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
    request: Request,
    current_user: AdminDep,
):
    """Mark selected items as arrived and update inventory stock."""
    result = await receive_po_items(
        po_id=po_id,
        item_updates=data.items,
        deps=_build_deps(),
        current_user=current_user,
    )
    await audit_log(
        user_id=current_user.id,
        action="po.receive",
        resource_type="purchase_order",
        resource_id=po_id,
        details={
            "received": result.received,
            "matched": result.matched,
            "cost_total": result.cost_total,
        },
        request=request,
        org_id=current_user.organization_id,
    )
    if result.cost_total > 0:
        try:
            await queue_po_for_sync(po_id)
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning("Failed to queue PO %s for Xero sync: %s", po_id, e)
    return result
