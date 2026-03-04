"""Document parse/import routes."""
import asyncio
import json
import logging
import os
import re
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from identity.application.auth_service import require_role
from shared.infrastructure.config import ANTHROPIC_AVAILABLE, LLM_SETUP_URL
from documents.application.import_service import import_document as do_import_document

from api.schemas import DocumentImportRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

_PARSE_MAX_RETRIES = 2
_PARSE_RETRY_DELAYS = (5, 15)  # seconds on rate limit

_DOCUMENT_PARSE_SYSTEM = """You are a document parser for a hardware store. Extract vendor name, date, total, and line items from receipts, invoices, or packing slips.

OUTPUT: return ONLY a single valid JSON object, no other text:
{"vendor_name": "...", "document_date": "YYYY-MM-DD", "total": 0.0, "products": [...]}

Per product:
{"name": "...", "quantity": 1, "price": 0.0, "cost": 0.0,
 "original_sku": null, "base_unit": "each", "sell_uom": "each", "pack_qty": 1, "suggested_department": "HDW"}

QUANTITY — most critical. Read the document's "Qty" / "Quantity" / "Count" column:
- quantity = number of selling units on this line (e.g. if Qty column shows 12, set quantity=12)
- NEVER default to 1 unless the document literally shows no quantity column or the cell is blank/1
- quantity is NOT the count inside a pack — that is pack_qty

COST vs PRICE — second most critical:
- cost = the unit price you PAY per selling unit (look for "Unit Price", "Unit Cost", "Each", "Price Ea." column)
- price = the suggested retail sell price (set 0.0 unless the document explicitly shows a retail/list price column)
- CRITICAL: Do NOT set cost = line extension/line total. Line total = qty × unit price.
  Example: if Qty=3 and Line Total=$29.97 → cost=9.99 NOT 29.97
- If document shows only line totals: cost = line_total / quantity
- If document shows a unit price column: cost = that column value directly

NAME: Remove vendor item codes and barcodes from name. Include specs (size, material, length):
- Good: "1/2\" x 10ft PEX Pipe" | Bad: "PEX PIPE 1/2X10 #4521-A"

original_sku: vendor's item code/part number for this line; null if not separately visible.

vendor_name: supplier name from document header (not the store's own name).
document_date: ISO YYYY-MM-DD. Use invoice/PO date, not delivery date.

UOM RULES — do NOT default everything to "each". Reason step by step:
1. Look for an explicit quantity+unit in the product description (e.g. "100ft", "5 Gal", "80lb").
2. If found: extract the number as pack_qty and the unit as base_unit and sell_uom.
3. If not explicit, infer from category keywords below.
Allowed values: each, case, box, pack, bag, roll, kit, gallon, quart, pint, liter, pound, ounce, foot, meter, yard, sqft

Examples:
- "5 Gal Exterior Paint" → base_unit=gallon, sell_uom=gallon, pack_qty=5 | PNT
- "2x4x8 Stud" → base_unit=foot, sell_uom=foot, pack_qty=8 | LUM
- "2x6x12 Lumber" → base_unit=foot, sell_uom=foot, pack_qty=12 | LUM
- "1/2\" PEX Pipe 100ft" → base_unit=foot, sell_uom=foot, pack_qty=100 | PLU
- "3/4\" Copper Pipe 10ft" → base_unit=foot, sell_uom=foot, pack_qty=10 | PLU
- "Romex 12/2 250ft" → base_unit=foot, sell_uom=foot, pack_qty=250 | ELE
- "#8 Wood Screw Box 100ct" → base_unit=box, sell_uom=box, pack_qty=1 | HDW
- "3/8\" Carriage Bolt 50pk" → base_unit=pack, sell_uom=pack, pack_qty=1 | HDW
- "Drywall 4x8 Sheet" → base_unit=sqft, sell_uom=sqft, pack_qty=32 | LUM
- "80lb Concrete Mix Bag" → base_unit=pound, sell_uom=pound, pack_qty=80 | HDW
- "50lb Play Sand" → base_unit=pound, sell_uom=pound, pack_qty=50 | HDW
- "Duct Tape Roll 60yd" → base_unit=roll, sell_uom=roll, pack_qty=1 | HDW
- "1/2\" Ball Valve" → base_unit=each, sell_uom=each, pack_qty=1 | PLU
- "Caulk Tube 10oz" → base_unit=each, sell_uom=each, pack_qty=1 | PNT
- "Quart Interior Paint" → base_unit=quart, sell_uom=quart, pack_qty=1 | PNT
Use "each" only when no unit or quantity is inferable.

Departments: PLU=plumbing, ELE=electrical, PNT=paint, LUM=lumber, TOL=tools, HDW=hardware, GDN=garden, APP=appliances."""


@router.post("/parse")
async def parse_document(
    file: UploadFile = File(...),
    use_ai: bool = False,
    _: dict = Depends(require_role("admin", "warehouse_manager")),
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
            return extracted
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"OCR parse error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    if not ANTHROPIC_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=f"AI not configured. Add ANTHROPIC_API_KEY to backend/.env — get a key at {LLM_SETUP_URL}",
        )

    try:
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
                    logger.info(f"Rate limit, retrying in {delay}s (attempt {attempt + 1})")
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
