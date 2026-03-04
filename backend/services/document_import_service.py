"""
Document import service: vendor lookup/create, product match/create, inventory updates.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from catalog.domain.product import ALLOWED_BASE_UNITS
from repositories import department_repo, product_repo, vendor_repo
from services.document_import import infer_uom, resolve_uom, suggest_department
from services.document_enrichment import enrich_for_import
from inventory.application.inventory_service import process_receiving_stock_changes
from catalog.domain.barcode import validate_barcode
from catalog.application.product_lifecycle import create_product as lifecycle_create
from inventory.application.uom_classifier import classify_uom_batch


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
    dept_codes = list(dept_by_code.keys())

    selected = [p for p in products if p.get("selected", True)]

    # AI-parsed items already have dept/UOM/SKU from the document-aware parse LLM.
    # Running a second (blind) LLM enrichment on them degrades quality — skip it.
    ai_parsed_items = [p for p in selected if p.get("_ai_parsed")]
    ocr_items = [p for p in selected if not p.get("_ai_parsed")]

    enrichment_warnings = []
    if ocr_items:
        vendor_products = await product_repo.list_by_vendor(vendor_id)
        ocr_items = await enrich_for_import(ocr_items, vendor_products, dept_codes)
        enrichment_warnings = [
            {"product": item.get("name", "Unknown"), "warning": item.pop("enrichment_warning")}
            for item in ocr_items
            if item.get("enrichment_warning")
        ]

    selected = ai_parsed_items + ocr_items

    for item in selected:
        suggested = (item.get("suggested_department") or "HDW").upper()
        if not suggested or suggested == "HDW" or suggested not in dept_by_code:
            rule_dept = suggest_department(item.get("name", "") or "", dept_by_code)
            if rule_dept:
                item["suggested_department"] = rule_dept

    # Rule-based UOM upgrade: only for items where UOM is still "each" (OCR items / missed)
    for item in selected:
        bu = (item.get("base_unit") or "each").lower()
        su = (item.get("sell_uom") or "each").lower()
        if bu == "each" and su == "each":
            inferred_bu, inferred_su, inferred_pq = infer_uom(item.get("name", "") or "")
            if inferred_bu != "each":
                item["base_unit"] = inferred_bu
                item["sell_uom"] = inferred_su
                item["pack_qty"] = inferred_pq

    # LLM UOM classifier: only for OCR items with invalid/missing UOM (AI parse already classified)
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

    org_id = (current_user or {}).get("organization_id") or "default"
    imported = []
    matched = []
    errors = []
    warnings = list(enrichment_warnings)
    for item in selected:
        try:
            delivered = item.get("delivered_qty")
            if delivered is None:
                delivered = item.get("quantity", 1)
            delivered = max(0, int(delivered))

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
                    reference_id=None,
                )
                # Backfill original_sku so future imports match on SKU, not name
                if item.get("original_sku") and not existing.get("original_sku"):
                    await product_repo.update(existing["id"], {"original_sku": item["original_sku"]})
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
            # Default sell price = cost × 1.4 if no explicit price provided; editable in Inventory
            price_val = float(item.get("price") or 0) or (round(cost_val * 1.4, 2) if cost_val > 0 else 0.0)

            barcode_val = item.get("barcode")
            if barcode_val and str(barcode_val).strip():
                barcode_val = str(barcode_val).strip()
                if barcode_val.isdigit():
                    valid, _ = validate_barcode(barcode_val)
                    if not valid:
                        warnings.append({
                            "product": item.get("name", "Unknown"),
                            "warning": "Invalid UPC/EAN barcode; using SKU",
                        })
                        barcode_val = None
            else:
                barcode_val = None

            product = await lifecycle_create(
                department_id=dept["id"],
                department_name=dept["name"],
                name=item.get("name", "Unknown"),
                description=item.get("description", ""),
                price=round(price_val, 2),
                cost=round(cost_val, 2),
                quantity=delivered,
                min_stock=5,
                vendor_id=vendor_id,
                vendor_name=vendor.get("name", ""),
                original_sku=item.get("original_sku"),
                barcode=barcode_val,
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
        "warnings": warnings,
        "products": imported,
        "matched_products": matched,
        "error_details": errors,
    }
