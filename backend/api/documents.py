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
from services.document_import_service import import_document as do_import_document

from .schemas import DocumentImportRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

_DOCUMENT_PARSE_SYSTEM = """You are a document parser for a hardware store. Extract vendor/supplier name, document date, total, and line items from receipts, invoices, or packing slips.
Per item include: name, quantity, ordered_qty, delivered_qty, price, cost, original_sku, base_unit, sell_uom, pack_qty, suggested_department.
Allowed UOM: each, case, box, pack, bag, roll, kit, gallon, quart, pint, liter, pound, ounce, foot, meter, yard, sqft.
Infer UOM from product names (e.g. "5 Gal Paint" -> base_unit gallon, pack_qty 5). Use EFFECTIVE price after discounts.
When ordered/delivered unclear, set both to quantity. Use "each", "each", 1 for base_unit, sell_uom, pack_qty when unsure.
Suggested department codes: PLU, ELE, PNT, LUM, TOL, HDW, GDN, APP.
Return ONLY valid JSON: {"vendor_name": "...", "document_date": "YYYY-MM-DD", "total": N, "products": [{"name": "...", "quantity": 1, "ordered_qty": 1, "delivered_qty": 1, "price": 9.99, "cost": 7.99, "original_sku": "...", "base_unit": "each", "sell_uom": "each", "pack_qty": 1, "suggested_department": "HDW"}]}"""


@router.post("/parse")
async def parse_document(file: UploadFile = File(...), current_user: dict = Depends(require_role("admin", "warehouse_manager"))):
    """Parse image or PDF document; extract vendor, items, UOM, costs, ordered/delivered."""
    import uuid

    try:
        contents = await file.read()
        if not os.environ.get("LLM_API_KEY"):
            raise HTTPException(status_code=500, detail="LLM API key not configured")

        content_type = (file.content_type or "").lower()
        is_pdf = content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf")

        if is_pdf:
            from services.llm import generate_with_pdf

            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
                    tf.write(contents)
                    temp_path = tf.name
                response = await asyncio.to_thread(
                    generate_with_pdf,
                    "Extract all product and vendor information. Return only valid JSON.",
                    temp_path,
                    system_instruction=_DOCUMENT_PARSE_SYSTEM,
                )
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
        else:
            from services.llm import generate_with_image

            mime = content_type or "image/jpeg"
            if "image/" not in mime:
                mime = "image/jpeg"
            response = await asyncio.to_thread(
                generate_with_image,
                "Extract all product and vendor information. Return only valid JSON.",
                contents,
                mime_type=mime,
                system_instruction=_DOCUMENT_PARSE_SYSTEM,
            )

        if not response:
            raise HTTPException(status_code=500, detail="LLM failed to process document")

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
