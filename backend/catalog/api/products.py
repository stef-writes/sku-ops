"""SKU CRUD routes — /api/catalog/skus."""

from fastapi import APIRouter, HTTPException, Query, Request

from assistant.application.llm import generate_text as _generate_text
from catalog.api.schemas import SuggestUomRequest
from catalog.application.queries import (
    count_skus,
    find_sku_by_barcode,
    get_department_by_id,
    get_sku_by_id,
    list_skus,
)
from catalog.application.sku_lifecycle import (
    create_product_with_sku as lifecycle_create,
)
from catalog.application.sku_lifecycle import (
    delete_sku as lifecycle_delete,
)
from catalog.application.sku_lifecycle import (
    update_sku as lifecycle_update,
)
from catalog.domain.errors import DuplicateBarcodeError, InvalidBarcodeError
from catalog.domain.product import SkuCreate, SkuUpdate
from inventory.application.inventory_service import process_import_stock_changes
from inventory.application.uom_classifier import classify_uom
from shared.api.deps import AdminDep, CurrentUserDep
from shared.infrastructure.config import ANTHROPIC_AVAILABLE as LLM_AVAILABLE
from shared.infrastructure.middleware.audit import audit_log
from shared.kernel.barcode import validate_barcode
from shared.kernel.errors import ResourceNotFoundError
from shared.kernel.units import compute_sell_fields

router = APIRouter(prefix="/catalog/skus", tags=["catalog-skus"])

_CONTRACTOR_HIDDEN_FIELDS = {
    "cost",
    "sell_cost",
    "min_stock",
    "vendor_barcode",
    "pack_qty",
    "organization_id",
    "purchase_uom",
    "purchase_pack_qty",
}


def _enrich_sell_fields(sku: dict) -> dict:
    """Add pre-computed sell_price, sell_cost, sell_quantity for POS display."""
    sku.update(
        compute_sell_fields(
            price=sku.get("price", 0.0),
            cost=sku.get("cost", 0.0),
            quantity=sku.get("quantity", 0),
            base_unit=sku.get("base_unit", "each"),
            sell_uom=sku.get("sell_uom", "each"),
            pack_qty=sku.get("pack_qty", 1),
        )
    )
    return sku


def _strip_for_contractor(sku: dict) -> dict:
    """Remove internal/cost fields that contractors must not see."""
    return {k: v for k, v in sku.items() if k not in _CONTRACTOR_HIDDEN_FIELDS}


@router.get("")
async def get_products(
    current_user: CurrentUserDep,
    category_id: str | None = None,
    search: str | None = None,
    low_stock: bool = False,
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    is_contractor = current_user.role == "contractor"
    items = await list_skus(
        category_id=category_id,
        search=search,
        low_stock=low_stock,
        limit=limit,
        offset=offset,
    )
    items = [_enrich_sell_fields(p.model_dump()) for p in items]
    if is_contractor:
        items = [_strip_for_contractor(p) for p in items]
    if limit is not None:
        total = await count_skus(
            category_id=category_id,
            search=search,
            low_stock=low_stock,
        )
        return {"items": items, "total": total}
    return items


@router.get("/by-barcode")
async def get_product_by_barcode(barcode: str, current_user: CurrentUserDep):
    """Look up SKU by barcode (for POS/request scan)."""
    code = barcode.strip()

    if code.isdigit() and len(code) in (12, 13):
        valid, _ = validate_barcode(code)
        if not valid:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_check_digit", "barcode": code},
            )

    sku = await find_sku_by_barcode(code)
    if not sku:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "barcode": code},
        )
    result = sku.model_dump()
    _enrich_sell_fields(result)
    if current_user.role == "contractor":
        return _strip_for_contractor(result)
    return result


@router.get("/{product_id}", response_model=None)
async def get_product(product_id: str, current_user: CurrentUserDep):
    sku = await get_sku_by_id(product_id)
    if not sku:
        raise HTTPException(status_code=404, detail="Product not found")
    result = sku.model_dump()
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
async def create_product(data: SkuCreate, current_user: AdminDep):
    department = await get_department_by_id(data.category_id)
    if not department:
        raise HTTPException(status_code=400, detail="Department not found")

    try:
        sku = await lifecycle_create(
            category_id=data.category_id,
            category_name=department.name,
            name=data.name,
            description=data.description or "",
            price=data.price,
            cost=data.cost,
            quantity=data.quantity,
            min_stock=data.min_stock,
            barcode=data.barcode,
            base_unit=getattr(data, "base_unit", "each"),
            sell_uom=getattr(data, "sell_uom", "each"),
            pack_qty=getattr(data, "pack_qty", 1),
            purchase_uom=getattr(data, "purchase_uom", "each"),
            purchase_pack_qty=getattr(data, "purchase_pack_qty", 1),
            user_id=current_user.id,
            user_name=current_user.name,
            on_stock_import=process_import_stock_changes,
        )
        return _enrich_sell_fields(sku.model_dump())
    except DuplicateBarcodeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except InvalidBarcodeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/{product_id}")
async def update_product(product_id: str, data: SkuUpdate, current_user: AdminDep):
    sku = await get_sku_by_id(product_id)
    if not sku:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        result = await lifecycle_update(product_id, data, current_sku=sku)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except DuplicateBarcodeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except InvalidBarcodeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _enrich_sell_fields(result.model_dump())


@router.delete("/{product_id}")
async def delete_product(product_id: str, request: Request, current_user: AdminDep):
    sku = await get_sku_by_id(product_id)
    if not sku:
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
        details={"sku": sku.sku, "name": sku.name},
        request=request,
        org_id=current_user.organization_id,
    )
    return {"message": "Product deleted"}
