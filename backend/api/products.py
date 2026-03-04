"""Product CRUD, stock history, and CSV import routes."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from identity.application.auth_service import get_current_user, require_role
from catalog.domain.barcode import validate_barcode
from shared.domain.exceptions import DuplicateBarcodeError, InvalidBarcodeError, ResourceNotFoundError
from models import Product, ProductCreate, ProductUpdate
from repositories import department_repo, product_repo, vendor_repo
from services.inventory import get_stock_history
from services.product_lifecycle import create_product as lifecycle_create, delete_product as lifecycle_delete, update_product as lifecycle_update
from services.uom_classifier import classify_uom, classify_uom_batch
from services.document_import import infer_uom, parse_csv_products, suggest_department

from .schemas import SuggestUomRequest

router = APIRouter(prefix="/products", tags=["products"])


@router.get("")
async def get_products(
    department_id: Optional[str] = None,
    search: Optional[str] = None,
    low_stock: bool = False,
    limit: Optional[int] = None,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    org_id = current_user.get("organization_id") or "default"
    items = await product_repo.list_products(
        department_id=department_id,
        search=search,
        low_stock=low_stock,
        limit=limit,
        offset=offset,
        organization_id=org_id,
    )
    if limit is not None:
        total = await product_repo.count_products(
            department_id=department_id,
            search=search,
            low_stock=low_stock,
            organization_id=org_id,
        )
        return {"items": items, "total": total}
    return items


@router.get("/by-barcode")
async def get_product_by_barcode(barcode: str, current_user: dict = Depends(get_current_user)):
    """Look up product by barcode (for POS/request scan)."""
    org_id = current_user.get("organization_id") or "default"
    product = await product_repo.find_by_barcode(barcode.strip(), organization_id=org_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/{product_id}", response_model=Product)
async def get_product(product_id: str, current_user: dict = Depends(get_current_user)):
    org_id = current_user.get("organization_id") or "default"
    product = await product_repo.get_by_id(product_id, organization_id=org_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/{product_id}/stock-history")
async def get_product_stock_history(
    product_id: str,
    limit: int = 50,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Get stock transaction history for a product (stock ledger)."""
    org_id = current_user.get("organization_id") or "default"
    product = await product_repo.get_by_id(product_id, organization_id=org_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    history = await get_stock_history(product_id=product_id, limit=limit)
    return {"product_id": product_id, "sku": product.get("sku"), "history": history}


@router.post("/suggest-uom")
async def suggest_uom(data: SuggestUomRequest, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    """Use AI to suggest base_unit, sell_uom, pack_qty from product name."""
    result = await classify_uom(data.name, data.description)
    return result


@router.post("", response_model=Product)
async def create_product(data: ProductCreate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    org_id = current_user.get("organization_id") or "default"
    department = await department_repo.get_by_id(data.department_id, org_id)
    if not department:
        raise HTTPException(status_code=400, detail="Department not found")

    vendor_name = ""
    if data.vendor_id:
        vendor = await vendor_repo.get_by_id(data.vendor_id, org_id)
        if vendor:
            vendor_name = vendor.get("name", "")

    try:
        product = await lifecycle_create(
            department_id=data.department_id,
            department_name=department["name"],
            name=data.name,
            description=data.description or "",
            price=data.price,
            cost=data.cost,
            quantity=data.quantity,
            min_stock=data.min_stock,
            vendor_id=data.vendor_id,
            vendor_name=vendor_name,
            original_sku=data.original_sku,
            barcode=data.barcode,
            base_unit=getattr(data, "base_unit", "each"),
            sell_uom=getattr(data, "sell_uom", "each"),
            pack_qty=getattr(data, "pack_qty", 1),
            user_id=current_user["id"],
            user_name=current_user.get("name", ""),
            organization_id=org_id,
        )
        return product
    except DuplicateBarcodeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except InvalidBarcodeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{product_id}", response_model=Product)
async def update_product(product_id: str, data: ProductUpdate, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    org_id = current_user.get("organization_id") or "default"
    product = await product_repo.get_by_id(product_id, organization_id=org_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    try:
        result = await lifecycle_update(product_id, update_data, current_product=product)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateBarcodeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except InvalidBarcodeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.delete("/{product_id}")
async def delete_product(product_id: str, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    org_id = current_user.get("organization_id") or "default"
    product = await product_repo.get_by_id(product_id, organization_id=org_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        await lifecycle_delete(product_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "Product deleted"}


@router.post("/import-csv")
async def import_products_csv(
    file: UploadFile = File(...),
    department_id: str = Form(...),
    vendor_id: Optional[str] = Form(None),
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Bulk import products from a Supply Yard-style CSV."""
    org_id = current_user.get("organization_id") or "default"
    department = await department_repo.get_by_id(department_id, org_id)
    if not department:
        raise HTTPException(status_code=400, detail="Department not found")

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    try:
        rows = parse_csv_products(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not rows:
        raise HTTPException(status_code=400, detail="No valid product rows found in CSV")

    vendor_name = ""
    if vendor_id:
        vendor = await vendor_repo.get_by_id(vendor_id, org_id)
        if vendor:
            vendor_name = vendor.get("name", "")

    all_depts = await department_repo.list_all(org_id)
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
                user_id=current_user["id"],
                user_name=current_user.get("name", ""),
                organization_id=org_id,
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
