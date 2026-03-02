"""
Purchase order service: create pending POs and receive items into inventory.
Items are saved as pending when a document is reviewed; inventory only updates on receive.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from models.product import ALLOWED_BASE_UNITS
from repositories import department_repo, product_repo, vendor_repo
from repositories.po_repo import (
    create_po as _create_po,
    create_po_items,
    get_po,
    get_po_items,
    update_po_item,
    update_po_status,
)
from services.document_import import infer_uom, suggest_department
from services.document_enrichment import enrich_for_import
from services.inventory import process_receiving_stock_changes
from services.product_lifecycle import create_product as lifecycle_create
from services.uom_classifier import classify_uom_batch


async def create_purchase_order(
    vendor_name: str,
    products: list,
    document_date: Optional[str] = None,
    total: Optional[float] = None,
    department_id: Optional[str] = None,
    create_vendor_if_missing: bool = True,
    current_user: dict = None,
) -> dict:
    """
    Save reviewed receipt items as a pending purchase order.
    Runs enrichment (UOM inference, dept suggestion, LLM) but does NOT update inventory.
    """
    vendor_name = (vendor_name or "").strip()
    if not vendor_name:
        raise HTTPException(status_code=400, detail="Vendor name is required")

    org_id = (current_user or {}).get("organization_id") or "default"

    vendor = await vendor_repo.find_by_name(vendor_name, org_id)
    if not vendor:
        if not create_vendor_if_missing:
            raise HTTPException(
                status_code=400,
                detail=f"Vendor '{vendor_name}' not found. Enable 'Create vendor if missing' or add the vendor first.",
            )
        vendor_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        await vendor_repo.insert({
            "id": vendor_id,
            "name": vendor_name,
            "contact_name": "",
            "email": "",
            "phone": "",
            "address": "",
            "product_count": 0,
            "created_at": now,
            "organization_id": org_id,
        })
        vendor = {"id": vendor_id, "name": vendor_name}
        vendor_created = True
    else:
        vendor_id = vendor["id"]
        vendor_created = False

    departments = await department_repo.list_all()
    dept_by_id = {d["id"]: d for d in departments}
    dept_by_code = {d["code"].upper(): d for d in departments}
    dept_codes = list(dept_by_code.keys())

    # Resolve override department code (if user selected one on the import page)
    override_dept_code = None
    if department_id and department_id in dept_by_id:
        override_dept_code = dept_by_id[department_id]["code"].upper()

    selected = [p for p in products if p.get("selected", True)]

    # AI-parsed items already have dept/UOM/SKU from the document-aware parse LLM.
    # A second (blind) LLM enrichment degrades quality — only run it for OCR-parsed items.
    ai_parsed_items = [p for p in selected if p.get("_ai_parsed")]
    ocr_items = [p for p in selected if not p.get("_ai_parsed")]

    if ocr_items:
        vendor_products = await product_repo.list_by_vendor(vendor_id)
        ocr_items = await enrich_for_import(ocr_items, vendor_products, dept_codes)
    for item in selected:
        item.pop("enrichment_warning", None)

    selected = ai_parsed_items + ocr_items

    # Dept resolution: user override wins; then parse-LLM value; then rule-based fallback
    for item in selected:
        if override_dept_code:
            item["suggested_department"] = override_dept_code
        else:
            suggested = (item.get("suggested_department") or "HDW").upper()
            if not suggested or suggested == "HDW" or suggested not in dept_by_code:
                rule_dept = suggest_department(item.get("name", "") or "", dept_by_code)
                if rule_dept:
                    item["suggested_department"] = rule_dept

    # Rule-based UOM upgrade for items still at "each"
    for item in selected:
        bu = (item.get("base_unit") or "each").lower()
        su = (item.get("sell_uom") or "each").lower()
        if bu == "each" and su == "each":
            inferred_bu, inferred_su, inferred_pq = infer_uom(item.get("name", "") or "")
            if inferred_bu != "each":
                item["base_unit"] = inferred_bu
                item["sell_uom"] = inferred_su
                item["pack_qty"] = inferred_pq

    # LLM UOM classifier: only for OCR items with invalid UOM
    needs_uom = [
        p for p in selected
        if not p.get("_ai_parsed")
        and (
            (p.get("base_unit") or "").lower() not in ALLOWED_BASE_UNITS
            or (p.get("sell_uom") or "").lower() not in ALLOWED_BASE_UNITS
        )
    ]
    if needs_uom:
        await classify_uom_batch(needs_uom)

    po_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    po = {
        "id": po_id,
        "vendor_id": vendor_id,
        "vendor_name": vendor_name,
        "document_date": document_date,
        "total": total,
        "status": "pending",
        "notes": None,
        "created_by_id": (current_user or {}).get("id", ""),
        "created_by_name": (current_user or {}).get("name", ""),
        "received_at": None,
        "received_by_id": None,
        "received_by_name": None,
        "created_at": now,
        "organization_id": org_id,
    }
    await _create_po(po)

    items_to_create = []
    for item in selected:
        cost_val = float(item.get("cost") or 0) or float(item.get("price") or 0) * 0.7
        items_to_create.append({
            "id": uuid.uuid4().hex,
            "po_id": po_id,
            "name": item.get("name", "Unknown"),
            "original_sku": item.get("original_sku"),
            "ordered_qty": int(item.get("ordered_qty") or item.get("quantity") or 1),
            "delivered_qty": item.get("delivered_qty"),
            "price": float(item.get("price") or 0),
            "cost": round(cost_val, 2),
            "base_unit": item.get("base_unit") or "each",
            "sell_uom": item.get("sell_uom") or "each",
            "pack_qty": int(item.get("pack_qty") or 1),
            "suggested_department": (item.get("suggested_department") or "HDW").upper(),
            "status": "ordered",
            "product_id": item.get("product_id") or None,
            "organization_id": org_id,
        })
    await create_po_items(items_to_create)

    return {
        "id": po_id,
        "vendor_id": vendor_id,
        "vendor_created": vendor_created,
        "vendor_name": vendor_name,
        "status": "ordered",
        "item_count": len(items_to_create),
        "created_at": now,
    }


async def mark_delivery_received(
    po_id: str,
    item_ids: list,
    current_user: dict = None,
) -> dict:
    """
    Transition selected 'ordered' items to 'pending' (delivery arrived at dock).
    Does NOT update inventory — that happens on receive_po_items().
    """
    org_id = (current_user or {}).get("organization_id") or "default"
    po = await get_po(po_id, org_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    all_items = await get_po_items(po_id)
    items_by_id = {i["id"]: i for i in all_items}

    transitioned = 0
    for item_id in item_ids:
        item = items_by_id.get(item_id)
        if not item or item["status"] != "ordered":
            continue
        await update_po_item(item_id, status="pending")
        transitioned += 1

    # Update PO status
    all_items_after = await get_po_items(po_id)
    arrived = sum(1 for i in all_items_after if i["status"] == "arrived")
    pending = sum(1 for i in all_items_after if i["status"] == "pending")
    ordered = sum(1 for i in all_items_after if i["status"] == "ordered")

    if arrived > 0 and pending == 0 and ordered == 0:
        new_status = "received"
        now = datetime.now(timezone.utc).isoformat()
        await update_po_status(
            po_id, status="received",
            received_at=now,
            received_by_id=current_user.get("id"),
            received_by_name=current_user.get("name", ""),
        )
    elif arrived > 0:
        new_status = "partial"
        await update_po_status(po_id, status="partial")
    else:
        new_status = po["status"]
        if transitioned > 0 and new_status == "ordered":
            # Still ordered-level (some pending, but none arrived yet)
            await update_po_status(po_id, status="ordered")

    return {"po_id": po_id, "status": new_status, "transitioned": transitioned}


async def receive_po_items(
    po_id: str,
    item_updates: list,  # [{"id": item_id, "delivered_qty": qty}]
    current_user: dict = None,
) -> dict:
    """
    Mark selected items as arrived and update inventory stock.
    New products are created for unmatched items; existing products get a RECEIVING transaction.
    """
    org_id = (current_user or {}).get("organization_id") or "default"
    po = await get_po(po_id, org_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    vendor_id = po.get("vendor_id")
    departments = await department_repo.list_all()
    default_dept = await department_repo.get_by_code("HDW") or (departments[0] if departments else None)
    dept_by_code = {d["code"].upper(): d for d in departments}

    all_items = await get_po_items(po_id)
    items_by_id = {item["id"]: item for item in all_items}
    updates_by_id = {u["id"]: u for u in item_updates}

    received = []
    matched = []
    errors = []

    for item_id, update in updates_by_id.items():
        item = items_by_id.get(item_id)
        if not item:
            errors.append({"item_id": item_id, "error": "Item not found"})
            continue
        if item["status"] == "arrived":
            continue  # already received
        if item["status"] == "ordered":
            errors.append({"item": item.get("name"), "error": "Item not yet marked as received at dock"})
            continue

        delivered = update.get("delivered_qty")
        if delivered is None:
            delivered = item.get("delivered_qty") or item.get("ordered_qty") or 1
        delivered = max(0, int(delivered))

        try:
            # 3-tier matching: explicit product_id → vendor SKU → name
            existing = None
            if item.get("product_id"):
                existing = await product_repo.get_by_id(item["product_id"], organization_id=org_id)
            if not existing and item.get("original_sku") and vendor_id:
                existing = await product_repo.find_by_original_sku_and_vendor(
                    str(item["original_sku"]).strip(), vendor_id, organization_id=org_id
                )
            if not existing and item.get("name") and vendor_id:
                existing = await product_repo.find_by_name_and_vendor(
                    item["name"], vendor_id, organization_id=org_id
                )

            if existing:
                await process_receiving_stock_changes(
                    product_id=existing["id"],
                    sku=existing["sku"],
                    product_name=existing["name"],
                    quantity=delivered,
                    user_id=current_user["id"],
                    user_name=current_user.get("name", ""),
                    reference_id=po_id,
                )
                # Backfill original_sku on product so future imports match on SKU, not name
                if item.get("original_sku") and not existing.get("original_sku"):
                    await product_repo.update(existing["id"], {"original_sku": item["original_sku"]})
                await update_po_item(item_id, status="arrived", product_id=existing["id"], delivered_qty=delivered)
                updated = await product_repo.get_by_id(existing["id"])
                matched.append(updated)
            else:
                dept = dept_by_code.get((item.get("suggested_department") or "HDW").upper()) or default_dept
                if not dept:
                    errors.append({"item": item.get("name"), "error": "No valid department"})
                    continue

                cost_val = float(item.get("cost") or 0) or float(item.get("price") or 0) * 0.7
                product = await lifecycle_create(
                    department_id=dept["id"],
                    department_name=dept["name"],
                    name=item.get("name", "Unknown"),
                    description="",
                    price=float(item.get("price") or 0),
                    cost=round(cost_val, 2),
                    quantity=delivered,
                    min_stock=5,
                    vendor_id=vendor_id,
                    vendor_name=po.get("vendor_name", ""),
                    original_sku=item.get("original_sku"),
                    barcode=None,
                    base_unit=item.get("base_unit") or "each",
                    sell_uom=item.get("sell_uom") or "each",
                    pack_qty=int(item.get("pack_qty") or 1),
                    user_id=current_user["id"],
                    user_name=current_user.get("name", ""),
                    organization_id=org_id,
                )
                await update_po_item(item_id, status="arrived", product_id=product.id, delivered_qty=delivered)
                received.append(product)

        except Exception as e:
            errors.append({"item": item.get("name"), "error": str(e)})

    # Update PO status based on item states
    all_items_after = await get_po_items(po_id)
    ordered_count = sum(1 for i in all_items_after if i["status"] == "ordered")
    pending_count = sum(1 for i in all_items_after if i["status"] == "pending")
    arrived_count = sum(1 for i in all_items_after if i["status"] == "arrived")
    now = datetime.now(timezone.utc).isoformat()

    if arrived_count > 0 and pending_count == 0 and ordered_count == 0:
        new_status = "received"
        await update_po_status(
            po_id, status="received",
            received_at=now,
            received_by_id=current_user.get("id"),
            received_by_name=current_user.get("name", ""),
        )
    elif arrived_count > 0:
        new_status = "partial"
        await update_po_status(po_id, status="partial")
    else:
        new_status = po["status"]

    return {
        "po_id": po_id,
        "status": new_status,
        "received": len(received),
        "matched": len(matched),
        "errors": len(errors),
        "error_details": errors,
    }
