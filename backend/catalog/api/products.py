"""Product CRUD and CSV import routes."""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from identity.application.auth_service import get_current_user, require_role
from kernel.errors import ResourceNotFoundError
from catalog.domain.errors import DuplicateBarcodeError, InvalidBarcodeError
from catalog.domain.product import Product, ProductCreate, ProductUpdate
from catalog.infrastructure.department_repo import department_repo
from catalog.infrastructure.product_repo import product_repo
from catalog.infrastructure.vendor_repo import vendor_repo
from catalog.application.product_lifecycle import create_product as lifecycle_create, delete_product as lifecycle_delete, update_product as lifecycle_update
from catalog.application.csv_import_service import import_csv
from inventory.application.uom_classifier import classify_uom
from inventory.application.inventory_service import process_import_stock_changes
from shared.infrastructure.config import LLM_AVAILABLE

from catalog.api.schemas import SuggestUomRequest

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


@router.post("/suggest-uom")
async def suggest_uom(data: SuggestUomRequest, current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    """Use AI to suggest base_unit, sell_uom, pack_qty from product name."""
    gen_text = None
    if LLM_AVAILABLE:
        from assistant.application.llm import generate_text
        gen_text = generate_text
    result = await classify_uom(data.name, data.description, generate_text=gen_text)
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
            on_stock_import=process_import_stock_changes,
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

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    try:
        return await import_csv(
            content=content,
            department_id=department_id,
            vendor_id=vendor_id,
            user_id=current_user["id"],
            user_name=current_user.get("name", ""),
            organization_id=org_id,
            on_stock_import=process_import_stock_changes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
