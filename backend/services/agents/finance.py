"""
FinanceAgent: invoices, payments, outstanding balances, revenue, P&L.
Tools: get_invoice_summary, get_outstanding_balances, get_revenue_summary, get_pl_summary.
"""
import json
import logging
from datetime import datetime, timezone, timedelta

from config import ANTHROPIC_MODEL, ANTHROPIC_FAST_MODEL, AGENT_THINKING_BUDGET
from services.agents.base import run_agent, _build_conversation

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial analyst for SKU-Ops, a hardware store management system.

TOOLS — use them when the user asks about finances, invoices, or payments:
- get_invoice_summary(): invoice counts and totals broken down by status (draft/sent/paid)
- get_outstanding_balances(limit): unpaid balances grouped by billing entity/contractor
- get_revenue_summary(days): revenue, tax, and transaction count for a period
- get_pl_summary(days): profit & loss — revenue vs cost, gross margin
- get_top_products(days, limit): top revenue-generating products over a period (from withdrawals)

WHEN TO USE EACH TOOL:
- "invoice status / how many invoices / invoice overview" → get_invoice_summary
- "who owes us / outstanding balance / unpaid accounts" → get_outstanding_balances
- "how much revenue / sales this week/month" → get_revenue_summary
- "profit / margin / P&L / how much did we make" → get_pl_summary
- "top products / best sellers / weekly sales report" → get_top_products

WEEKLY SALES REPORT — when asked for a weekly or periodic report, call ALL of these in parallel:
  get_revenue_summary(days=7) + get_pl_summary(days=7) + get_top_products(days=7, limit=10) + get_outstanding_balances()
  Then format as a structured report with sections: Revenue Summary, Gross Margin, Top Products, Outstanding Balances.

FORMAT — respond in GitHub-flavored markdown:
- For balance and invoice tables, use a markdown table with a separator row:

| Entity | Balance | Withdrawals | Oldest Unpaid |
|--------|---------|-------------|---------------|
| ABC Corp | $1,250.00 | 3 | 2026-01-15 |

- For weekly/periodic reports, use ## section headers to separate each section
- Use **bold** for totals, margins, and key figures
- Lead with a one-line headline ("**$8,400 outstanding across 12 entities**") then the table
- Clearly separate revenue (billed) from cash received (paid status)

Never make up financial data — always use a tool.
Dollar amounts to 2 decimal places. Be concise and clear.

REASONING — think before acting:
1. Identify the financial question: invoice pipeline? cash collected? who owes what? profitability?
2. For "how are we doing" type questions, call get_revenue_summary AND get_pl_summary together
3. For weekly/periodic reports, pull all 4 data sources in parallel for a complete picture
4. When reporting balances, always surface the total outstanding and the top offenders by name
5. Distinguish between revenue (what was billed) and cash received (payment_status=paid)
6. Present margins as percentages, not just raw dollar differences — context matters"""

TOOL_SCHEMAS = [
    {
        "name": "get_invoice_summary",
        "description": "Invoice counts and totals grouped by status (draft, sent, paid).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_outstanding_balances",
        "description": "Unpaid withdrawal balances grouped by billing entity/contractor. Shows who owes money.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max entities to return", "default": 20},
            },
        },
    },
    {
        "name": "get_revenue_summary",
        "description": "Revenue summary for the last N days: total revenue, tax collected, transaction count.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Lookback window in days", "default": 30},
            },
        },
    },
    {
        "name": "get_pl_summary",
        "description": "Profit & loss for the last N days: revenue, cost of goods sold, gross profit and margin.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Lookback window in days", "default": 30},
            },
        },
    },
    {
        "name": "get_top_products",
        "description": "Top products ranked by revenue over the last N days. Use for weekly/periodic sales reports.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Lookback window in days", "default": 7},
                "limit": {"type": "integer", "description": "Max products to return", "default": 10},
            },
        },
    },
]


async def execute_tool(name: str, args: dict, ctx: dict) -> str:
    org_id = ctx.get("org_id", "default")
    try:
        if name == "get_invoice_summary":
            return await _get_invoice_summary(org_id)
        if name == "get_outstanding_balances":
            return await _get_outstanding_balances(args, org_id)
        if name == "get_revenue_summary":
            return await _get_revenue_summary(args, org_id)
        if name == "get_pl_summary":
            return await _get_pl_summary(args, org_id)
        if name == "get_top_products":
            return await _get_top_products(args, org_id)
        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        logger.warning(f"FinanceAgent tool {name} error: {e}")
        return json.dumps({"error": str(e)})


async def _get_invoice_summary(org_id: str) -> str:
    from repositories import invoice_repo
    invoices = await invoice_repo.list_invoices(limit=10000, org_id=org_id)
    summary: dict[str, dict] = {}
    for inv in invoices:
        status = inv.get("status", "unknown")
        if status not in summary:
            summary[status] = {"count": 0, "total": 0.0}
        summary[status]["count"] += 1
        summary[status]["total"] += inv.get("total", 0)
    for s in summary.values():
        s["total"] = round(s["total"], 2)
    grand_total = round(sum(inv.get("total", 0) for inv in invoices), 2)
    return json.dumps({
        "total_invoices": len(invoices),
        "grand_total": grand_total,
        "by_status": summary,
    })


async def _get_outstanding_balances(args: dict, org_id: str) -> str:
    from repositories import withdrawal_repo
    limit = min(int(args.get("limit") or 20), 100)
    withdrawals = await withdrawal_repo.list_withdrawals(
        payment_status="unpaid",
        limit=10000,
        organization_id=org_id,
    )
    entity_map: dict[str, dict] = {}
    for w in withdrawals:
        entity = w.get("billing_entity") or w.get("contractor_name") or "Unknown"
        if entity not in entity_map:
            entity_map[entity] = {"balance": 0.0, "withdrawal_count": 0, "oldest": w.get("created_at", "")}
        entity_map[entity]["balance"] += w.get("total", 0)
        entity_map[entity]["withdrawal_count"] += 1
    sorted_entities = sorted(entity_map.items(), key=lambda x: x[1]["balance"], reverse=True)
    out = [
        {
            "entity": entity,
            "balance": round(data["balance"], 2),
            "withdrawal_count": data["withdrawal_count"],
            "oldest_unpaid": data["oldest"][:10],
        }
        for entity, data in sorted_entities[:limit]
    ]
    total_outstanding = sum(w.get("total", 0) for w in withdrawals)
    return json.dumps({
        "total_outstanding": round(total_outstanding, 2),
        "entity_count": len(entity_map),
        "balances": out,
    })


async def _get_revenue_summary(args: dict, org_id: str) -> str:
    from repositories import withdrawal_repo
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=since,
        limit=10000,
        organization_id=org_id,
    )
    total_revenue = sum(w.get("total", 0) for w in withdrawals)
    total_tax = sum(w.get("tax", 0) for w in withdrawals)
    paid = sum(w.get("total", 0) for w in withdrawals if w.get("payment_status") == "paid")
    unpaid = sum(w.get("total", 0) for w in withdrawals if w.get("payment_status") == "unpaid")
    invoiced = sum(w.get("total", 0) for w in withdrawals if w.get("payment_status") == "invoiced")
    return json.dumps({
        "period_days": days,
        "transaction_count": len(withdrawals),
        "total_revenue": round(total_revenue, 2),
        "total_tax": round(total_tax, 2),
        "revenue_ex_tax": round(total_revenue - total_tax, 2),
        "paid": round(paid, 2),
        "unpaid": round(unpaid, 2),
        "invoiced": round(invoiced, 2),
    })


async def _get_pl_summary(args: dict, org_id: str) -> str:
    from repositories import withdrawal_repo
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    withdrawals = await withdrawal_repo.list_withdrawals(
        start_date=since,
        limit=10000,
        organization_id=org_id,
    )
    total_revenue = sum(w.get("total", 0) for w in withdrawals)
    total_cost = sum(w.get("cost_total", 0) for w in withdrawals)
    gross_profit = total_revenue - total_cost
    margin_pct = round((gross_profit / total_revenue * 100), 1) if total_revenue > 0 else 0
    return json.dumps({
        "period_days": days,
        "transaction_count": len(withdrawals),
        "revenue": round(total_revenue, 2),
        "cost_of_goods": round(total_cost, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_margin_pct": margin_pct,
    })


async def _get_top_products(args: dict, org_id: str) -> str:
    from repositories import withdrawal_repo
    days = min(int(args.get("days") or 7), 365)
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
    ranked = sorted(product_map.values(), key=lambda x: x["total_revenue"], reverse=True)[:limit]
    for r in ranked:
        r["total_revenue"] = round(r["total_revenue"], 2)
    return json.dumps({
        "period_days": days,
        "count": len(ranked),
        "products": ranked,
    })


async def chat(
    messages: list[dict],
    user_message: str,
    history: list[dict] | None,
    ctx: dict,
) -> dict:
    from config import ANTHROPIC_AVAILABLE, ANTHROPIC_API_KEY
    if not ANTHROPIC_AVAILABLE:
        return {"response": "Finance agent requires ANTHROPIC_API_KEY.", "tool_calls": [], "history": [], "thinking": []}
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
        "agent": "finance",
    }
