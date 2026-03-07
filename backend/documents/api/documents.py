"""Document parse/import routes."""
import asyncio
import json
import logging
import os
import re
import tempfile
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

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
from catalog.domain.barcode import validate_barcode
from documents.application.import_parser import infer_uom as rule_infer_uom
from documents.application.import_service import ImportDeps
from documents.application.import_service import import_document as do_import_document
from documents.domain.document import Document, DocumentImportRequest
from documents.infrastructure.document_repo import document_repo
from inventory.application.inventory_service import process_receiving_stock_changes
from inventory.application.uom_classifier import classify_uom_batch as _classify_uom_batch
from kernel.types import CurrentUser
from shared.api.deps import ManagerDep
from shared.infrastructure.config import ANTHROPIC_AVAILABLE, LLM_SETUP_URL
from shared.infrastructure.config import LLM_AVAILABLE as _LLM_AVAILABLE
from shared.infrastructure.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

_PARSE_MAX_RETRIES = 2
_PARSE_RETRY_DELAYS = (5, 15)  # seconds on rate limit

_DOCUMENT_PARSE_SYSTEM = load_prompt(__file__, "document_parse_prompt.md")


async def _persist_parsed_document(extracted: dict, filename: str, content_type: str, file_size: int, current_user: CurrentUser) -> dict:
    """Save parsed document to the archive and return the extracted data with document_id."""
    import hashlib
    doc = Document(
        filename=filename,
        document_type="other",
        vendor_name=extracted.get("vendor_name"),
        file_hash=hashlib.sha256(filename.encode()).hexdigest()[:16],
        file_size=file_size,
        mime_type=content_type,
        parsed_data=json.dumps(extracted),
        status="parsed",
        uploaded_by_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    try:
        await document_repo.insert(doc)
        extracted["document_id"] = doc.id
    except (RuntimeError, OSError, ValueError) as e:
        logger.warning("Failed to persist document record: %s", e)
    return extracted


@router.post("/parse")
async def parse_document(
    file: Annotated[UploadFile, File(...)],
    current_user: ManagerDep,
    use_ai: bool = False,
):
    """Parse image or PDF. use_ai=true uses Claude (requires ANTHROPIC_API_KEY); default uses free OCR."""
    contents = await file.read()
    content_type = (file.content_type or "").lower()
    filename = file.filename or ""

    if not use_ai:
        try:
            from documents.application.ocr_service import extract_from_document
            extracted = await asyncio.to_thread(
                extract_from_document, contents, content_type, filename
            )
            for p in extracted.get("products", []):
                qty = p.get("quantity", 1)
                if "ordered_qty" not in p or p["ordered_qty"] is None:
                    p["ordered_qty"] = qty
                if "delivered_qty" not in p or p["delivered_qty"] is None:
                    p["delivered_qty"] = qty
            return await _persist_parsed_document(extracted, filename, content_type, len(contents), current_user)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.exception("OCR parse error")
            raise HTTPException(status_code=500, detail=str(e)) from e

    if not ANTHROPIC_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"AI not configured. Add ANTHROPIC_API_KEY to backend/.env — get a key at {LLM_SETUP_URL}",
        )

    try:
        is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")

        def _do_parse():
            if is_pdf:
                from assistant.application.llm import generate_with_pdf
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
                    tf.write(contents)
                    temp_path = tf.name
                try:
                    return generate_with_pdf(
                        "Extract all product and vendor information. Return only valid JSON.",
                        temp_path,
                        system_instruction=_DOCUMENT_PARSE_SYSTEM,
                    )
                finally:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
            else:
                from assistant.application.llm import generate_with_image
                return generate_with_image(
                    "Extract all product and vendor information. Return only valid JSON.",
                    contents,
                    system_instruction=_DOCUMENT_PARSE_SYSTEM,
                )

        response = None
        for attempt in range(_PARSE_MAX_RETRIES + 1):
            try:
                response = await asyncio.to_thread(_do_parse)
                break
            except ValueError as e:
                if "rate limit" in str(e).lower() and attempt < _PARSE_MAX_RETRIES:
                    delay = _PARSE_RETRY_DELAYS[attempt]
                    logger.info("Rate limit, retrying in %ss (attempt %d)", delay, attempt + 1)
                    await asyncio.sleep(delay)
                else:
                    raise

        if not response or not str(response).strip():
            raise HTTPException(status_code=500, detail="Claude returned no content. The document may be unreadable or blocked.")

        json_match = re.search(r"\{[\s\S]*\}", response)
        extracted = json.loads(json_match.group()) if json_match else json.loads(response)

        for p in extracted.get("products", []):
            qty = p.get("quantity", 1)
            # Backfill PO fields from quantity (schema no longer asks LLM for these)
            p.setdefault("ordered_qty", qty)
            p.setdefault("delivered_qty", qty)
            if p["ordered_qty"] is None:
                p["ordered_qty"] = qty
            if p["delivered_qty"] is None:
                p["delivered_qty"] = qty
            # Signal downstream: skip redundant LLM re-enrichment
            p["_ai_parsed"] = True

        return await _persist_parsed_document(extracted, filename, content_type, len(contents), current_user)
    except json.JSONDecodeError as e:
        logger.exception("Document parse JSON error")
        raise HTTPException(status_code=422, detail="Could not parse document data") from e
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Document parse: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Document parse error")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("")
async def list_documents(
    current_user: ManagerDep,
    status: str | None = None,
    vendor_name: str | None = None,
    po_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List uploaded/parsed documents."""
    return await document_repo.list_documents(
        organization_id=current_user.organization_id,
        status=status, vendor_name=vendor_name, po_id=po_id,
        limit=limit, offset=offset,
    )


@router.get("/{doc_id}")
async def get_document(doc_id: str, current_user: ManagerDep):
    doc = await document_repo.get_by_id(doc_id, current_user.organization_id)
    if not doc:
        from fastapi import HTTPException as _E
        raise _E(status_code=404, detail="Document not found")
    return doc


async def _wired_classify_uom_batch(products):
    """Wire LLM + rule-based deps into the UOM classifier."""
    gen_text = None
    if _LLM_AVAILABLE:
        from assistant.application.llm import generate_text
        gen_text = generate_text
    return await _classify_uom_batch(products, generate_text=gen_text, rule_infer=rule_infer_uom)


@router.post("/import")
async def import_document(
    data: DocumentImportRequest,
    current_user: ManagerDep,
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
        create_product=lambda **kw: lifecycle_create(**kw, on_stock_import=process_receiving_stock_changes),
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
        raise HTTPException(status_code=500, detail="Import failed — please check the file and try again") from e
