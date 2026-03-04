"""
UOM classification for hardware/building-supply products.
Uses Anthropic Claude when ANTHROPIC_API_KEY is set; otherwise falls back to rule-based infer_uom.
"""
from typing import List, Optional
import asyncio
import json
import re
import logging

from shared.infrastructure.config import LLM_AVAILABLE
from documents.application.import_parser import infer_uom as rule_infer_uom
from assistant.application.llm import generate_text

logger = logging.getLogger(__name__)

ALLOWED_UNITS = [
    "each", "case", "box", "pack", "bag", "roll", "kit",
    "gallon", "quart", "pint", "liter",
    "pound", "ounce",
    "foot", "meter", "yard",
    "sqft",
]


def _normalize_unit(raw: str) -> str:
    """Map LLM output to allowed unit, default to each."""
    if not raw or not isinstance(raw, str):
        return "each"
    v = raw.lower().strip()
    # Common LLM variations and abbreviations
    mapping = {
        "gal": "gallon", "gals": "gallon", "gallons": "gallon", "gal.": "gallon",
        "qts": "quart", "quarts": "quart", "qt": "quart", "qt.": "quart",
        "pt": "pint", "pints": "pint", "pts": "pint", "pt.": "pint",
        "lbs": "pound", "lb": "pound", "pounds": "pound", "lb.": "pound",
        "oz": "ounce", "ozs": "ounce", "ounces": "ounce", "oz.": "ounce",
        "ft": "foot", "feet": "foot", "lf": "foot", "lnft": "foot", "ln ft": "foot", "linear foot": "foot",
        "m": "meter", "meters": "meter", "metres": "meter",
        "yd": "yard", "yards": "yard", "yds": "yard",
        "sq ft": "sqft", "sqft": "sqft", "square feet": "sqft", "sq. ft": "sqft",
        "bx": "box", "cs": "case", "pk": "pack", "pkg": "pack", "pkgs": "pack",
        "ea": "each", "pc": "each", "pcs": "each", "piece": "each", "pieces": "each",
    }
    v = mapping.get(v, v)
    return v if v in ALLOWED_UNITS else "each"


def _normalize_pack_qty(val) -> int:
    """Ensure pack_qty is valid positive int."""
    if val is None:
        return 1
    try:
        n = int(val)
        return max(1, n)
    except (ValueError, TypeError):
        return 1


async def classify_uom(product_name: str, description: Optional[str] = None) -> dict:
    """
    Use AI to classify UOM for a single product.
    Returns {"base_unit": str, "sell_uom": str, "pack_qty": int}.
    """
    units_str = ", ".join(ALLOWED_UNITS)
    prompt = f"""Classify the unit of measure for this hardware/building-supply product.
Product name: {product_name}
{f'Description: {description}' if description else ''}

Allowed units: {units_str}

Consider: "5 Gal Paint" -> gallon, pack_qty 5; "2x4x8" -> foot; "Nail Box" -> box; "Pipe Fitting" -> each.
Return ONLY valid JSON: {{"base_unit": "...", "sell_uom": "...", "pack_qty": 1}}"""

    try:
        response = await asyncio.to_thread(
            generate_text,
            prompt,
            system_instruction="You are a UOM classifier. Return only valid JSON.",
        )
        if response:
            json_match = re.search(r"\{[^{}]*\}", response)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "base_unit": _normalize_unit(data.get("base_unit")),
                    "sell_uom": _normalize_unit(data.get("sell_uom", data.get("base_unit"))),
                    "pack_qty": _normalize_pack_qty(data.get("pack_qty")),
                }
    except Exception as e:
        logger.warning(f"UOM classification failed: {e}")
    return {"base_unit": "each", "sell_uom": "each", "pack_qty": 1}


async def classify_uom_batch(products: List[dict]) -> List[dict]:
    """
    Classify UOM for products. Uses LLM when available; otherwise rule-based infer_uom.
    Returns same list with base_unit, sell_uom, pack_qty added to each item.
    """
    if not products:
        return []

    # Free path: rule-based (no API key)
    if not LLM_AVAILABLE:
        for p in products:
            bu, su, pq = rule_infer_uom(p.get("name", ""))
            p["base_unit"] = bu
            p["sell_uom"] = su
            p["pack_qty"] = pq
        return products

    for p in products:
        p.setdefault("base_unit", "each")
        p.setdefault("sell_uom", "each")
        p.setdefault("pack_qty", 1)

    units_str = ", ".join(ALLOWED_UNITS)
    names = [p.get("name", "Unknown") for p in products]
    prompt = f"""Classify unit of measure for each hardware/building-supply product.
Allowed units: {units_str}

Products:
{chr(10).join(f'- "{n}"' for n in names)}

Infer base_unit, sell_uom, pack_qty from the name. Examples: "5 Gal Paint" -> gallon/gallon/5; "2x4x8 Stud" -> foot/foot/8; "PEX 1/2 100ft" -> foot/foot/100; "Screw Box" -> box/box/1; "Wire 12/2" -> foot/foot/1; "Drywall 4x8" -> sqft/sqft/1; "Concrete 80lb" -> pound/pound/1; "Duct Tape" -> roll/roll/1. Use "each" only when name suggests a single item (faucet, fixture).
Return ONLY a JSON array, one object per product in same order: [{{"base_unit":"...","sell_uom":"...","pack_qty":1}}, ...]"""

    def _rule_fallback(p: dict) -> None:
        bu, su, pq = rule_infer_uom(p.get("name", ""))
        p["base_unit"] = bu
        p["sell_uom"] = su
        p["pack_qty"] = pq

    try:
        response = await asyncio.to_thread(
            generate_text,
            prompt,
            system_instruction="You are a UOM classifier. Return only a valid JSON array.",
        )
        if response:
            json_match = re.search(r"\[[\s\S]*\]", response)
            if json_match:
                results = json.loads(json_match.group())
                for i, p in enumerate(products):
                    r = results[i] if i < len(results) else None
                    if r and isinstance(r, dict):
                        p["base_unit"] = _normalize_unit(r.get("base_unit"))
                        p["sell_uom"] = _normalize_unit(r.get("sell_uom", r.get("base_unit")))
                        p["pack_qty"] = _normalize_pack_qty(r.get("pack_qty"))
                    else:
                        # LLM returned fewer results than products — use rules for the gap
                        _rule_fallback(p)
                return products
    except Exception as e:
        logger.warning(f"Batch UOM classification failed, falling back to rules: {e}")

    # LLM unavailable or failed — rule-based fallback for every item
    for p in products:
        _rule_fallback(p)
    return products
