"""
Document import service: vendor lookup/create, product match/create, inventory updates.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from models import Product
from models.product import ALLOWED_BASE_UNITS
from repositories import department_repo, product_repo, vendor_repo
from services.document_import import resolve_uom
from services.inventory import process_receiving_stock_changes
from services.product_lifecycle import create_product as lifecycle_create
from services.uom_classifier import classify_uom_batch


async def import_document(
    vendor_name: str,
    products: list,
    department_id: Optional[str] = None,
    create_vendor_if_missing: bool = True,
    current_user: dict = None,
) -> dict:
    """
    Import parsed products; create or match vendor, add/receive inventory.
    Returns summary with imported, matched, errors.
    """
    vendor_name = (vendor_name or "").strip()
    if not vendor_name:
        raise HTTPException(status_code=400, detail="Vendor name is required")

    vendor = await vendor_repo.find_by_name(vendor_name)
    if not vendor:
        if not create_vendor_if_missing:
            raise HTTPException(status_code=400, detail=f"Vendor '{vendor_name}' not found. Enable 'Create vendor if missing' or add vendor first.")
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
        })
        vendor = {"id": vendor_id, "name": vendor_name}
        vendor_created = True
    else:
        vendor_id = vendor["id"]
        vendor_created = False

    departments = await department_repo.list_all()
    default_dept = await department_repo.get_by_code("HDW") or (departments[0] if departments else None)
    dept_by_id = {d["id"]: d for d in departments}
    dept_by_code = {d["code"].upper(): d for d in departments}

    selected = [p for p in products if p.get("selected", True)]
    needs_uom = [p for p in selected if (p.get("base_unit") or "").lower() not in ALLOWED_BASE_UNITS or (p.get("sell_uom") or "").lower() not in ALLOWED_BASE_UNITS]
    if needs_uom:
        await classify_uom_batch(needs_uom)

    imported = []
    matched = []
    errors = []
    for item in selected:
        try:
            delivered = item.get("delivered_qty")
            if delivered is None:
                delivered = item.get("quantity", 1)
            delivered = max(0, int(delivered))

            existing = None
            if item.get("original_sku") and vendor_id:
                existing = await product_repo.find_by_original_sku_and_vendor(
                    str(item.get("original_sku")).strip(), vendor_id
                )
            if existing:
                await process_receiving_stock_changes(
                    product_id=existing["id"],
                    sku=existing["sku"],
                    product_name=existing["name"],
                    quantity=delivered,
                    user_id=current_user["id"],
                    user_name=current_user.get("name", ""),
                    reference_id=None,
                )
                updated = await product_repo.get_by_id(existing["id"])
                matched.append(updated)
                continue

            dept = None
            if department_id and department_id in dept_by_id:
                dept = dept_by_id[department_id]
            if not dept:
                code = (item.get("suggested_department") or "HDW").upper()
                dept = dept_by_code.get(code) or default_dept
            if not dept:
                errors.append({"product": item.get("name"), "error": "No valid department"})
                continue

            bu, su, pq = resolve_uom(item)
            cost_val = float(item.get("cost") or 0) or float(item.get("price", 0)) * 0.7

            product = await lifecycle_create(
                department_id=dept["id"],
                department_name=dept["name"],
                name=item.get("name", "Unknown"),
                description=item.get("description", ""),
                price=float(item.get("price", 0)),
                cost=round(cost_val, 2),
                quantity=delivered,
                min_stock=5,
                vendor_id=vendor_id,
                vendor_name=vendor.get("name", ""),
                original_sku=item.get("original_sku"),
                base_unit=bu,
                sell_uom=su,
                pack_qty=pq,
                user_id=current_user["id"],
                user_name=current_user.get("name", ""),
            )
            imported.append(product)
        except Exception as e:
            errors.append({"product": item.get("name"), "error": str(e)})

    return {
        "vendor_id": vendor_id,
        "vendor_created": vendor_created,
        "imported": len(imported),
        "matched": len(matched),
        "errors": len(errors),
        "products": imported,
        "matched_products": matched,
        "error_details": errors,
    }
