"""
Free OCR-based document parsing - no API key required.
Uses Tesseract (pytesseract) to extract text, then regex to structure into vendor + line items.
Aligns with document_import_service: same output shape as LLM parse.
"""
import io
import re
from datetime import datetime
from typing import Optional

from services.document_import import infer_uom, parse_dollar

# Line item: optional SKU/code, description, quantity, price. Common patterns.
_LINE_PATTERNS = [
    # "Item Name    2    $9.99" or "Item Name  2  $9.99"
    re.compile(r"^(.+?)\s{2,}(\d+)\s+\$?([\d,]+\.?\d*)\s*$"),
    # "Item Name  $9.99" (qty 1)
    re.compile(r"^(.+?)\s+\$?([\d,]+\.?\d*)\s*$"),
    # "2  Item Name  $19.98"
    re.compile(r"^(\d+)\s+(.+?)\s+\$?([\d,]+\.?\d*)\s*$"),
]
# Skip lines that look like headers, totals, tax
_SKIP_PATTERNS = [
    re.compile(r"^(subtotal|total|tax|amount due|balance|payment)\b", re.I),
    re.compile(r"^\s*[\d.]+\s*$"),  # just a number
    re.compile(r"^[A-Z\s]{3,}$"),  # all caps header
    re.compile(r"^(date|invoice|receipt|order)\s*#?", re.I),
]


def _image_to_text(image_bytes: bytes) -> str:
    """OCR image to text. Requires pytesseract and tesseract-ocr installed."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        text = pytesseract.image_to_string(img, config="--psm 6")
        return text or ""
    except ImportError:
        raise ValueError("pytesseract not installed. Run: pip install pytesseract. Also install tesseract-ocr: brew install tesseract")
    except Exception as e:
        raise ValueError(f"OCR failed: {e}") from e


def _pdf_to_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF. Tries pypdf first (text PDFs), then pdf2image+OCR for scanned."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
        if text_parts:
            return "\n".join(text_parts)
    except ImportError:
        pass

    # Fallback: render PDF to images, OCR each page
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
        images = convert_from_bytes(pdf_bytes)
        parts = [pytesseract.image_to_string(img, config="--psm 6") for img in images]
        return "\n".join(p or "" for p in parts)
    except ImportError:
        raise ValueError(
            "PDF OCR requires: pip install pypdf pdf2image pytesseract. "
            "Also: brew install tesseract poppler"
        ) from None
    except Exception as e:
        raise ValueError(f"PDF extraction failed: {e}") from e


def _extract_vendor(lines: list[str]) -> str:
    """Heuristic: vendor often in first few non-empty lines, before line items."""
    for i, line in enumerate(lines[:15]):
        s = line.strip()
        if len(s) < 3:
            continue
        if _looks_like_item_line(s):
            break
        if not any(p.search(s) for p in _SKIP_PATTERNS):
            if len(s) > 2 and not re.match(r"^\d", s):
                return s
    return "Unknown Vendor"


def _looks_like_item_line(line: str) -> bool:
    """Check if line might be a product/line item (has price)."""
    return bool(re.search(r"\$?[\d,]+\.\d{2}\s*$", line))


def _parse_line_item(line: str) -> Optional[dict]:
    """Parse a line into {name, quantity, price, cost, ...} or None if not a line item."""
    line = line.strip()
    if not line or len(line) < 4:
        return None
    if any(p.search(line) for p in _SKIP_PATTERNS):
        return None

    for pat in _LINE_PATTERNS:
        m = pat.match(line)
        if m:
            groups = m.groups()
            if len(groups) == 3:
                if re.match(r"^\d+$", groups[0]):
                    qty = int(groups[0])
                    name = groups[1].strip()
                    price = parse_dollar(groups[2])
                else:
                    name = groups[0].strip()
                    qty_str = groups[1]
                    price = parse_dollar(groups[2])
                    qty = int(qty_str) if qty_str.isdigit() else 1
            else:
                name = groups[0].strip()
                price = parse_dollar(groups[1])
                qty = 1

            if not name or price <= 0:
                continue
            bu, su, pq = infer_uom(name)
            return {
                "name": name[:200],
                "quantity": max(1, qty),
                "ordered_qty": max(1, qty),
                "delivered_qty": max(1, qty),
                # Invoice/PO price is the unit cost (what store pays vendor).
                # Sell price defaults to cost × 1.4 — editable per product in Inventory.
                "price": round(price * 1.4, 2),
                "cost": round(price, 2),
                "original_sku": None,
                "base_unit": bu,
                "sell_uom": su,
                "pack_qty": pq,
                "suggested_department": "HDW",
            }
    return None


def extract_from_document(file_bytes: bytes, content_type: str = "", filename: str = "") -> dict:
    """
    Extract vendor + products from image or PDF using OCR. No API key needed.
    Returns same structure as LLM parse for document_import_service.
    """
    is_pdf = (
        content_type == "application/pdf"
        or (filename or "").lower().endswith(".pdf")
    )

    if is_pdf:
        text = _pdf_to_text(file_bytes)
    else:
        text = _image_to_text(file_bytes)

    lines = [ln for ln in text.splitlines() if ln.strip()]

    vendor = _extract_vendor(lines)

    products = []
    for line in lines:
        item = _parse_line_item(line)
        if item:
            products.append(item)

    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "vendor_name": vendor,
        "document_date": today,
        "total": sum(p.get("price", 0) * p.get("quantity", 1) for p in products),
        "products": products,
    }
