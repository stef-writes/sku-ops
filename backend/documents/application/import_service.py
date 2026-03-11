"""Document import service: vendor lookup/create, product match/create, inventory updates."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from documents.application.enrichment_service import enrich_for_import
from documents.application.import_parser import infer_uom, resolve_uom, suggest_department
from documents.domain.document import DocumentLineItem
from kernel.errors import ResourceNotFoundError
from kernel.types import CurrentUser
from shared.kernel.units import ALLOWED_BASE_UNITS


@dataclass
class ImportDeps:
    """Cross-domain dependencies injected by the API layer."""

    list_departments: Callable[..., Awaitable[list]]
    get_department_by_code: Callable[..., Awaitable[Any]]
    find_vendor_by_name: Callable[..., Awaitable[Any]]
    insert_vendor: Callable[..., Awaitable[None]]
    list_products_by_vendor: Callable[..., Awaitable[list]]
    get_product_by_id: Callable[..., Awaitable[Any]]
    find_product_by_sku_and_vendor: Callable[..., Awaitable[Any]]
    find_product_by_name_and_vendor: Callable[..., Awaitable[Any]]
    update_product: Callable[..., Awaitable[Any]]
    validate_barcode: Callable[..., Any]
    create_product: Callable[..., Awaitable[Any]]
    process_receiving_stock_changes: Callable[..., Awaitable[None]]
    classify_uom_batch: Callable[..., Awaitable[list]]


async def import_document(
    vendor_name: str,
    products: list[DocumentLineItem],
    deps: ImportDeps,
    current_user: CurrentUser,
    department_id: str | None = None,
    create_vendor_if_missing: bool = True,
) -> dict:
    """Import parsed products; create or match vendor, add/receive inventory."""
    vendor_name = (vendor_name or "").strip()
    if not vendor_name:
        raise ValueError("Vendor name is required")

    org_id = current_user.organization_id

    vendor = await deps.find_vendor_by_name(vendor_name, org_id)
    if not vendor:
        if not create_vendor_if_missing:
            raise ResourceNotFoundError("Vendor", vendor_name)
        vendor_id = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        await deps.insert_vendor(
            {
                "id": vendor_id,
                "name": vendor_name,
                "contact_name": "",
                "email": "",
                "phone": "",
                "address": "",
                "product_count": 0,
                "created_at": now,
                "organization_id": org_id,
            }
        )
        vendor_created = True
    else:
        vendor_id = vendor.id
        vendor_name = vendor.name
        vendor_created = False

    departments = await deps.list_departments(organization_id=org_id)
    default_dept = await deps.get_department_by_code("HDW", organization_id=org_id) or (
        departments[0] if departments else None
    )
    dept_by_id = {d.id: d for d in departments}
    dept_by_code = {d.code.upper(): d for d in departments}
    dept_codes = list(dept_by_code.keys())

    selected = [p for p in products if p.selected]
    selected_dicts = [p.model_dump() for p in selected]

    ai_parsed_items = [d for d in selected_dicts if d.get("ai_parsed")]
    ocr_items = [d for d in selected_dicts if not d.get("ai_parsed")]

    enrichment_warnings = []
    if ocr_items:
        vendor_products = await deps.list_products_by_vendor(vendor_id)
        ocr_items = await enrich_for_import(ocr_items, vendor_products, dept_codes)
        enrichment_warnings = [
            {"product": item.get("name", "Unknown"), "warning": item.pop("enrichment_warning")}
            for item in ocr_items
            if item.get("enrichment_warning")
        ]

    selected_dicts = ai_parsed_items + ocr_items

    for item in selected_dicts:
        suggested = (item.get("suggested_department") or "HDW").upper()
        if not suggested or suggested == "HDW" or suggested not in dept_by_code:
            rule_dept = suggest_department(item.get("name", "") or "", dept_by_code)
            if rule_dept:
                item["suggested_department"] = rule_dept

    for item in selected_dicts:
        bu = (item.get("base_unit") or "each").lower()
        su = (item.get("sell_uom") or "each").lower()
        if bu == "each" and su == "each":
            inferred_bu, inferred_su, inferred_pq = infer_uom(item.get("name", "") or "")
            if inferred_bu != "each":
                item["base_unit"] = inferred_bu
                item["sell_uom"] = inferred_su
                item["pack_qty"] = inferred_pq

    needs_uom = [
        d
        for d in selected_dicts
        if not d.get("ai_parsed")
        and (
            (d.get("base_unit") or "").lower() not in ALLOWED_BASE_UNITS
            or (d.get("sell_uom") or "").lower() not in ALLOWED_BASE_UNITS
        )
    ]
    if needs_uom:
        await deps.classify_uom_batch(needs_uom)

    imported = []
    matched = []
    errors = []
    warnings = list(enrichment_warnings)
    for item in selected_dicts:
        try:
            delivered = item.get("delivered_qty")
            if delivered is None:
                delivered = item.get("quantity", 1)
            delivered = max(0.0, float(delivered))

            existing = None
            if item.get("product_id"):
                existing = await deps.get_product_by_id(item["product_id"], organization_id=org_id)
            if not existing and item.get("original_sku") and vendor_id:
                existing = await deps.find_product_by_sku_and_vendor(
                    str(item["original_sku"]).strip(), vendor_id, organization_id=org_id
                )
            if not existing and item.get("name") and vendor_id:
                existing = await deps.find_product_by_name_and_vendor(
                    item["name"], vendor_id, organization_id=org_id
                )

            if existing:
                await deps.process_receiving_stock_changes(
                    product_id=existing.id,
                    sku=existing.sku,
                    product_name=existing.name,
                    quantity=delivered,
                    user_id=current_user.id,
                    user_name=current_user.name,
                    reference_id=None,
                    organization_id=org_id,
                )
                if item.get("original_sku") and not existing.original_sku:
                    await deps.update_product(existing.id, {"original_sku": item["original_sku"]})
                updated = await deps.get_product_by_id(existing.id)
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
            price_val = float(item.get("price") or 0) or (
                round(cost_val * 1.4, 2) if cost_val > 0 else 0.0
            )

            barcode_val = item.get("barcode")
            if barcode_val and str(barcode_val).strip():
                barcode_val = str(barcode_val).strip()
                if barcode_val.isdigit():
                    valid, _ = deps.validate_barcode(barcode_val)
                    if not valid:
                        warnings.append(
                            {
                                "product": item.get("name", "Unknown"),
                                "warning": "Invalid UPC/EAN barcode; using SKU",
                            }
                        )
                        barcode_val = None
            else:
                barcode_val = None

            product = await deps.create_product(
                department_id=dept.id,
                department_name=dept.name,
                name=item.get("name", "Unknown"),
                description=item.get("description", ""),
                price=round(price_val, 2),
                cost=round(cost_val, 2),
                quantity=delivered,
                min_stock=5,
                vendor_id=vendor_id,
                vendor_name=vendor_name,
                original_sku=item.get("original_sku"),
                barcode=barcode_val,
                base_unit=bu,
                sell_uom=su,
                pack_qty=pq,
                user_id=current_user.id,
                user_name=current_user.name,
                organization_id=org_id,
            )
            imported.append(product)
        except (ValueError, RuntimeError, OSError, KeyError) as e:
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
