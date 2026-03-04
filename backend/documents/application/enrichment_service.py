"""
LLM enrichment for document import: department classification and product alignment.
When ANTHROPIC_API_KEY is set, enriches extracted items with suggested_department and original_sku
to match existing vendor products.
"""
import asyncio
import json
import re
import logging
from typing import List

from shared.infrastructure.config import LLM_AVAILABLE
from shared.infrastructure.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


async def enrich_for_import(
    items: List[dict],
    vendor_products: List[dict],
    dept_codes: List[str],
) -> List[dict]:
    """
    When LLM available: enrich items with suggested_department and original_sku.
    vendor_products: existing products from this vendor (id, name, original_sku, sku).
    dept_codes: valid department codes.
    """
    if not LLM_AVAILABLE or not items:
        return items

    try:
        from assistant.application.llm import generate_text
    except ImportError:
        return items

    vendor_str = "\n".join(
        f"- {p.get('name','')} | original_sku: {p.get('original_sku') or 'none'} | sku: {p.get('sku','')}"
        for p in vendor_products[:100]  # limit for prompt size
    )
    items_str = "\n".join(
        f"{i+1}. {item.get('name','')} (current suggested_department: {item.get('suggested_department') or 'HDW'}, original_sku: {item.get('original_sku') or 'none'})"
        for i, item in enumerate(items)
    )

    prompt = f"""You are a hardware store import assistant. For each line item, suggest the best department code and match to an existing vendor product if possible.

Valid department codes: {', '.join(dept_codes)}
Department hints: PLU=plumbing, ELE=electrical, PNT=paint, LUM=lumber, TOL=tools, HDW=hardware, GDN=garden, APP=appliances.

Existing products from this vendor:
{vendor_str if vendor_str.strip() else "(none - all will be new)"}

Line items to classify:
{items_str}

For each item (1 to {len(items)}), return a JSON array with one object per item in the same order:
[{{"suggested_department": "PLU", "original_sku": "vendor-sku-if-matched-or-null"}}, ...]
If you can match an item to an existing product by name/similarity, use that product's original_sku. Otherwise use null.
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
    except Exception as e:
        logger.warning("Document enrichment failed (%s: %s) — items returned without enrichment", type(e).__name__, e)
        for item in items:
            item.setdefault("enrichment_warning", "Auto-classification unavailable — verify department and SKU matching")
    return items
