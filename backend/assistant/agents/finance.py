"""
FinanceAgent: invoices, payments, outstanding balances, revenue, P&L.
Tools: get_invoice_summary, get_outstanding_balances, get_revenue_summary, get_pl_summary, get_top_products.
"""
import json
import logging
from datetime import datetime, timezone, timedelta

from pydantic_ai import Agent, RunContext

from shared.infrastructure.config import (
    AGENT_PRIMARY_MODEL,
    AGENT_THINKING_BUDGET,
    DEFAULT_DEEP_THINKING_BUDGET,
)
from assistant.agents.deps import AgentDeps

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

_agent = Agent(
    AGENT_PRIMARY_MODEL,
    deps_type=AgentDeps,
    system_prompt=SYSTEM_PROMPT,
)


@_agent.tool
async def get_invoice_summary(ctx: RunContext[AgentDeps]) -> str:
    """Invoice counts and totals grouped by status (draft, sent, paid)."""
    return await _get_invoice_summary(ctx.deps.org_id)


@_agent.tool
async def get_outstanding_balances(ctx: RunContext[AgentDeps], limit: int = 20) -> str:
    """Unpaid withdrawal balances grouped by billing entity/contractor. Shows who owes money."""
    return await _get_outstanding_balances({"limit": limit}, ctx.deps.org_id)


@_agent.tool
async def get_revenue_summary(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Revenue summary for the last N days: total revenue, tax collected, transaction count."""
    return await _get_revenue_summary({"days": days}, ctx.deps.org_id)


@_agent.tool
async def get_pl_summary(ctx: RunContext[AgentDeps], days: int = 30) -> str:
    """Profit & loss for the last N days: revenue, cost of goods sold, gross profit and margin."""
    return await _get_pl_summary({"days": days}, ctx.deps.org_id)


@_agent.tool
async def get_top_products(ctx: RunContext[AgentDeps], days: int = 7, limit: int = 10) -> str:
    """Top products ranked by revenue over the last N days. Use for weekly/periodic sales reports."""
    return await _get_top_products({"days": days, "limit": limit}, ctx.deps.org_id)


async def run(user_message: str, history: list[dict] | None, deps: AgentDeps, mode: str = "fast") -> dict:
    from shared.infrastructure.config import ANTHROPIC_AVAILABLE
    if not ANTHROPIC_AVAILABLE:
        return {"response": "Finance agent requires ANTHROPIC_API_KEY.", "tool_calls": [], "history": [], "thinking": [], "agent": "finance"}

    from assistant.agents.agent_utils import build_message_history, extract_text_history, extract_tool_calls, calc_cost, run_agent

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
            agent_name="FinanceAgent",
        )
    except Exception as e:
        logger.error(f"FinanceAgent failed: {e}")
        return {"response": "I ran into an issue. Please try again in a moment.", "tool_calls": [], "history": history or [], "thinking": [], "agent": "finance"}

    usage = result.usage()
    cost = calc_cost(AGENT_PRIMARY_MODEL, usage)
    return {
        "response": result.output,
        "tool_calls": extract_tool_calls(result.all_messages()),
        "thinking": [],
        "history": extract_text_history(result.all_messages()),
        "usage": {"cost_usd": cost, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "model": AGENT_PRIMARY_MODEL},
        "agent": "finance",
    }


# ── DB query implementations (unchanged) ────────────────────────────────────

async def _get_invoice_summary(org_id: str) -> str:
    from finance.infrastructure.invoice_repo import invoice_repo
    invoices = await invoice_repo.list_invoices(limit=10000, organization_id=org_id)
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
    return json.dumps({"total_invoices": len(invoices), "grand_total": grand_total, "by_status": summary})


async def _get_outstanding_balances(args: dict, org_id: str) -> str:
    from operations.infrastructure.withdrawal_repo import withdrawal_repo
    limit = min(int(args.get("limit") or 20), 100)
    withdrawals = await withdrawal_repo.list_withdrawals(payment_status="unpaid", limit=10000, organization_id=org_id)
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
    return json.dumps({"total_outstanding": round(total_outstanding, 2), "entity_count": len(entity_map), "balances": out})


async def _get_revenue_summary(args: dict, org_id: str) -> str:
    from operations.infrastructure.withdrawal_repo import withdrawal_repo
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    withdrawals = await withdrawal_repo.list_withdrawals(start_date=since, limit=10000, organization_id=org_id)
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
    from operations.infrastructure.withdrawal_repo import withdrawal_repo
    days = min(int(args.get("days") or 30), 365)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    withdrawals = await withdrawal_repo.list_withdrawals(start_date=since, limit=10000, organization_id=org_id)
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
    from operations.infrastructure.withdrawal_repo import withdrawal_repo
    days = min(int(args.get("days") or 7), 365)
    limit = min(int(args.get("limit") or 10), 50)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    withdrawals = await withdrawal_repo.list_withdrawals(start_date=since, limit=10000, organization_id=org_id)
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
    return json.dumps({"period_days": days, "count": len(ranked), "products": ranked})
