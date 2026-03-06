"""Zero-LLM lookup engine — pattern-match user queries to single tool calls.

Handles ~60% of queries at zero LLM cost. Each pattern maps to:
  (regex, tool_function, arg_extractor, response_template)

try_lookup() returns a formatted markdown response string or None.
"""
import json
import logging
import re
from collections.abc import Callable

from assistant.agents.tools.registry import get_by_lookup_key

logger = logging.getLogger(__name__)


# ── Arg extractors ────────────────────────────────────────────────────────────

def _extract_sku(m: re.Match, msg: str) -> dict:
    sku = (m.group("sku") if "sku" in m.groupdict() else "").strip().upper()
    return {"sku": sku}


def _extract_name(m: re.Match, msg: str) -> dict:
    name = (m.group("name") if "name" in m.groupdict() else "").strip()
    return {"name": name}


def _extract_query(m: re.Match, msg: str) -> dict:
    query = (m.group("query") if "query" in m.groupdict() else msg).strip()
    return {"query": query}


def _extract_job(m: re.Match, msg: str) -> dict:
    job_id = (m.group("job") if "job" in m.groupdict() else "").strip()
    return {"job_id": job_id}


def _extract_dept(m: re.Match, msg: str) -> dict:
    code = (m.group("dept") if "dept" in m.groupdict() else "").strip().upper()
    return {"dept_code": code}


def _no_args(m: re.Match, msg: str) -> dict:
    return {}


def _extract_limit(m: re.Match, msg: str) -> dict:
    return {"limit": 20}


# ── Response templates ────────────────────────────────────────────────────────

def _format_product_search(data: dict) -> str:
    products = data.get("products", [])
    if not products:
        return "No products found matching your search."
    lines = ["| SKU | Name | On Hand | Dept |", "|-----|------|---------|------|"]
    for p in products[:20]:
        lines.append(f"| {p.get('sku', '')} | {p.get('name', '')} | {p.get('quantity', '')} | {p.get('department', '')} |")
    return f"**{data.get('count', 0)} product(s) found:**\n\n" + "\n".join(lines)


def _format_product_details(data: dict) -> str:
    if "error" in data:
        return data["error"]
    return (
        f"**{data.get('name', '')}** (`{data.get('sku', '')}`)\n\n"
        f"| Field | Value |\n|-------|-------|\n"
        f"| Price | ${data.get('price', 0):.2f} |\n"
        f"| Cost | ${data.get('cost', 0):.2f} |\n"
        f"| On Hand | {data.get('quantity', 0)} {data.get('sell_uom', 'each')} |\n"
        f"| Min Stock | {data.get('min_stock', 0)} |\n"
        f"| Department | {data.get('department', '')} |\n"
        f"| Vendor | {data.get('vendor', '')} |"
    )


def _format_low_stock(data: dict) -> str:
    products = data.get("products", [])
    if not products:
        return "No products are below their reorder point right now."
    lines = ["| SKU | Name | On Hand | Min | Dept |", "|-----|------|---------|-----|------|"]
    for p in products[:20]:
        lines.append(f"| {p.get('sku', '')} | {p.get('name', '')} | {p.get('quantity', '')} | {p.get('min_stock', '')} | {p.get('department', '')} |")
    return f"**{data.get('count', 0)} product(s) at or below reorder point:**\n\n" + "\n".join(lines)


def _format_stats(data: dict) -> str:
    return (
        f"**Inventory Summary**\n\n"
        f"- **{data.get('total_skus', 0)}** distinct products\n"
        f"- **${data.get('total_cost_value', 0):,.2f}** total cost value\n"
        f"- **{data.get('low_stock_count', 0)}** below reorder point\n"
        f"- **{data.get('out_of_stock_count', 0)}** out of stock"
    )


def _format_departments(data: dict) -> str:
    depts = data.get("departments", [])
    if not depts:
        return "No departments found."
    lines = ["| Code | Name | Products |", "|------|------|----------|"]
    for d in depts:
        lines.append(f"| {d.get('code', '')} | {d.get('name', '')} | {d.get('product_count', 0)} |")
    return "**Departments:**\n\n" + "\n".join(lines)


def _format_vendors(data: dict) -> str:
    vendors = data.get("vendors", [])
    if not vendors:
        return "No vendors found."
    lines = ["| Vendor | Products |", "|--------|----------|"]
    for v in vendors:
        lines.append(f"| {v.get('name', '')} | {v.get('product_count', 0)} |")
    return "**Vendors:**\n\n" + "\n".join(lines)


def _format_pending_requests(data: dict) -> str:
    reqs = data.get("pending_requests", [])
    if not reqs:
        return "No pending material requests."
    lines = ["| Contractor | Job | Items | Requested |", "|-----------|-----|-------|-----------|"]
    for r in reqs:
        lines.append(f"| {r.get('contractor', '')} | {r.get('job_id', '')} | {r.get('item_count', 0)} | {r.get('requested_at', '')} |")
    return f"**{data.get('count', 0)} pending request(s):**\n\n" + "\n".join(lines)


def _format_outstanding(data: dict) -> str:
    balances = data.get("balances", [])
    if not balances:
        return "No outstanding balances."
    lines = ["| Entity | Balance | Withdrawals | Oldest |", "|--------|---------|-------------|--------|"]
    for b in balances:
        lines.append(f"| {b.get('entity', '')} | ${b.get('balance', 0):,.2f} | {b.get('withdrawal_count', 0)} | {b.get('oldest_unpaid', '')} |")
    return f"**${data.get('total_outstanding', 0):,.2f} outstanding across {data.get('entity_count', 0)} entities:**\n\n" + "\n".join(lines)


def _format_contractor(data: dict) -> str:
    ws = data.get("withdrawals", [])
    if not ws:
        return f"No withdrawals found for '{data.get('contractor_search', '')}'."
    lines = ["| Date | Job | Total | Status |", "|------|-----|-------|--------|"]
    for w in ws[:15]:
        lines.append(f"| {w.get('date', '')} | {w.get('job_id', '')} | ${w.get('total', 0):,.2f} | {w.get('payment_status', '')} |")
    return (
        f"**{data.get('contractor_search', '')}** — {data.get('count', 0)} withdrawal(s), "
        f"${data.get('total_spent', 0):,.2f} total, ${data.get('unpaid_balance', 0):,.2f} unpaid\n\n" + "\n".join(lines)
    )


def _format_job_materials(data: dict) -> str:
    if "error" in data:
        return data["error"]
    items = data.get("items", [])
    lines = ["| SKU | Name | Qty | Subtotal |", "|-----|------|-----|----------|"]
    for i in items:
        lines.append(f"| {i.get('sku', '')} | {i.get('name', '')} | {i.get('quantity', 0)} | ${i.get('subtotal', 0):,.2f} |")
    return (
        f"**Job {data.get('job_id', '')}** — {data.get('contractor', '')}, "
        f"${data.get('total', 0):,.2f} total\n\n" + "\n".join(lines)
    )


# ── Lookup patterns ───────────────────────────────────────────────────────────
# Each entry: (compiled_regex, tool_module_path, tool_func_name, arg_extractor, response_formatter)

_LOOKUP_PATTERNS: list[tuple[re.Pattern, str, str, Callable, Callable]] = [
    # Inventory lookups
    (re.compile(r"(?:do we have|search for|find|look up|lookup)\s+(?P<query>.+)", re.IGNORECASE),
     "inventory", "search_products", _extract_query, _format_product_search),

    (re.compile(r"(?:details?|info|tell me about)\s+(?:for\s+)?(?:sku\s+)?(?P<sku>[A-Z]{2,4}-\w+-\w+)", re.IGNORECASE),
     "inventory", "product_details", _extract_sku, _format_product_details),

    (re.compile(r"(?:low stock|below reorder|needs? reorder)", re.IGNORECASE),
     "inventory", "low_stock", _no_args, _format_low_stock),

    (re.compile(r"(?:inventory stats?|how many products?|catalogue size|catalog size|how many skus?)", re.IGNORECASE),
     "inventory", "stats", _no_args, _format_stats),

    (re.compile(r"(?:list|show|what)\s+departments?", re.IGNORECASE),
     "inventory", "departments", _no_args, _format_departments),

    (re.compile(r"(?:list|show|what)\s+vendors?|(?:who are|list)\s+(?:our\s+)?suppliers?", re.IGNORECASE),
     "inventory", "vendors", _no_args, _format_vendors),

    # Ops lookups
    (re.compile(r"pending\s+(?:material\s+)?requests?|requests?\s+awaiting", re.IGNORECASE),
     "ops", "pending_requests", _no_args, _format_pending_requests),

    (re.compile(r"(?:history|withdrawals?)\s+(?:for|by)\s+(?P<name>[\w\s]+?)(?:\s*$|\s+(?:last|this|in))", re.IGNORECASE),
     "ops", "contractor_history", _extract_name, _format_contractor),

    (re.compile(r"(?:what\s+(?:was\s+)?(?:pulled|used)|materials?)\s+(?:for|on)\s+(?:job\s+)?(?P<job>[\w-]+)", re.IGNORECASE),
     "ops", "job_materials", _extract_job, _format_job_materials),

    # Finance lookups
    (re.compile(r"(?:who owes|outstanding\s+balance|unpaid\s+accounts?|unpaid\s+balance)", re.IGNORECASE),
     "finance", "outstanding", _no_args, _format_outstanding),
]

# ── Public API ────────────────────────────────────────────────────────────────

async def try_lookup(message: str, org_id: str) -> str | None:
    """Try to answer the message with a single tool call + template.

    Returns a formatted markdown string if a pattern matches, else None.
    """
    for pattern, domain, tool_key, arg_extractor, formatter in _LOOKUP_PATTERNS:
        m = pattern.search(message)
        if not m:
            continue
        try:
            entry = get_by_lookup_key(domain, tool_key)
            if not entry:
                continue
            args = arg_extractor(m, message)
            if entry.takes_args:
                raw = await entry.fn(args, org_id)
            else:
                raw = await entry.fn(org_id)
            data = json.loads(raw)
            return formatter(data)
        except Exception as e:
            logger.warning(f"Lookup failed for pattern={pattern.pattern}: {e}")
            continue
    return None
