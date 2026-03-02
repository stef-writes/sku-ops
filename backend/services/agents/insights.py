"""
InsightsAgent: trends, top products, velocity, stockout forecasting.
Tools: get_top_products, get_department_activity, forecast_stockout.
"""
import json
import logging
from datetime import datetime, timezone, timedelta

from config import ANTHROPIC_MODEL, ANTHROPIC_FAST_MODEL, AGENT_THINKING_BUDGET
from db import get_connection
from services.agents.base import run_agent, _build_conversation

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a business insights analyst for SKU-Ops, a hardware store management system.

TOOLS — use them when the user asks about trends, analytics, or forecasting:
- get_top_products(days, by, limit): top products by volume (units) or revenue over a period
- get_department_activity(dept_code, days): stock movement summary for a department
- forecast_stockout(limit): products predicted to run out soon based on usage velocity

WHEN TO USE EACH TOOL:
- "top selling / most used / best products / highest revenue" → get_top_products
- "how is [dept] performing / department activity / PLU/ELE/HDW movement" → get_department_activity
- "what's going to run out / stockout forecast / upcoming shortages" → forecast_stockout

Department codes: PLU=plumbing, ELE=electrical, PNT=paint, LUM=lumber,
                  TOL=tools, HDW=hardware, GDN=garden, APP=appliances

FORMAT — respond in GitHub-flavored markdown:
- For rankings and forecasts, use a markdown table with a separator row:

| Rank | Product | Units | Revenue |
|------|---------|-------|---------|
| 1 | PVC Pipe 1/2" | 142 | $284.00 |

- Use **bold** for #1 items, critical-risk stockouts, and key totals
- Lead with a summary sentence ("**Top product earned 3× more than #2**") before the table
- For stockout forecasts, sort by urgency; flag ≤3 days as critical with bold or a note

Never make up analytics data — always use a tool.
Be specific with numbers, trends, and time periods.

REASONING — think before acting:
1. Identify the analytical lens: ranking? trend over time? risk/forecast? department health?
2. For "what's popular" → get_top_products; for "what's at risk" → forecast_stockout; for dept-specific → get_department_activity
3. If the question spans multiple departments or timeframes, call tools in parallel
4. After results, go beyond the raw list: note the gap between #1 and #2, flag critical-risk items, highlight outliers
5. Always state the time period for any trend or ranking — "top products over 30 days" not just "top products"
6. For stockout forecasts, prioritise critical (≤3 days) over high (≤7 days) — tell the user what needs action today"""

TOOL_SCHEMAS = [
    {
        "name": "get_top_products",
        "description": "Top products ranked by units withdrawn or revenue generated over the last N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Lookback window in days", "default": 30},
                "by": {"type": "string", "description": "'volume' (units) or 'revenue' (dollars)", "default": "revenue"},
                "limit": {"type": "integer", "description": "Max results", "default": 10},
            },
        },
    },
    {
        "name": "get_department_activity",
        "description": "Stock movement summary for a department over the last N days (withdrawals, receiving, net change).",
        "input_schema": {
            "type": "object",
            "properties": {
                "dept_code": {"type": "string", "description": "Department code (e.g. PLU, ELE, HDW)"},
                "days": {"type": "integer", "description": "Lookback window in days", "default": 30},
            },
            "required": ["dept_code"],
        },
    },
    {
        "name": "forecast_stockout",
        "description": "Products predicted to run out soonest based on recent withdrawal velocity. Returns days-until-zero estimates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max products to return", "default": 15},
            },
        },
    },
]


async def execute_tool(name: str, args: dict, ctx: dict) -> str:
    org_id = ctx.get("org_id", "default")
    try:
        if name == "get_top_products":
            return await _get_top_products(args, org_id)
        if name == "get_department_activity":
            return await _get_department_activity(args, org_id)
        if name == "forecast_stockout":
            return await _forecast_stockout(args, org_id)
        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        logger.warning(f"InsightsAgent tool {name} error: {e}")
        return json.dumps({"error": str(e)})


async def _get_top_products(args: dict, org_id: str) -> str:
    from repositories import withdrawal_repo
    days = min(int(args.get("days") or 30), 365)
    by = args.get("by", "revenue").lower()
    if by not in ("volume", "revenue"):
        by = "revenue"
    limit = min(int(args.get("limit") or 10), 50)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=since,
        limit=10000,
        organization_id=org_id,
    )
    product_map: dict[str, dict] = {}
    for w in withdrawals:
        for item in (w.get("items") or []):
            sku = item.get("sku") or item.get("name", "unknown")
            name = item.get("name", sku)
            qty = item.get("quantity", 0)
            revenue = item.get("subtotal", 0)
            if sku not in product_map:
                product_map[sku] = {"sku": sku, "name": name, "total_units": 0, "total_revenue": 0.0}
            product_map[sku]["total_units"] += qty
            product_map[sku]["total_revenue"] += revenue
    sort_key = "total_revenue" if by == "revenue" else "total_units"
    ranked = sorted(product_map.values(), key=lambda x: x[sort_key], reverse=True)[:limit]
    for r in ranked:
        r["total_revenue"] = round(r["total_revenue"], 2)
    return json.dumps({
        "period_days": days,
        "ranked_by": by,
        "count": len(ranked),
        "products": ranked,
    })


async def _get_department_activity(args: dict, org_id: str) -> str:
    dept_code = (args.get("dept_code") or "").strip().upper()
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_connection()
    # Get department products
    cur = await conn.execute(
        """SELECT p.id, p.sku, p.name, p.quantity, p.min_stock
           FROM products p
           JOIN departments d ON p.department_id = d.id
           WHERE UPPER(d.code) = ?
             AND (p.organization_id = ? OR p.organization_id IS NULL)""",
        (dept_code, org_id),
    )
    products = [dict(r) for r in await cur.fetchall()]
    if not products:
        return json.dumps({"error": f"Department '{dept_code}' not found or has no products"})
    product_ids = [p["id"] for p in products]
    placeholders = ",".join("?" * len(product_ids))
    # Stock transaction summary
    cur = await conn.execute(
        f"""SELECT
              transaction_type,
              COUNT(*) as txn_count,
              COALESCE(SUM(ABS(quantity_delta)), 0) as total_units
            FROM stock_transactions
            WHERE product_id IN ({placeholders}) AND created_at >= ?
            GROUP BY transaction_type""",
        (*product_ids, since),
    )
    type_summary: dict[str, dict] = {}
    for row in await cur.fetchall():
        type_summary[row["transaction_type"]] = {
            "transactions": row["txn_count"],
            "units": int(row["total_units"]),
        }
    withdrawals = type_summary.get("WITHDRAWAL", {"transactions": 0, "units": 0})
    receiving = type_summary.get("RECEIVING", {"transactions": 0, "units": 0})
    imports = type_summary.get("IMPORT", {"transactions": 0, "units": 0})
    low_stock_count = sum(1 for p in products if p["quantity"] <= p["min_stock"])
    return json.dumps({
        "dept_code": dept_code,
        "period_days": days,
        "product_count": len(products),
        "low_stock_count": low_stock_count,
        "withdrawals": withdrawals,
        "receiving": receiving,
        "imports": imports,
        "net_units": (receiving["units"] + imports["units"]) - withdrawals["units"],
    })


async def _forecast_stockout(args: dict, org_id: str) -> str:
    limit = min(int(args.get("limit") or 15), 50)
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    conn = get_connection()
    # All products with quantity > 0 (zero-stock already known)
    cur = await conn.execute(
        """SELECT id, sku, name, quantity, min_stock, department_name
           FROM products
           WHERE quantity > 0
             AND (organization_id = ? OR organization_id IS NULL)
           ORDER BY quantity ASC
           LIMIT 200""",
        (org_id,),
    )
    products = [dict(r) for r in await cur.fetchall()]
    if not products:
        return json.dumps({"count": 0, "forecast": []})
    product_ids = [p["id"] for p in products]
    placeholders = ",".join("?" * len(product_ids))
    cur = await conn.execute(
        f"""SELECT product_id, COALESCE(SUM(ABS(quantity_delta)), 0) as total_used
            FROM stock_transactions
            WHERE product_id IN ({placeholders}) AND transaction_type = 'WITHDRAWAL' AND created_at >= ?
            GROUP BY product_id""",
        (*product_ids, since),
    )
    velocity_map = {row["product_id"]: row["total_used"] for row in await cur.fetchall()}
    forecast = []
    for p in products:
        total_used = velocity_map.get(p["id"], 0)
        avg_daily = total_used / 30
        if avg_daily <= 0:
            continue  # not moving → not a stockout risk
        days_until_zero = round(p["quantity"] / avg_daily, 1)
        forecast.append({
            "sku": p["sku"],
            "name": p["name"],
            "department": p["department_name"],
            "quantity": p["quantity"],
            "min_stock": p["min_stock"],
            "avg_daily_use": round(avg_daily, 2),
            "days_until_stockout": days_until_zero,
            "risk": "critical" if days_until_zero <= 3 else "high" if days_until_zero <= 7 else "medium",
        })
    forecast.sort(key=lambda x: x["days_until_stockout"])
    return json.dumps({"count": len(forecast), "forecast": forecast[:limit]})


async def chat(
    messages: list[dict],
    user_message: str,
    history: list[dict] | None,
    ctx: dict,
) -> dict:
    from config import ANTHROPIC_AVAILABLE, ANTHROPIC_API_KEY
    if not ANTHROPIC_AVAILABLE:
        return {"response": "Insights agent requires ANTHROPIC_API_KEY.", "tool_calls": [], "history": [], "thinking": []}
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    thinking_budget = AGENT_THINKING_BUDGET
    model = ANTHROPIC_MODEL if thinking_budget > 0 else ANTHROPIC_FAST_MODEL
    conversation = _build_conversation(messages, history, user_message)
    result = await run_agent(
        client, model, SYSTEM_PROMPT, TOOL_SCHEMAS, execute_tool, conversation, ctx,
        thinking_budget=thinking_budget,
    )
    return {
        "response": result["response"],
        "tool_calls": result["tool_calls"],
        "thinking": result.get("thinking", []),
        "history": result["conversation"],
        "agent": "insights",
    }
