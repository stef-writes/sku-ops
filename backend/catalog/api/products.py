"""Product CRUD routes."""

from fastapi import APIRouter, HTTPException, Query, Request

from assistant.application.llm import generate_text as _generate_text
from catalog.api.schemas import BulkGroupAssign, SuggestUomRequest
from catalog.application.product_lifecycle import (
    bulk_assign_product_group,
    rename_product_group,
)
from catalog.application.product_lifecycle import (
    create_product as lifecycle_create,
)
from catalog.application.product_lifecycle import (
    delete_product as lifecycle_delete,
)
from catalog.application.product_lifecycle import (
    update_product as lifecycle_update,
)
from catalog.application.queries import (
    count_products,
    find_product_by_barcode,
    get_department_by_id,
    get_product_by_id,
    get_vendor_by_id,
    list_product_groups,
    list_products,
)
from catalog.domain.errors import DuplicateBarcodeError, InvalidBarcodeError
from catalog.domain.product import ProductCreate, ProductUpdate
from inventory.application.inventory_service import process_import_stock_changes
from inventory.application.uom_classifier import classify_uom
from shared.api.deps import AdminDep, CurrentUserDep
from shared.infrastructure.config import LLM_AVAILABLE
from shared.infrastructure.middleware.audit import audit_log
from shared.kernel.barcode import validate_barcode
from shared.kernel.errors import ResourceNotFoundError
from shared.kernel.units import compute_sell_fields

router = APIRouter(prefix="/products", tags=["products"])

_CONTRACTOR_HIDDEN_FIELDS = {
    "cost",
    "sell_cost",
    "vendor_id",
    "vendor_name",
    "min_stock",
    "original_sku",
    "vendor_barcode",
    "pack_qty",
    "organization_id",
}


def _enrich_sell_fields(product: dict) -> dict:
    """Add pre-computed sell_price, sell_cost, sell_quantity for POS display."""
    product.update(
        compute_sell_fields(
            price=product.get("price", 0.0),
            cost=product.get("cost", 0.0),
            quantity=product.get("quantity", 0),
            base_unit=product.get("base_unit", "each"),
            sell_uom=product.get("sell_uom", "each"),
            pack_qty=product.get("pack_qty", 1),
        )
    )
    return product


def _strip_for_contractor(product: dict) -> dict:
    """Remove internal/cost fields that contractors must not see."""
    return {k: v for k, v in product.items() if k not in _CONTRACTOR_HIDDEN_FIELDS}


@router.get("")
async def get_products(
    current_user: CurrentUserDep,
    department_id: str | None = None,
    search: str | None = None,
    low_stock: bool = False,
    product_group: str | None = None,
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    is_contractor = current_user.role == "contractor"
    items = await list_products(
        department_id=department_id,
        search=search,
        low_stock=low_stock,
        limit=limit,
        offset=offset,
        product_group=product_group,
    )
    items = [_enrich_sell_fields(p) for p in items]
    if is_contractor:
        items = [_strip_for_contractor(p) for p in items]
    if limit is not None:
        total = await count_products(
            department_id=department_id,
            search=search,
            low_stock=low_stock,
            product_group=product_group,
        )
        return {"items": items, "total": total}
    return items


@router.get("/groups")
async def get_product_groups(current_user: AdminDep):
    """Return distinct product groups with counts and total stock."""
    return await list_product_groups()


@router.post("/groups/assign")
async def bulk_assign_group(data: BulkGroupAssign, current_user: AdminDep):
    """Assign or clear product_group for multiple products at once."""
    updated = await bulk_assign_product_group(
        product_ids=data.product_ids,
        product_group=data.product_group,
    )
    group_val = data.product_group.strip() if data.product_group else None
    return {"updated": updated, "product_group": group_val}


@router.post("/groups/rename")
async def rename_group(
    current_user: AdminDep,
    old_name: str = Query(...),
    new_name: str = Query(...),
):
    """Rename a product group across all products that have it."""
    try:
        updated = await rename_product_group(
            old_name=old_name,
            new_name=new_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"updated": updated, "old_name": old_name.strip(), "new_name": new_name.strip()}


@router.get("/by-barcode")
async def get_product_by_barcode(barcode: str, current_user: CurrentUserDep):
    """Look up product by barcode (for POS/request scan).

    Returns structured error detail so the UI can differentiate:
      - {"code": "invalid_check_digit", "barcode": "..."} — numeric input with bad check digit
      - {"code": "not_found", "barcode": "..."} — valid format but no match in DB
    """
    code = barcode.strip()

    if code.isdigit() and len(code) in (12, 13):
        valid, _ = validate_barcode(code)
        if not valid:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_check_digit", "barcode": code},
            )

    product = await find_product_by_barcode(code)
    if not product:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "barcode": code},
        )
    result = product.model_dump()
    _enrich_sell_fields(result)
    if current_user.role == "contractor":
        return _strip_for_contractor(result)
    return result


@router.get("/{product_id}", response_model=None)
async def get_product(product_id: str, current_user: CurrentUserDep):
    product = await get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    result = product.model_dump()
    _enrich_sell_fields(result)
    if current_user.role == "contractor":
        return _strip_for_contractor(result)
    return result


@router.post("/suggest-uom")
async def suggest_uom(data: SuggestUomRequest, _current_user: AdminDep):
    """Use AI to suggest base_unit, sell_uom, pack_qty from product name."""
    gen_text = _generate_text if LLM_AVAILABLE else None
    result = await classify_uom(data.name, data.description, generate_text=gen_text)
    return result


@router.post("")
async def create_product(data: ProductCreate, current_user: AdminDep):
    department = await get_department_by_id(data.department_id)
    if not department:
        raise HTTPException(status_code=400, detail="Department not found")

    vendor_name = ""
    if data.vendor_id:
        vendor = await get_vendor_by_id(data.vendor_id)
        if vendor:
            vendor_name = vendor.name

    try:
        product = await lifecycle_create(
            department_id=data.department_id,
            department_name=department.name,
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
            product_group=data.product_group,
            user_id=current_user.id,
            user_name=current_user.name,
            on_stock_import=process_import_stock_changes,
        )
        return _enrich_sell_fields(product.model_dump())
    except DuplicateBarcodeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except InvalidBarcodeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/{product_id}")
async def update_product(product_id: str, data: ProductUpdate, current_user: AdminDep):
    product = await get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    if "product_group" in data.model_fields_set and data.product_group is None:
        update_data["product_group"] = None
    try:
        result = await lifecycle_update(product_id, update_data, current_product=product)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DuplicateBarcodeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except InvalidBarcodeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _enrich_sell_fields(result.model_dump())


@router.delete("/{product_id}")
async def delete_product(product_id: str, request: Request, current_user: AdminDep):
    product = await get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        await lifecycle_delete(product_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await audit_log(
        user_id=current_user.id,
        action="product.delete",
        resource_type="product",
        resource_id=product_id,
        details={"sku": product.sku, "name": product.name},
        request=request,
        org_id=current_user.organization_id,
    )
    return {"message": "Product deleted"}
