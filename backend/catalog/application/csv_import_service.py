"""Catalog CSV import service — extracts CSV import business logic from the API layer."""
from typing import Optional

from catalog.domain.barcode import validate_barcode
from catalog.infrastructure.department_repo import department_repo
from catalog.infrastructure.vendor_repo import vendor_repo
from catalog.application.product_lifecycle import create_product as lifecycle_create
from documents.application.import_parser import infer_uom, parse_csv_products, suggest_department


async def import_csv(
    content: bytes,
    department_id: str,
    vendor_id: Optional[str],
    user_id: str,
    user_name: str,
    organization_id: str,
) -> dict:
    """
    Parse CSV content and import products. Returns summary dict with
    imported/errors/warnings/products/error_details keys.
    """
    rows = parse_csv_products(content)
    if not rows:
        raise ValueError("No valid product rows found in CSV")

    department = await department_repo.get_by_id(department_id, organization_id)
    if not department:
        raise ValueError("Department not found")

    vendor_name = ""
    if vendor_id:
        vendor = await vendor_repo.get_by_id(vendor_id, organization_id)
        if vendor:
            vendor_name = vendor.get("name", "")

    all_depts = await department_repo.list_all(organization_id)
    dept_cache = {department["code"]: department, department["id"]: department}
    dept_by_code = {d["code"]: d for d in all_depts}
    for d in all_depts:
        dept_cache[d["code"]] = d
        dept_cache[d["name"].lower()] = d

    imported = []
    errors = []
    warnings = []

    for item in rows:
        try:
            dept = department
            if item.get("department"):
                raw = item["department"].strip()
                key = raw.upper()[:3] if len(raw) >= 3 else raw.lower()
                dept = dept_cache.get(key) or dept_cache.get(raw.lower()) or department
            else:
                suggested_code = suggest_department(item["name"], dept_by_code)
                if suggested_code:
                    dept = dept_by_code.get(suggested_code) or department

            bu, su, pq = infer_uom(item["name"])

            barcode_val = item.get("barcode")
            if barcode_val and str(barcode_val).strip():
                barcode_val = str(barcode_val).strip()
                if barcode_val.isdigit():
                    valid, _ = validate_barcode(barcode_val)
                    if not valid:
                        warnings.append({
                            "product": item["name"],
                            "warning": "Invalid UPC/EAN barcode; using SKU",
                        })
                        barcode_val = None
            else:
                barcode_val = None

            product = await lifecycle_create(
                department_id=dept["id"],
                department_name=dept["name"],
                name=item["name"],
                description="",
                price=item["price"],
                cost=item["cost"],
                quantity=item["quantity"],
                min_stock=item["min_stock"],
                vendor_id=vendor_id,
                vendor_name=vendor_name,
                original_sku=item.get("original_sku"),
                barcode=barcode_val,
                base_unit=bu,
                sell_uom=su,
                pack_qty=pq,
                user_id=user_id,
                user_name=user_name,
                organization_id=organization_id,
            )
            imported.append({"id": product.id, "sku": product.sku, "name": product.name, "quantity": product.quantity})
        except Exception as e:
            errors.append({"product": item["name"], "error": str(e)})

    return {
        "imported": len(imported),
        "errors": len(errors),
        "warnings": warnings,
        "products": imported,
        "error_details": errors[:20],
    }
