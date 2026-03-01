"""Document parse/import and chat assistant routes."""
import asyncio
import json
import logging
import os
import re
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from auth import get_current_user, require_role
from config import LLM_AVAILABLE, LLM_SETUP_URL
from services.document_import_service import import_document as do_import_document

from .schemas import DocumentImportRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Retry on rate limit: wait then retry (Gemini free tier ~60 req/min)
_PARSE_MAX_RETRIES = 2
_PARSE_RETRY_DELAYS = (5, 15)  # seconds

_DOCUMENT_PARSE_SYSTEM = """You are a document parser for a hardware store. Extract vendor/supplier name, document date, total, and line items from receipts, invoices, or packing slips.
Per item include: name, quantity, ordered_qty, delivered_qty, price, cost, original_sku, base_unit, sell_uom, pack_qty, suggested_department.

IMPORTANT - Infer UOM from product names; do NOT default everything to "each". Allowed UOM: each, case, box, pack, bag, roll, kit, gallon, quart, pint, liter, pound, ounce, foot, meter, yard, sqft.
Examples: "5 Gal Paint" -> gallon/gallon/5; "2x4x8 Stud" -> foot/foot/8; "1/2 PEX Pipe 100ft" -> foot/foot/100; "Screw Box 100" -> box/box/1; "Wire 12/2 250ft" -> foot/foot/250; "Drywall 4x8" -> sqft/sqft/1; "Caulk Tube" -> each/each/1; "Concrete 80lb" -> pound/pound/1; "Duct Tape" -> roll/roll/1.
Use "each" only for single items like faucets, light fixtures, or when the name gives no UOM clue.

Use EFFECTIVE price after discounts. When ordered/delivered unclear, set both to quantity.
Suggested department codes: PLU, ELE, PNT, LUM, TOL, HDW, GDN, APP.
Return ONLY valid JSON: {"vendor_name": "...", "document_date": "YYYY-MM-DD", "total": N, "products": [{"name": "...", "quantity": 1, "ordered_qty": 1, "delivered_qty": 1, "price": 9.99, "cost": 7.99, "original_sku": "...", "base_unit": "gallon", "sell_uom": "gallon", "pack_qty": 5, "suggested_department": "PNT"}]}"""


@router.post("/parse")
async def parse_document(
    file: UploadFile = File(...),
    use_ai: bool = False,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """
    Parse image or PDF document; extract vendor, items, UOM, costs.
    By default uses free OCR (Tesseract). Set use_ai=true to use Gemini when LLM_API_KEY is configured.
    """
    try:
        contents = await file.read()
        content_type = (file.content_type or "").lower()
        filename = file.filename or ""

        # Free path: OCR (no API key)
        if not use_ai or not LLM_AVAILABLE:
            from services.ocr_parse import extract_from_document
            extracted = await asyncio.to_thread(
                extract_from_document,
                contents,
                content_type=content_type,
                filename=filename,
            )
            for p in extracted.get("products", []):
                qty = p.get("quantity", 1)
                if "ordered_qty" not in p or p["ordered_qty"] is None:
                    p["ordered_qty"] = qty
                if "delivered_qty" not in p or p["delivered_qty"] is None:
                    p["delivered_qty"] = qty
            return extracted

        # AI path: Gemini (requires LLM_API_KEY)
        is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")

        def _do_parse():
            if is_pdf:
                from services.llm import generate_with_pdf
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
                from services.llm import generate_with_image
                mime = content_type or "image/jpeg"
                if "image/" not in mime:
                    mime = "image/jpeg"
                return generate_with_image(
                    "Extract all product and vendor information. Return only valid JSON.",
                    contents,
                    mime_type=mime,
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
                    logger.info(f"Rate limit hit, retrying in {delay}s (attempt {attempt + 1}/{_PARSE_MAX_RETRIES + 1})")
                    await asyncio.sleep(delay)
                else:
                    raise

        if not response or not str(response).strip():
            raise HTTPException(status_code=500, detail="LLM returned no content. The document may be unreadable or blocked.")

        json_match = re.search(r"\{[\s\S]*\}", response)
        extracted = json.loads(json_match.group()) if json_match else json.loads(response)

        for p in extracted.get("products", []):
            qty = p.get("quantity", 1)
            if "ordered_qty" not in p or p["ordered_qty"] is None:
                p["ordered_qty"] = qty
            if "delivered_qty" not in p or p["delivered_qty"] is None:
                p["delivered_qty"] = qty

        return extracted
    except json.JSONDecodeError as e:
        logger.error(f"Document parse JSON error: {e}")
        raise HTTPException(status_code=422, detail="Could not parse document data")
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Document parse: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Document parse error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import")
async def import_document(
    data: DocumentImportRequest,
    current_user: dict = Depends(require_role("admin", "warehouse_manager")),
):
    """Import parsed products; create or match vendor."""
    return await do_import_document(
        vendor_name=data.vendor_name,
        products=data.products,
        department_id=data.department_id,
        create_vendor_if_missing=data.create_vendor_if_missing,
        current_user=current_user,
    )
