"""Document parse/import routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from assistant.application.llm import generate_text as _generate_text
from catalog.application.product_lifecycle import create_product as lifecycle_create
from catalog.application.queries import (
    find_product_by_name_and_vendor,
    find_product_by_original_sku_and_vendor,
    find_vendor_by_name,
    get_department_by_code,
    get_product_by_id,
    insert_vendor,
    list_departments,
    list_products_by_vendor,
    update_product,
)
from documents.application.import_parser import infer_uom as rule_infer_uom
from documents.application.import_service import ImportDeps
from documents.application.import_service import import_document as do_import_document
from documents.application.parse_service import parse_document_with_ai
from documents.application.queries import get_document_by_id
from documents.application.queries import list_documents as query_list_documents
from documents.domain.document import DocumentImportRequest
from inventory.application.inventory_service import process_receiving_stock_changes
from inventory.application.uom_classifier import classify_uom_batch as _classify_uom_batch
from shared.api.deps import AdminDep
from shared.infrastructure.config import LLM_AVAILABLE as _LLM_AVAILABLE
from shared.kernel.barcode import validate_barcode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/parse")
async def parse_document(
    file: Annotated[UploadFile, File(...)],
    current_user: AdminDep,
    use_ai: bool = False,
):
    """Parse image or PDF. use_ai=true uses Claude (requires ANTHROPIC_API_KEY); default uses free OCR."""
    contents = await file.read()
    content_type = (file.content_type or "").lower()
    filename = file.filename or ""

    if not use_ai:
        raise HTTPException(
            status_code=501,
            detail="OCR parsing is not available. Use use_ai=true with an Anthropic API key.",
        )

    try:
        return await parse_document_with_ai(contents, content_type, filename, current_user)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        detail = str(e)
        if "no content" in detail.lower():
            raise HTTPException(status_code=500, detail=detail) from e
        raise HTTPException(status_code=400, detail=detail) from e
    except Exception as e:
        logger.exception("Document parse error")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("")
async def list_documents(
    current_user: AdminDep,
    status: str | None = None,
    vendor_name: str | None = None,
    po_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List uploaded/parsed documents."""
    return await query_list_documents(
        status=status,
        vendor_name=vendor_name,
        po_id=po_id,
        limit=limit,
        offset=offset,
    )


@router.get("/{doc_id}")
async def get_document(doc_id: str, current_user: AdminDep):
    doc = await get_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


async def _wired_classify_uom_batch(products):
    """Wire LLM + rule-based deps into the UOM classifier."""
    gen_text = _generate_text if _LLM_AVAILABLE else None
    return await _classify_uom_batch(products, generate_text=gen_text, rule_infer=rule_infer_uom)


@router.post("/import")
async def import_document(
    data: DocumentImportRequest,
    current_user: AdminDep,
):
    """Import parsed products; create or match vendor."""
    deps = ImportDeps(
        list_departments=list_departments,
        get_department_by_code=get_department_by_code,
        find_vendor_by_name=find_vendor_by_name,
        insert_vendor=insert_vendor,
        list_products_by_vendor=list_products_by_vendor,
        get_product_by_id=get_product_by_id,
        find_product_by_sku_and_vendor=find_product_by_original_sku_and_vendor,
        find_product_by_name_and_vendor=find_product_by_name_and_vendor,
        update_product=update_product,
        validate_barcode=validate_barcode,
        create_product=lambda **kw: lifecycle_create(
            **kw, on_stock_import=process_receiving_stock_changes
        ),
        process_receiving_stock_changes=process_receiving_stock_changes,
        classify_uom_batch=_wired_classify_uom_batch,
    )
    try:
        return await do_import_document(
            vendor_name=data.vendor_name,
            products=data.products,
            deps=deps,
            department_id=data.department_id,
            create_vendor_if_missing=data.create_vendor_if_missing,
            current_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Document import failed")
        raise HTTPException(
            status_code=500, detail="Import failed — please check the file and try again"
        ) from e
