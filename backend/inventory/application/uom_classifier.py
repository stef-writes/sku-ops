"""
UOM classification for hardware/building-supply products.
Uses LLM when a generate_text callable is provided; otherwise falls back to rule-based inference.
Cross-domain dependencies (LLM, rule parser) are injected by callers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from shared.infrastructure.prompt_loader import load_prompt
from shared.kernel.units import ALLOWED_BASE_UNITS

logger = logging.getLogger(__name__)

# Type aliases for injected dependencies
GenerateTextFn = Callable[[str, str | None], str | None] | None
RuleInferFn = Callable[[str], tuple[str, str, int]]


@dataclass(frozen=True)
class UOMClassification:
    """Result of classifying a product's unit of measure."""

    base_unit: str
    sell_uom: str
    pack_qty: int


def _default_rule_infer(_name: str) -> tuple[str, str, int]:
    """Fallback: everything is 'each'."""
    return "each", "each", 1


def _normalize_unit(raw: str) -> str:
    """Map LLM output to allowed unit, default to each."""
    if not raw or not isinstance(raw, str):
        return "each"
    v = raw.lower().strip()
    # Common LLM variations and abbreviations
    mapping = {
        "gal": "gallon",
        "gals": "gallon",
        "gallons": "gallon",
        "gal.": "gallon",
        "qts": "quart",
        "quarts": "quart",
        "qt": "quart",
        "qt.": "quart",
        "pt": "pint",
        "pints": "pint",
        "pts": "pint",
        "pt.": "pint",
        "lbs": "pound",
        "lb": "pound",
        "pounds": "pound",
        "lb.": "pound",
        "oz": "ounce",
        "ozs": "ounce",
        "ounces": "ounce",
        "oz.": "ounce",
        "ft": "foot",
        "feet": "foot",
        "lf": "foot",
        "lnft": "foot",
        "ln ft": "foot",
        "linear foot": "foot",
        "in": "inch",
        "in.": "inch",
        "inches": "inch",
        "inch": "inch",
        "m": "meter",
        "meters": "meter",
        "metres": "meter",
        "yd": "yard",
        "yards": "yard",
        "yds": "yard",
        "sq ft": "sqft",
        "sqft": "sqft",
        "square feet": "sqft",
        "sq. ft": "sqft",
        "bx": "box",
        "cs": "case",
        "pk": "pack",
        "pkg": "pack",
        "pkgs": "pack",
        "ea": "each",
        "pc": "each",
        "pcs": "each",
        "piece": "each",
        "pieces": "each",
    }
    v = mapping.get(v, v)
    return v if v in ALLOWED_BASE_UNITS else "each"


def _normalize_pack_qty(val) -> int:
    """Ensure pack_qty is valid positive int."""
    if val is None:
        return 1
    try:
        n = int(val)
        return max(1, n)
    except (ValueError, TypeError):
        return 1


async def classify_uom(
    product_name: str,
    description: str | None = None,
    *,
    generate_text: GenerateTextFn = None,
) -> UOMClassification:
    """Use AI to classify UOM for a single product.

    Pass generate_text callable to enable LLM classification.
    Falls back to each/each/1 when no LLM is available.
    """
    if not generate_text:
        return UOMClassification(base_unit="each", sell_uom="each", pack_qty=1)

    units_str = ", ".join(sorted(ALLOWED_BASE_UNITS))
    prompt = f"""Classify the unit of measure for this hardware/building-supply product.
Product name: {product_name}
{f"Description: {description}" if description else ""}

Allowed units: {units_str}

Rules:
- Linear goods (pipe, wire, cable, lumber, conduit, trim, rebar): base_unit=foot. sell_uom=foot (or inch if sold by the inch).
- Liquids (paint, stain, primer, sealer): base_unit=gallon (or quart/pint for smaller sizes).
- Fasteners (screws, nails, bolts): base_unit=box.
- Sheet goods (drywall, plywood): base_unit=sqft.
- Bulk (concrete, mortar, soil): base_unit=bag or pound.
- Use "each" ONLY for discrete items that are individual units (fixtures, faucets, tools, valves, individual fittings).
- pack_qty = embedded quantity in name (e.g. "5 Gal Paint" -> 5, "PEX 100ft" -> 100).
- sell_uom can differ from base_unit. E.g. pipe bought by the foot but sold by the inch: base_unit=foot, sell_uom=inch.

Examples: "5 Gal Paint" -> gallon/gallon/5; "2x4x8 Stud" -> foot/foot/8; "1/2 PEX 100ft" -> foot/foot/100; "3/4 Copper Pipe" -> foot/inch/1; "Nail Box 16d" -> box/box/1; "Pipe Fitting 1/2" -> each/each/1.
Return ONLY valid JSON: {{"base_unit": "...", "sell_uom": "...", "pack_qty": 1}}"""

    try:
        response = await asyncio.to_thread(
            generate_text,
            prompt,
            load_prompt(__file__, "uom_classifier_prompt.md"),
        )
        if response:
            json_match = re.search(r"\{[^{}]*\}", response)
            if json_match:
                data = json.loads(json_match.group())
                return UOMClassification(
                    base_unit=_normalize_unit(data.get("base_unit")),
                    sell_uom=_normalize_unit(data.get("sell_uom", data.get("base_unit"))),
                    pack_qty=_normalize_pack_qty(data.get("pack_qty")),
                )
    except (json.JSONDecodeError, ValueError, RuntimeError, OSError) as e:
        logger.warning("UOM classification failed: %s", e)
    return UOMClassification(base_unit="each", sell_uom="each", pack_qty=1)


async def classify_uom_batch(
    products: list[dict],
    *,
    generate_text: GenerateTextFn = None,
    rule_infer: RuleInferFn = _default_rule_infer,
) -> list[dict]:
    """
    Classify UOM for products. Uses LLM when generate_text is provided;
    otherwise falls back to rule_infer.
    Returns same list with base_unit, sell_uom, pack_qty added to each item.
    """
    if not products:
        return []

    def _rule_fallback(p: dict) -> None:
        bu, su, pq = rule_infer(p.get("name", ""))
        p["base_unit"] = bu
        p["sell_uom"] = su
        p["pack_qty"] = pq

    if not generate_text:
        for p in products:
            _rule_fallback(p)
        return products

    for p in products:
        p.setdefault("base_unit", "each")
        p.setdefault("sell_uom", "each")
        p.setdefault("pack_qty", 1)

    units_str = ", ".join(sorted(ALLOWED_BASE_UNITS))
    names = [p.get("name", "Unknown") for p in products]
    prompt = f"""Classify unit of measure for each hardware/building-supply product.
Allowed units: {units_str}

Products:
{chr(10).join(f'- "{n}"' for n in names)}

Rules:
- Linear goods (pipe, wire, cable, lumber, conduit, trim, rebar): base_unit=foot. sell_uom=foot or inch.
- Liquids (paint, stain, primer, sealer): base_unit=gallon (or quart/pint for smaller).
- Fasteners (screws, nails, bolts): base_unit=box.
- Sheet goods (drywall, plywood): base_unit=sqft.
- Bulk (concrete, mortar, soil): base_unit=bag or pound.
- Tape, mesh, fabric: base_unit=roll.
- Use "each" ONLY for discrete items (fixtures, faucets, tools, valves, individual fittings).
- pack_qty = embedded quantity from name (e.g. "5 Gal" -> 5, "100ft" -> 100, "80lb" -> 80).
- sell_uom can differ from base_unit when contractors buy in smaller increments.

Examples: "5 Gal Paint" -> gallon/gallon/5; "2x4x8 Stud" -> foot/foot/8; "PEX 1/2 100ft" -> foot/foot/100; "3/4 Copper Pipe" -> foot/inch/1; "Screw Box 16d" -> box/box/1; "Wire 12/2 NM" -> foot/foot/1; "Drywall 4x8" -> sqft/sqft/1; "Concrete 80lb" -> pound/pound/80; "Duct Tape" -> roll/roll/1; "Faucet Kitchen" -> each/each/1.
Return ONLY a JSON array, one object per product in same order: [{{"base_unit":"...","sell_uom":"...","pack_qty":1}}, ...]"""

    try:
        response = await asyncio.to_thread(
            generate_text,
            prompt,
            load_prompt(__file__, "uom_classifier_batch_prompt.md"),
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
                        _rule_fallback(p)
                return products
    except (json.JSONDecodeError, ValueError, RuntimeError, OSError) as e:
        logger.warning("Batch UOM classification failed, falling back to rules: %s", e)

    for p in products:
        _rule_fallback(p)
    return products
