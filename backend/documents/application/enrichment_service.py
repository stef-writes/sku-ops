"""
LLM enrichment for document import: department, UOM, and product alignment.
When ANTHROPIC_API_KEY is set, enriches extracted items with suggested_department,
base_unit, sell_uom, pack_qty, and original_sku to match existing vendor products.
"""

import asyncio
import json
import logging
import re

from assistant.application.llm import generate_text
from shared.infrastructure.config import LLM_AVAILABLE
from shared.infrastructure.prompt_loader import load_prompt
from shared.kernel.units import ALLOWED_BASE_UNITS

logger = logging.getLogger(__name__)

_ENRICHMENT_UNITS_STR = ", ".join(sorted(ALLOWED_BASE_UNITS))


def _normalize_enriched_unit(raw) -> str:
    """Coerce LLM unit output to an allowed unit."""
    if not raw or not isinstance(raw, str):
        return "each"
    v = raw.lower().strip()
    abbrev = {
        "gal": "gallon",
        "gals": "gallon",
        "gallons": "gallon",
        "ft": "foot",
        "feet": "foot",
        "lf": "foot",
        "linear foot": "foot",
        "in": "inch",
        "in.": "inch",
        "inches": "inch",
        "yd": "yard",
        "yards": "yard",
        "lb": "pound",
        "lbs": "pound",
        "pounds": "pound",
        "oz": "ounce",
        "ounces": "ounce",
        "qt": "quart",
        "quarts": "quart",
        "pt": "pint",
        "pints": "pint",
        "sq ft": "sqft",
        "square feet": "sqft",
        "ea": "each",
        "pc": "each",
        "pcs": "each",
        "bx": "box",
        "cs": "case",
        "pk": "pack",
        "pkg": "pack",
    }
    v = abbrev.get(v, v)
    return v if v in ALLOWED_BASE_UNITS else "each"


async def enrich_for_import(
    items: list[dict],
    vendor_products: list[dict],
    dept_codes: list[str],
) -> list[dict]:
    """
    When LLM available: enrich items with suggested_department, UOM, and original_sku.
    vendor_products: existing products from this vendor (id, name, original_sku, sku).
    dept_codes: valid department codes.
    """
    if not LLM_AVAILABLE or not items:
        return items

    vendor_str = "\n".join(
        f"- {p.get('name', '')} | original_sku: {p.get('original_sku') or 'none'} | sku: {p.get('sku', '')}"
        for p in vendor_products[:100]
    )
    items_str = "\n".join(
        f"{i + 1}. {item.get('name', '')} (current suggested_department: {item.get('suggested_department') or 'HDW'}, original_sku: {item.get('original_sku') or 'none'})"
        for i, item in enumerate(items)
    )

    prompt = f"""You are a hardware store import assistant. For each line item:
1. Suggest the best department code.
2. Match to an existing vendor product if possible.
3. Classify the unit of measure (base_unit, sell_uom, pack_qty).

Valid department codes: {", ".join(dept_codes)}
Department hints: PLU=plumbing, ELE=electrical, PNT=paint, LUM=lumber, TOL=tools, HDW=hardware, GDN=garden, APP=appliances.

Allowed units: {_ENRICHMENT_UNITS_STR}

UOM rules:
- Linear goods (pipe, wire, cable, lumber, conduit, trim): base_unit=foot, sell_uom=foot (or inch if sold by inch).
- Liquids (paint, stain, primer, sealer): base_unit=gallon (or quart/pint if smaller).
- Fasteners (screws, nails, bolts): base_unit=box.
- Sheet goods (drywall, plywood): base_unit=sqft.
- Bulk (concrete, mortar, soil): base_unit=bag or pound.
- Use "each" ONLY for discrete items (fixtures, faucets, tools, valves, fittings).
- pack_qty: embedded quantity from name, e.g. "5 Gal Paint" -> pack_qty=5, "PEX 100ft" -> pack_qty=100.
- sell_uom can differ from base_unit when contractors buy in smaller units (e.g. base_unit=foot, sell_uom=inch for pipe sold by the inch).

Existing products from this vendor:
{vendor_str if vendor_str.strip() else "(none - all will be new)"}

Line items to classify:
{items_str}

For each item (1 to {len(items)}), return a JSON array with one object per item in same order:
[{{"suggested_department": "PLU", "original_sku": "vendor-sku-or-null", "base_unit": "foot", "sell_uom": "foot", "pack_qty": 1}}, ...]
Return ONLY the JSON array, no other text."""

    try:
        response = await asyncio.to_thread(
            generate_text,
            prompt,
            system_instruction=load_prompt(__file__, "enrichment_prompt.md"),
        )
        if not response:
            return items

        json_match = re.search(r"\[[\s\S]*\]", response)
        if not json_match:
            return items

        try:
            results = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.warning("Document enrichment: LLM returned invalid JSON — %s", e)
            return items

        for i, item in enumerate(items):
            if i < len(results):
                r = results[i]
                if isinstance(r, dict):
                    dept = (r.get("suggested_department") or "").upper().strip()
                    if dept and dept in dept_codes:
                        item["suggested_department"] = dept
                    orig = r.get("original_sku")
                    if orig and str(orig).strip():
                        item["original_sku"] = str(orig).strip()
                    bu = _normalize_enriched_unit(r.get("base_unit"))
                    su = _normalize_enriched_unit(r.get("sell_uom", r.get("base_unit")))
                    if bu != "each":
                        item["base_unit"] = bu
                        item["sell_uom"] = su
                        try:
                            item["pack_qty"] = max(1, int(r.get("pack_qty", 1)))
                        except (ValueError, TypeError):
                            item["pack_qty"] = 1
    except (ValueError, RuntimeError, OSError, KeyError, json.JSONDecodeError) as e:
        logger.warning(
            "Document enrichment failed (%s: %s) — items returned without enrichment",
            type(e).__name__,
            e,
        )
        for item in items:
            item.setdefault(
                "enrichment_warning",
                "Auto-classification unavailable — verify department, UOM, and SKU matching",
            )
    return items
