"""
InventoryAgent: product search, stock levels, reorders, departments, vendors.
Tools: search_products, search_semantic, get_product_details, get_inventory_stats,
       list_low_stock, list_departments, list_vendors,
       get_usage_velocity, get_reorder_suggestions, get_department_health, get_slow_movers.
"""
import json
import logging
from datetime import datetime, timezone, timedelta

from pydantic_ai import Agent, RunContext

from shared.infrastructure.config import (
    AGENT_PRIMARY_MODEL,
    AGENT_THINKING_BUDGET,
    DEFAULT_DEEP_THINKING_BUDGET,
    ANTHROPIC_AVAILABLE,
    OPENAI_API_KEY,
)
from shared.infrastructure.database import get_connection
from assistant.agents.deps import AgentDeps
from assistant.agents.agent_utils import build_message_history, extract_text_history, extract_tool_calls, calc_cost, run_agent
from assistant.agents.search import get_index
from catalog.application.queries import (
    list_products as catalog_list_products,
    list_low_stock as catalog_list_low_stock,
    list_departments as catalog_list_departments,
    list_vendors as catalog_list_vendors,
    get_sku_counters,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an inventory specialist for SKU-Ops, a hardware store management system.

TOOLS:
- search_products(query, limit): find products by name, SKU, or barcode
- search_semantic(query, limit): concept search — use when search_products finds nothing or query is descriptive ("something for fixing pipes")
- get_product_details(sku): full details for one product
- get_inventory_stats(): catalogue summary — SKU count, cost value, low/out-of-stock counts
- list_low_stock(limit): products at or below their reorder point
- list_departments(): all departments with product counts
- list_vendors(): all vendors with product counts
- get_usage_velocity(sku, days): how fast a product moves
- get_reorder_suggestions(limit): priority reorder list by urgency
- get_department_health(): per-department breakdown of healthy/low/out-of-stock product counts
- get_slow_movers(limit, days): products with stock on hand but very low withdrawal activity (dead or slow stock)

WHEN TO USE EACH TOOL:
- "do we have X / find X / search for Y" → search_products first, search_semantic if no results
- "details on [product] / tell me about SKU X" → get_product_details
- "overall stats / how many products / catalogue size" → get_inventory_stats
- "low stock / needs reordering / running low" → list_low_stock
- "list departments / what departments" → list_departments
- "list vendors / suppliers" → list_vendors
- "how fast does X move / usage rate" → get_usage_velocity
- "what should we reorder / reorder priority" → get_reorder_suggestions
- "department health / stock health by department" → get_department_health
- "slow movers / dead stock / not moving / sitting on shelf" → get_slow_movers

DEEP INVENTORY ANALYSIS — when asked for a full analysis, call in parallel:
  get_inventory_stats() + get_department_health() + get_slow_movers() + get_reorder_suggestions()
  Then write a structured report with sections: Overview, Department Health, Slow Movers, Reorder Priority.

TERMINOLOGY — be precise, hardware products have different units:
- "total_skus" = number of distinct product lines in the catalogue (not a physical count)
- "quantity" = stock on hand in that product's sell_uom (e.g. 5 gallons, 3 boxes, 12 each)
- NEVER say "X units" or "X items" — always include the specific UOM from sell_uom
- NEVER report total_quantity_sum as meaningful — it adds gallons + boxes + each, which is nonsense
- "low stock" means on-hand quantity is at or below the reorder point for that product

FORMAT — respond in GitHub-flavored markdown:
- For product lists, use a markdown table with a separator row:

| SKU | Name | On Hand | UOM | Reorder At |
|-----|------|---------|-----|------------|
| PLU-001 | Copper Pipe 3/4" | 8 | each | 10 |

- Use **bold** for critical numbers (zero stock, amounts) and key names
- Use bullet lists (- item) for multi-item summaries without tabular structure
- Keep prose responses to 1–3 sentences unless the question needs more

RESPONSE RULES:
- Stats: say "47 distinct products" or "47 SKUs" — not "47 products worth of units"
- Stock: say "8 each on hand" or "3 gallons on hand" — not "8 units"
- Low stock: "Copper Pipe: 8 each on hand, reorder at 10"
- If a product is out of stock (quantity=0), say "out of stock"
- Never make up data — always use a tool
- Be concise. If no results, say so clearly.

REASONING — think before acting:
1. Identify exactly what data the question needs before calling any tool
2. Call independent tools in the same turn when they don't depend on each other
   (e.g. get_inventory_stats + list_low_stock can run together)
3. After each tool result, ask: "Is this sufficient to answer accurately?" — if not, call more
4. Chain tools for multi-part questions: "What's low AND moving fast?" → list_low_stock, then
   get_usage_velocity for the critical items
5. If search_products finds nothing, always try search_semantic before concluding unavailable
6. Never stop early with partial data when a follow-up tool call would give a complete answer"""

_agent = Agent(
    AGENT_PRIMARY_MODEL,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
)


@_agent.tool
async def search_products(ctx: RunContext[AgentDeps], query: str, limit: int = 20) -> str:
    """Search products by name, SKU, or barcode. Returns matching products with SKU, name, quantity, min_stock, department."""
    return await _search_products({"query": query, "limit": limit}, ctx.deps.org_id)


@_agent.tool
async def search_semantic(ctx: RunContext[AgentDeps], query: str, limit: int = 10) -> str:
    """Semantic/concept search for products. Use when exact search fails or query is descriptive (e.g. 'something for fixing pipes', 'waterproof coating')."""
    return await _search_semantic({"query": query, "limit": limit}, ctx.deps.org_id)


@_agent.tool
async def get_product_details(ctx: RunContext[AgentDeps], sku: str) -> str:
    """Get full details for one product by SKU: price, cost, vendor, UOM, barcode, reorder point."""
    return await _get_product_details({"sku": sku}, ctx.deps.org_id)


@_agent.tool
async def get_inventory_stats(ctx: RunContext[AgentDeps]) -> str:
    """Catalogue summary: total_skus (distinct product lines), total_cost_value, low_stock_count, out_of_stock_count. Does NOT return a meaningful total unit count — products have different units."""
    return await _get_inventory_stats(ctx.deps.org_id)


@_agent.tool
async def list_low_stock(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """List products at or below their reorder point (quantity <= min_stock)."""
    return await _list_low_stock({"limit": limit}, ctx.deps.org_id)


@_agent.tool
async def list_departments(ctx: RunContext[AgentDeps]) -> str:
    """List all departments with product counts and next SKU."""
    return await _list_departments(ctx.deps.org_id)


@_agent.tool
async def list_vendors(ctx: RunContext[AgentDeps]) -> str:
    """List all vendors with product counts."""
    return await _list_vendors(ctx.deps.org_id)


@_agent.tool
async def get_usage_velocity(ctx: RunContext[AgentDeps], sku: str, days: int = 30) -> str:
    """How fast a product moves: total and average daily withdrawals over the last N days."""
    return await _get_usage_velocity({"sku": sku, "days": days}, ctx.deps.org_id)


@_agent.tool
async def get_reorder_suggestions(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Priority reorder list: low-stock products ranked by urgency (days until stockout based on usage velocity)."""
    return await _get_reorder_suggestions({"limit": limit}, ctx.deps.org_id)


@_agent.tool
async def get_department_health(ctx: RunContext[AgentDeps]) -> str:
    """Per-department breakdown showing healthy, low-stock, and out-of-stock product counts."""
    return await _get_department_health(ctx.deps.org_id)


@_agent.tool
async def get_slow_movers(ctx: RunContext[AgentDeps], limit: int = 20, days: int = 30) -> str:
    """Products with stock on hand but very low or zero withdrawal activity — dead or slow-moving stock tying up inventory."""
    return await _get_slow_movers({"limit": limit, "days": days}, ctx.deps.org_id)


async def run(user_message: str, history: list[dict] | None, deps: AgentDeps, mode: str = "fast", session_id: str = "") -> dict:
    if not ANTHROPIC_AVAILABLE:
        return {"response": "Inventory agent requires ANTHROPIC_API_KEY.", "tool_calls": [], "history": [], "thinking": [], "agent": "inventory"}

    deep = mode == "deep"
    thinking_budget = (AGENT_THINKING_BUDGET or DEFAULT_DEEP_THINKING_BUDGET) if deep else 0
    msg_history = build_message_history(history)
    model_settings: dict = {}
    if thinking_budget > 0:
        model_settings["anthropic_thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

    try:
        result = await run_agent(
            _agent, user_message,
            msg_history=msg_history, deps=deps,
            model_settings=model_settings or None,
            agent_name="InventoryAgent",
            session_id=session_id, mode=mode,
        )
    except Exception as e:
        logger.error(f"InventoryAgent failed: {e}")
        return {"response": "I ran into an issue. Please try again in a moment.", "tool_calls": [], "history": history or [], "thinking": [], "agent": "inventory"}

    usage = result.usage()
    cost = calc_cost(AGENT_PRIMARY_MODEL, usage)
    return {
        "response": result.output,
        "tool_calls": extract_tool_calls(result.all_messages()),
        "thinking": [],
        "history": extract_text_history(result.all_messages()),
        "usage": {"cost_usd": cost, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "model": AGENT_PRIMARY_MODEL},
        "agent": "inventory",
    }


# ── DB query implementations (unchanged) ────────────────────────────────────

async def _search_products(args: dict, org_id: str) -> str:
    query = (args.get("query") or "").strip()
    limit = min(int(args.get("limit") or 20), 50)
    items = await catalog_list_products(search=query, limit=limit, organization_id=org_id)
    out = [
        {
            "sku": p.get("sku"),
            "name": p.get("name"),
            "quantity": p.get("quantity"),
            "sell_uom": p.get("sell_uom", "each"),
            "min_stock": p.get("min_stock"),
            "department": p.get("department_name"),
        }
        for p in items
    ]
    return json.dumps({"count": len(out), "products": out})


async def _search_semantic(args: dict, org_id: str) -> str:
    query = (args.get("query") or "").strip()
    limit = min(int(args.get("limit") or 10), 30)
    index = await get_index(org_id)
    if OPENAI_API_KEY and index._embeddings is not None:
        results = await index.search_semantic(query, limit=limit, api_key=OPENAI_API_KEY)
        method = "embedding"
    else:
        results = index.search_bm25(query, limit=limit)
        method = "bm25"
    out = [
        {
            "sku": p.get("sku"),
            "name": p.get("name"),
            "quantity": p.get("quantity"),
            "sell_uom": p.get("sell_uom", "each"),
            "min_stock": p.get("min_stock"),
            "department": p.get("department_name"),
        }
        for p in results
    ]
    return json.dumps({"count": len(out), "products": out, "method": method})


async def _get_product_details(args: dict, org_id: str) -> str:
    sku = (args.get("sku") or "").strip().upper()
    conn = get_connection()
    cur = await conn.execute(
        "SELECT * FROM products WHERE UPPER(sku) = ? AND (organization_id = ? OR organization_id IS NULL)",
        (sku, org_id),
    )
    row = await cur.fetchone()
    if not row:
        return json.dumps({"error": f"Product with SKU '{sku}' not found"})
    p = dict(row)
    return json.dumps({
        "sku": p.get("sku"),
        "name": p.get("name"),
        "description": p.get("description"),
        "price": p.get("price"),
        "cost": p.get("cost"),
        "quantity": p.get("quantity"),
        "min_stock": p.get("min_stock"),
        "department": p.get("department_name"),
        "vendor": p.get("vendor_name"),
        "original_sku": p.get("original_sku"),
        "barcode": p.get("barcode"),
        "base_unit": p.get("base_unit"),
        "sell_uom": p.get("sell_uom"),
        "pack_qty": p.get("pack_qty"),
    })


async def _get_inventory_stats(org_id: str) -> str:
    conn = get_connection()
    cur = await conn.execute(
        "SELECT COUNT(*) FROM products WHERE (organization_id = ? OR organization_id IS NULL)",
        (org_id,),
    )
    total_skus = (await cur.fetchone())[0]
    cur = await conn.execute(
        "SELECT COALESCE(SUM(quantity * cost), 0) FROM products WHERE (organization_id = ? OR organization_id IS NULL)",
        (org_id,),
    )
    total_value = round(float((await cur.fetchone())[0] or 0), 2)
    cur = await conn.execute(
        "SELECT COUNT(*) FROM products WHERE quantity <= min_stock AND (organization_id = ? OR organization_id IS NULL)",
        (org_id,),
    )
    low_count = (await cur.fetchone())[0]
    cur = await conn.execute(
        "SELECT COUNT(*) FROM products WHERE quantity = 0 AND (organization_id = ? OR organization_id IS NULL)",
        (org_id,),
    )
    out_of_stock = (await cur.fetchone())[0]
    return json.dumps({
        "total_skus": total_skus,
        "_note": "total_skus is the count of distinct product lines. No meaningful total unit count exists because products are measured in different units (each, gallon, box, etc.).",
        "total_cost_value": total_value,
        "low_stock_count": low_count,
        "out_of_stock_count": out_of_stock,
    })


async def _list_low_stock(args: dict, org_id: str) -> str:
    limit = min(int(args.get("limit") or 20), 50)
    items = await catalog_list_low_stock(limit=limit, organization_id=org_id)
    out = [
        {
            "sku": p.get("sku"),
            "name": p.get("name"),
            "quantity": p.get("quantity"),
            "sell_uom": p.get("sell_uom", "each"),
            "min_stock": p.get("min_stock"),
            "department": p.get("department_name"),
        }
        for p in items
    ]
    return json.dumps({"count": len(out), "products": out})


async def _list_departments(org_id: str) -> str:
    depts = await catalog_list_departments(organization_id=org_id)
    counters = await get_sku_counters()
    out = []
    for d in depts:
        code = d.get("code", "")
        next_num = counters.get(code, 0) + 1
        next_sku = f"{code}-ITM-{str(next_num).zfill(6)}"
        out.append({
            "name": d.get("name"),
            "code": code,
            "product_count": d.get("product_count", 0),
            "next_sku": next_sku,
        })
    return json.dumps({"departments": out})


async def _list_vendors(org_id: str) -> str:
    vendors = await catalog_list_vendors(organization_id=org_id)
    out = [{"name": v.get("name"), "product_count": v.get("product_count", 0)} for v in vendors]
    return json.dumps({"vendors": out})


async def _get_usage_velocity(args: dict, org_id: str) -> str:
    sku = (args.get("sku") or "").strip().upper()
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_connection()
    cur = await conn.execute(
        "SELECT id, name, quantity, sell_uom FROM products WHERE UPPER(sku) = ? AND (organization_id = ? OR organization_id IS NULL)",
        (sku, org_id),
    )
    row = await cur.fetchone()
    if not row:
        return json.dumps({"error": f"Product '{sku}' not found"})
    product_id, product_name, current_qty, sell_uom = row["id"], row["name"], row["quantity"], row["sell_uom"] or "each"
    cur = await conn.execute(
        """SELECT COUNT(*) as txn_count, COALESCE(SUM(ABS(quantity_delta)), 0) as total_used
           FROM stock_transactions
           WHERE product_id = ? AND transaction_type = 'WITHDRAWAL' AND created_at >= ?""",
        (product_id, since),
    )
    row = await cur.fetchone()
    txn_count = row["txn_count"] if row else 0
    total_used = int(row["total_used"]) if row else 0
    avg_daily = round(total_used / days, 2)
    days_until_zero = round(current_qty / avg_daily, 1) if avg_daily > 0 else None
    return json.dumps({
        "sku": sku,
        "name": product_name,
        "sell_uom": sell_uom,
        "current_quantity": current_qty,
        "period_days": days,
        "total_withdrawn": total_used,
        "withdrawal_transactions": txn_count,
        "avg_daily_use": avg_daily,
        "days_until_stockout": days_until_zero,
        "_note": None if days_until_zero is not None else "days_until_stockout is null because avg_daily_use=0 — no withdrawals recorded in this period, not a data error.",
    })


async def _get_reorder_suggestions(args: dict, org_id: str) -> str:
    limit = min(int(args.get("limit") or 20), 50)
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    conn = get_connection()
    low_stock = await catalog_list_low_stock(limit=100, organization_id=org_id)
    if not low_stock:
        return json.dumps({"count": 0, "suggestions": []})
    product_ids = [p["id"] for p in low_stock]
    placeholders = ",".join("?" * len(product_ids))
    cur = await conn.execute(
        f"""SELECT product_id, COALESCE(SUM(ABS(quantity_delta)), 0) as total_used
            FROM stock_transactions
            WHERE product_id IN ({placeholders}) AND transaction_type = 'WITHDRAWAL' AND created_at >= ?
            GROUP BY product_id""",
        (*product_ids, since),
    )
    velocity_map = {row["product_id"]: row["total_used"] for row in await cur.fetchall()}
    suggestions = []
    for p in low_stock:
        total_used = velocity_map.get(p["id"], 0)
        avg_daily = total_used / 30
        qty = p.get("quantity", 0)
        days_until_zero = round(qty / avg_daily, 1) if avg_daily > 0 else None
        urgency = (
            "critical" if days_until_zero is not None and days_until_zero <= 3
            else "high" if days_until_zero is not None and days_until_zero <= 7
            else "medium" if days_until_zero is not None
            else "no_velocity_data"
        )
        suggestions.append({
            "sku": p.get("sku"),
            "name": p.get("name"),
            "quantity": qty,
            "sell_uom": p.get("sell_uom", "each"),
            "min_stock": p.get("min_stock"),
            "avg_daily_use": round(avg_daily, 2),
            "days_until_stockout": days_until_zero,
            "urgency": urgency,
        })
    suggestions.sort(key=lambda x: (
        x["days_until_stockout"] is None,
        x["days_until_stockout"] if x["days_until_stockout"] is not None else 9999,
    ))
    return json.dumps({
        "count": len(suggestions),
        "suggestions": suggestions[:limit],
        "_note": "urgency='no_velocity_data' means the product has no withdrawal history in the last 30 days — it is still below reorder point and may need restocking.",
    })


async def _get_department_health(org_id: str) -> str:
    conn = get_connection()
    cur = await conn.execute(
        """SELECT d.name, d.code,
                  COUNT(p.id) as product_count,
                  SUM(CASE WHEN p.quantity = 0 THEN 1 ELSE 0 END) as out_of_stock,
                  SUM(CASE WHEN p.quantity > 0 AND p.quantity <= p.min_stock THEN 1 ELSE 0 END) as low_stock,
                  SUM(CASE WHEN p.quantity > p.min_stock THEN 1 ELSE 0 END) as healthy
           FROM departments d
           LEFT JOIN products p ON p.department_id = d.id
             AND (p.organization_id = ? OR p.organization_id IS NULL)
           WHERE (d.organization_id = ? OR d.organization_id IS NULL)
           GROUP BY d.id, d.name, d.code
           ORDER BY (out_of_stock + low_stock) DESC""",
        (org_id, org_id),
    )
    rows = [dict(r) for r in await cur.fetchall()]
    return json.dumps({"departments": rows})


async def _get_slow_movers(args: dict, org_id: str) -> str:
    limit = min(int(args.get("limit") or 20), 100)
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_connection()
    cur = await conn.execute(
        """SELECT p.id, p.sku, p.name, p.quantity, p.sell_uom, p.min_stock,
                  p.department_name,
                  COALESCE(txn.total_used, 0) as units_withdrawn
           FROM products p
           LEFT JOIN (
               SELECT product_id, SUM(ABS(quantity_delta)) as total_used
               FROM stock_transactions
               WHERE transaction_type = 'WITHDRAWAL' AND created_at >= ?
               GROUP BY product_id
           ) txn ON p.id = txn.product_id
           WHERE (p.organization_id = ? OR p.organization_id IS NULL)
             AND p.quantity > 0
           ORDER BY COALESCE(txn.total_used, 0) ASC, p.quantity DESC
           LIMIT ?""",
        (since, org_id, limit),
    )
    rows = [dict(r) for r in await cur.fetchall()]
    out = [
        {
            "sku": r["sku"],
            "name": r["name"],
            "quantity": r["quantity"],
            "sell_uom": r["sell_uom"] or "each",
            "department": r["department_name"],
            "units_withdrawn_30d": int(r["units_withdrawn"]),
        }
        for r in rows
    ]
    return json.dumps({"period_days": days, "count": len(out), "slow_movers": out})
